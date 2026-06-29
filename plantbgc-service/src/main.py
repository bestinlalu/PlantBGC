import io
import os
import shutil
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, Form, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from src.database import get_db, Base, engine
from src.models import AnalysisJob
from src.config import settings
from src.email_utils import send_queued_email
import src.models


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Wait for Postgres to be ready before creating tables.
    # The healthcheck in docker-compose ensures postgres accepts connections
    # before this container starts, but we retry here as an extra safety net.
    for attempt in range(10):
        try:
            Base.metadata.create_all(bind=engine)
            break
        except Exception as exc:
            if attempt == 9:
                raise RuntimeError(f"DB not ready after 10 attempts: {exc}") from exc
            time.sleep(3)
    yield


app = FastAPI(title="PlantBGC Genome Analysis API", lifespan=lifespan)

# Target the templates folder safely across systems
current_dir = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(current_dir, "templates"))

app.mount("/icons", StaticFiles(directory=os.path.join(current_dir, "icons")), name="icons")

# --- FRONTEND ROUTE ---
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serves the front-end dashboard UI directly to browser requests."""
    return templates.TemplateResponse("index.html", {"request": request})


ALLOWED_EXTENSIONS = {".fna", ".fa", ".fasta", ".gbk", ".gbff"}
ALLOWED_INPUT_TYPES = {"genome_dna", "cds_nucleotide", "protein_fasta"}
ALLOWED_RUN_MODES = {"predict_bgc"}


# --- BACKEND API ENDPOINT ---
@app.post("/api/v1/analyze")
async def analyze_genome(
    email: str = Form(...),
    job_name: str = Form(""),
    input_type: str = Form("genome_dna"),
    run_mode: str = Form("predict_bgc"),
    use_for_training: bool = Form(False),
    file: UploadFile = Form(...),
    db: Session = Depends(get_db)
):
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    if input_type not in ALLOWED_INPUT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid input_type: {input_type}")

    if run_mode not in ALLOWED_RUN_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid run_mode: {run_mode}")

    job_id = uuid.uuid4()
    unique_filename = f"{job_id}_{file.filename}"
    destination_path = os.path.join(settings.UPLOAD_DIR, "raw", unique_filename)

    try:
        with open(destination_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                buffer.write(chunk)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {str(e)}")

    if use_for_training:
        training_path = os.path.join(settings.UPLOAD_DIR, "training", unique_filename)
        shutil.copy2(destination_path, training_path)

    db_job = AnalysisJob(
        id=job_id,
        user_email=email,
        job_name=job_name.strip() or None,
        input_filename=file.filename,
        input_file_path=destination_path,
        input_type=input_type,
        run_mode=run_mode,
        allow_training=use_for_training,
        status="PENDING"
    )
    db.add(db_job)
    db.commit()

    # bgc_worker polls the DB for PENDING jobs — no Celery dispatch needed here.
    # (Celery 5.x requires Python >=3.8; plantbgc requires Python <3.8 — incompatible.)

    # Queue position = count of PENDING jobs created at or before this one (FIFO order).
    queue_position = (
        db.query(AnalysisJob)
        .filter(AnalysisJob.status == "PENDING")
        .filter(AnalysisJob.created_at <= db_job.created_at)
        .count()
    )
    send_queued_email(email, str(job_id), queue_position)

    return {
        "job_id": str(job_id),
        "status": "PENDING",
        "queue_position": queue_position,
        "message": "Genome uploaded and successfully queued. Check your email for updates!"
    }


# --- DOWNLOAD ENDPOINT ---
@app.get("/api/v1/jobs/{job_id}/download")
def download_results(job_id: str, db: Session = Depends(get_db)):
    """
    Zips the output directory for a completed job and streams it to the user.
    The job_id UUID acts as an unguessable access token.
    """
    job = db.query(AnalysisJob).filter(AnalysisJob.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    if job.status != "COMPLETE":
        raise HTTPException(
            status_code=400,
            detail=f"Results are not ready yet. Current status: {job.status}"
        )

    output_dir = job.output_file_path
    if not output_dir or not os.path.isdir(output_dir):
        raise HTTPException(status_code=404, detail="Output directory not found on disk.")

    # Stream a zip of the entire output directory back to the client
    def zip_stream():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(output_dir):
                for filename in files:
                    file_path = os.path.join(root, filename)
                    # Store relative path inside the zip so it's clean when extracted
                    arcname = os.path.relpath(file_path, start=output_dir)
                    zf.write(file_path, arcname)
        buffer.seek(0)
        yield from buffer

    zip_filename = f"plantbgc_results_{job_id}.zip"
    return StreamingResponse(
        zip_stream(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )