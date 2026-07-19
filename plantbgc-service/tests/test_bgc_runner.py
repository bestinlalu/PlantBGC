"""
Tests for src/bgc_runner.py.

plantbgc subprocess calls are always mocked — no real analysis runs.
"""
import os
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models import AnalysisJob

DATABASE_URL = os.environ["DATABASE_URL"]


# ── Postgres DB shared across runner tests ────────────────────────────────────

@pytest.fixture(scope="module")
def runner_engine():
    eng = create_engine(DATABASE_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def runner_db(runner_engine):
    Session = sessionmaker(bind=runner_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


def _pending_job(runner_db, tmp_path=None):
    import pathlib
    from src.config import settings
    upload_raw = pathlib.Path(settings.UPLOAD_DIR) / "raw"
    upload_raw.mkdir(parents=True, exist_ok=True)
    input_file = upload_raw / "test_genome.fna"
    input_file.write_bytes(b">seq\nATCG\n")
    job_id = uuid.uuid4()
    job = AnalysisJob(
        id=job_id,
        user_email="user@test.com",
        job_name="TestJob",
        input_filename="genome.fna",
        input_file_path=str(input_file),
        status="PENDING",
    )
    runner_db.add(job)
    runner_db.commit()
    return job_id, str(input_file)


# ── _build_plantbgc_command ───────────────────────────────────────────────────

def test_build_command_genome_dna(tmp_path):
    from src.bgc_runner import _build_plantbgc_command
    cmd = _build_plantbgc_command("/input.fna", "/out", "genome_dna", "predict_bgc")
    assert cmd[0] == "plantbgc"
    assert "Predict" in cmd
    assert "/input.fna" in cmd
    assert "/out" in cmd
    assert "--protein" not in cmd


def test_build_command_protein_fasta_adds_flag(tmp_path):
    from src.bgc_runner import _build_plantbgc_command
    cmd = _build_plantbgc_command("/proteins.faa", "/out", "protein_fasta", "predict_bgc")
    assert "--protein" in cmd


# ── _process_job ──────────────────────────────────────────────────────────────

def test_process_job_marks_complete_on_success(runner_db, monkeypatch):
    import src.bgc_runner as runner
    job_id, input_path = _pending_job(runner_db)

    monkeypatch.setattr(runner, "SessionLocal", sessionmaker(bind=runner_db.bind))
    monkeypatch.setattr("src.bgc_runner.send_completion_email", lambda **kw: None)
    monkeypatch.setattr("src.bgc_runner.send_failure_admin_email", lambda **kw: None)

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "done"
    mock_result.stderr = ""

    with patch("src.bgc_runner.subprocess.run", return_value=mock_result):
        runner._process_job(str(job_id), input_path, "genome_dna",
                            "predict_bgc", "user@test.com", "TestJob")

    runner_db.expire_all()  # flush identity map so we see the committed update
    job = runner_db.query(AnalysisJob).filter_by(id=job_id).first()
    assert job.status == "COMPLETE"
    assert job.completed_at is not None


def test_process_job_marks_failed_on_nonzero_exit(runner_db, monkeypatch):
    import src.bgc_runner as runner
    job_id, input_path = _pending_job(runner_db)

    monkeypatch.setattr(runner, "SessionLocal", sessionmaker(bind=runner_db.bind))
    monkeypatch.setattr("src.bgc_runner.send_completion_email", lambda **kw: None)
    monkeypatch.setattr("src.bgc_runner.send_failure_admin_email", lambda **kw: None)

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "OOM"

    with patch("src.bgc_runner.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError):
            runner._process_job(str(job_id), input_path, "genome_dna",
                                "predict_bgc", "user@test.com", "TestJob")

    runner_db.expire_all()  # flush identity map so we see the committed update
    job = runner_db.query(AnalysisJob).filter_by(id=job_id).first()
    assert job.status == "FAILED"
    assert job.error_message is not None


def test_process_job_sends_admin_email_on_failure(runner_db, monkeypatch):
    import src.bgc_runner as runner
    job_id, input_path = _pending_job(runner_db)

    monkeypatch.setattr(runner, "SessionLocal", sessionmaker(bind=runner_db.bind))
    monkeypatch.setattr("src.bgc_runner.send_completion_email", lambda **kw: None)

    admin_calls = []
    monkeypatch.setattr("src.bgc_runner.send_failure_admin_email",
                        lambda **kw: admin_calls.append(kw))

    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "crash"

    with patch("src.bgc_runner.subprocess.run", return_value=mock_result):
        with pytest.raises(RuntimeError):
            runner._process_job(str(job_id), input_path, "genome_dna",
                                "predict_bgc", "user@test.com", "TestJob")

    assert len(admin_calls) == 1
    assert admin_calls[0]["user_email"] == "user@test.com"


def test_process_job_does_not_send_admin_email_on_success(runner_db, monkeypatch):
    import src.bgc_runner as runner
    job_id, input_path = _pending_job(runner_db)

    monkeypatch.setattr(runner, "SessionLocal", sessionmaker(bind=runner_db.bind))
    monkeypatch.setattr("src.bgc_runner.send_completion_email", lambda **kw: None)

    admin_calls = []
    monkeypatch.setattr("src.bgc_runner.send_failure_admin_email",
                        lambda **kw: admin_calls.append(kw))

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "ok"
    mock_result.stderr = ""

    with patch("src.bgc_runner.subprocess.run", return_value=mock_result):
        runner._process_job(str(job_id), input_path, "genome_dna",
                            "predict_bgc", "user@test.com", "TestJob")

    assert admin_calls == []
