"""
BGC Worker — Database polling runner (Python 3.7).

Replaces Celery for the bgc_worker because:
  - plantbgc (PyPI) requires Python <3.8
  - Celery 5.x requires Python >=3.8
  - These constraints are mutually exclusive in the same container

Flow:
  1. Poll DB every POLL_INTERVAL seconds for a PENDING job
  2. Claim it (set STARTED) and run plantbgc Predict / prepare
  3. Mark COMPLETE or FAILED, send completion email directly via SMTP
"""
from __future__ import annotations

import os
import signal
import time
import subprocess  # TODO: Uncomment when plantbgc release with syntax fixes is published
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings
from src.database import Base
from src.models import AnalysisJob
from src.email_utils import send_started_email, send_completion_email

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "15"))  # seconds between DB polls

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Set by the SIGTERM handler when a deploy wants this container to shut down.
# We never kill a running plantbgc job — we just stop claiming NEW jobs after
# the current one (if any) finishes. Combined with a long stop_grace_period in
# docker-compose.yml, `docker compose up` can swap worker images without ever
# losing in-progress work.
_draining = False


def _handle_sigterm(signum, frame):
    global _draining
    print("Received SIGTERM — draining: will finish current job, then exit "
          "without claiming new ones.")
    _draining = True


signal.signal(signal.SIGTERM, _handle_sigterm)


def _wait_for_tables() -> None:
    """Create tables if missing. Idempotent — safe alongside bgc_web's own create_all.
    Retries so the worker doesn't depend on bgc_web's startup timing."""
    for attempt in range(10):
        try:
            Base.metadata.create_all(bind=engine)
            return
        except Exception as exc:
            if attempt == 9:
                raise RuntimeError(f"DB not ready after 10 attempts: {exc}") from exc
            time.sleep(3)


# ── Command builder ────────────────────────────────────────────────────────────

def _build_plantbgc_command(input_file_path: str, output_dir: str,
                             input_type: str, run_mode: str) -> list:
    """Build the plantbgc CLI command based on job configuration."""
    cmd = [
        "plantbgc", "Predict",
        "--output", output_dir,
        "--score", "0.5",
        "--min-proteins", "3",
        "--prodigal-meta-mode",   # handles contigs shorter than 20,000 bp
    ]
    if input_type == "protein_fasta":
        cmd.append("--protein")
    cmd.append(input_file_path)
    return cmd


# ── Job processor ──────────────────────────────────────────────────────────────

def _process_job(job_id: str, input_file_path: str, input_type: str,
                 run_mode: str, user_email: str) -> None:
    """Run the plantbgc command for one job, then update DB and send email."""
    output_dir = os.path.join(settings.UPLOAD_DIR, "results", job_id)
    os.makedirs(output_dir, exist_ok=True)

    analysis_error: Exception | None = None

    try:
        # ------------------------------------------------------------------
        # TODO: Uncomment the block below when the plantbgc release with
        #       syntax fixes is published to PyPI and baked into Dockerfile.bgc
        #       (also uncomment `import subprocess` at the top of this file
        #       and `RUN plantbgc download` in Dockerfile.bgc)
        # ------------------------------------------------------------------
        cmd = _build_plantbgc_command(input_file_path, output_dir, input_type, run_mode)
        print(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"plantbgc failed (exit {result.returncode}):\n{result.stderr}"
            )
        print(f"plantbgc stdout:\n{result.stdout}")
        # ------------------------------------------------------------------

        # Stub: simulate a successful run until plantbgc release is ready
        cmd = _build_plantbgc_command(input_file_path, output_dir, input_type, run_mode)
        print(f"[STUB] Would run: {' '.join(cmd)}")

    except Exception as e:
        analysis_error = e
        print(f"Job {job_id} analysis FAILED: {e}")

    # Write final status to DB
    db = SessionLocal()
    try:
        job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()
        if job:
            if analysis_error is None:
                job.status = "COMPLETE"
                job.output_file_path = output_dir
                print(f"Job {job_id} marked COMPLETE.")
            else:
                job.status = "FAILED"
                job.error_message = str(analysis_error)
                print(f"Job {job_id} marked FAILED.")
            job.completed_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"DB write failed for job {job_id}: {e}")
    finally:
        db.close()

    # Send completion email (always, regardless of success/failure)
    send_completion_email(
        user_email=user_email,
        job_id=job_id,
        status="COMPLETE" if analysis_error is None else "FAILED",
        error_message=str(analysis_error) if analysis_error else None,
    )

    if analysis_error:
        raise analysis_error


# ── Polling loop ───────────────────────────────────────────────────────────────

def poll() -> None:
    _wait_for_tables()
    print(f"BGC runner started. Polling every {POLL_INTERVAL}s for PENDING jobs...")

    while True:
        if _draining:
            print("Draining complete — no job in progress. Exiting cleanly.")
            return

        db = SessionLocal()
        job_id = input_file_path = input_type = run_mode = user_email = None

        try:
            # SELECT FOR UPDATE SKIP LOCKED — atomically claims one PENDING job.
            # If two bgc_worker containers run concurrently, each will lock a
            # different row; neither can see the other's locked row, preventing
            # double processing. FIFO order is enforced by created_at.
            job = (
                db.query(AnalysisJob)
                .filter(AnalysisJob.status == "PENDING")
                .order_by(AnalysisJob.created_at)
                .with_for_update(skip_locked=True)
                .first()
            )

            if job:
                # Claim the job atomically before releasing the session
                job_id = str(job.id)
                input_file_path = job.input_file_path
                input_type = job.input_type
                run_mode = job.run_mode
                user_email = job.user_email

                job.status = "STARTED"
                job.started_at = datetime.utcnow()
                db.commit()
                print(f"Claimed job {job_id} | type={input_type} | mode={run_mode}")
                send_started_email(user_email, job_id)

        except Exception as e:
            db.rollback()
            print(f"DB poll error: {e}")
        finally:
            db.close()

        if job_id and input_file_path and user_email:
            # Process outside the DB session (avoids holding connection during long run)
            try:
                _process_job(job_id, input_file_path, input_type or "genome_dna",
                             run_mode or "predict_bgc", user_email)
            except Exception as e:
                print(f"Job {job_id} raised unhandled exception: {e}")
        else:
            # No pending jobs — wait before next poll
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    poll()
