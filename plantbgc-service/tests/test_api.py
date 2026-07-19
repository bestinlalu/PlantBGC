"""
Tests for the FastAPI endpoints in src/main.py.
"""
import io
import os
import uuid
import zipfile

import pytest

from src.models import AnalysisJob


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fna_file(name="genome.fna", content=b">seq1\nATCG\n"):
    return ("file", (name, io.BytesIO(content), "application/octet-stream"))


def _submit(client, email="user@test.com", job_name="", filename="genome.fna",
            input_type="genome_dna"):
    return client.post("/api/v1/analyze", data={
        "email": email,
        "job_name": job_name,
        "input_type": input_type,
        "run_mode": "predict_bgc",
        "use_for_training": False,
    }, files=[_fna_file(filename)])


# ── UI ────────────────────────────────────────────────────────────────────────

def test_homepage_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "PlantBGC" in r.text
    assert "<html" in r.text.lower()


# ── Job submission ────────────────────────────────────────────────────────────

def test_submit_success(client):
    r = _submit(client, email="user@test.com", job_name="MyRun")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "PENDING"
    assert "job_id" in body
    assert body["queue_position"] >= 1


def test_submit_uses_filename_when_job_name_empty(client, db_session):
    r = _submit(client, job_name="", filename="arabidopsis.fna")
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    job = db_session.query(AnalysisJob).filter_by(id=job_id).first()
    # job_name should fall back to filename without extension
    assert job.job_name == "arabidopsis"


def test_submit_uses_provided_job_name(client, db_session):
    r = _submit(client, job_name="CustomName", filename="arabidopsis.fna")
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    job = db_session.query(AnalysisJob).filter_by(id=job_id).first()
    assert job.job_name == "CustomName"


def test_submit_rejects_unsupported_extension(client):
    r = client.post("/api/v1/analyze", data={
        "email": "user@test.com", "job_name": "", "input_type": "genome_dna",
        "run_mode": "predict_bgc", "use_for_training": False,
    }, files=[("file", ("genome.txt", io.BytesIO(b"data"), "text/plain"))])
    assert r.status_code == 400
    assert "Unsupported file type" in r.json()["detail"]


def test_submit_rejects_invalid_input_type(client):
    r = client.post("/api/v1/analyze", data={
        "email": "user@test.com", "job_name": "", "input_type": "INVALID",
        "run_mode": "predict_bgc", "use_for_training": False,
    }, files=[_fna_file()])
    assert r.status_code == 400


def test_submit_rejects_invalid_run_mode(client):
    r = client.post("/api/v1/analyze", data={
        "email": "user@test.com", "job_name": "", "input_type": "genome_dna",
        "run_mode": "prepare_only", "use_for_training": False,
    }, files=[_fna_file()])
    assert r.status_code == 400


def test_submit_rejects_missing_email(client):
    r = client.post("/api/v1/analyze", data={
        "job_name": "", "input_type": "genome_dna",
        "run_mode": "predict_bgc", "use_for_training": False,
    }, files=[_fna_file()])
    assert r.status_code == 422


def test_submit_queue_position_increments(client):
    r1 = _submit(client, email="a@test.com")
    r2 = _submit(client, email="b@test.com")
    assert r2.json()["queue_position"] > r1.json()["queue_position"]


def test_submit_file_saved_to_disk(client, db_session):
    r = _submit(client, filename="sample.fna")
    job_id = r.json()["job_id"]
    job = db_session.query(AnalysisJob).filter_by(id=job_id).first()
    assert job is not None
    assert os.path.isfile(job.input_file_path)
    assert job.input_file_path.endswith("sample.fna")


def test_submit_training_copy_created(client, db_session):
    r = client.post("/api/v1/analyze", data={
        "email": "user@test.com", "job_name": "", "input_type": "genome_dna",
        "run_mode": "predict_bgc", "use_for_training": True,
    }, files=[_fna_file("train.fna")])
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    job = db_session.query(AnalysisJob).filter_by(id=job_id).first()
    # Training copy lives alongside the raw file with the same filename
    training_path = job.input_file_path.replace("/raw/", "/training/")
    assert os.path.isfile(training_path)


# ── Download endpoint ─────────────────────────────────────────────────────────

def _make_complete_job(db_session, tmp_path, files):
    """Insert a COMPLETE job record and populate its output directory."""
    job_id = uuid.uuid4()
    output_dir = tmp_path / "results" / str(job_id)
    output_dir.mkdir(parents=True)

    for fname, content in files.items():
        (output_dir / fname).write_bytes(content)

    job = AnalysisJob(
        id=job_id,
        user_email="user@test.com",
        job_name="TestJob",
        input_filename="genome.fna",
        input_file_path=str(tmp_path / "raw" / "genome.fna"),
        input_type="genome_dna",
        run_mode="predict_bgc",
        status="COMPLETE",
        output_file_path=str(output_dir),
    )
    db_session.add(job)
    db_session.commit()
    return str(job_id)


def test_download_returns_zip(client, db_session, tmp_path):
    job_id = _make_complete_job(db_session, tmp_path, {
        "result.bgc.tsv": b"col1\tcol2\n",
        "result.bgc.gbk": b"LOCUS ...",
    })
    r = client.get(f"/api/v1/jobs/{job_id}/download")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"


def test_download_excludes_full_gbk(client, db_session, tmp_path):
    job_id = _make_complete_job(db_session, tmp_path, {
        "result.full.gbk":  b"FULL GBK DATA",
        "result.bgc.gbk":   b"BGC GBK DATA",
        "result.bgc.tsv":   b"tsv data",
    })
    r = client.get(f"/api/v1/jobs/{job_id}/download")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
    assert not any(n.endswith(".full.gbk") for n in names)
    assert any(n.endswith(".bgc.gbk") for n in names)


def test_download_only_includes_allowed_extensions(client, db_session, tmp_path):
    job_id = _make_complete_job(db_session, tmp_path, {
        "result.bgc.tsv":  b"tsv",
        "result.bgc.gbk":  b"gbk",
        "result.json":     b"{}",
        "LOG.txt":         b"log data",       # .txt — should be excluded
        "result.fna":      b">seq\nATCG",     # .fna — should be excluded
    })
    r = client.get(f"/api/v1/jobs/{job_id}/download")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
    assert "LOG.txt" not in names
    assert "result.fna" not in names
    assert "result.bgc.tsv" in names
    assert "result.bgc.gbk" in names
    assert "result.json" in names


def test_download_404_for_unknown_job(client):
    r = client.get(f"/api/v1/jobs/{uuid.uuid4()}/download")
    assert r.status_code == 404


def test_download_400_for_pending_job(client, db_session):
    job_id = uuid.uuid4()
    db_session.add(AnalysisJob(
        id=job_id, user_email="u@test.com", job_name="J",
        input_filename="g.fna", input_file_path="/tmp/g.fna",
        status="PENDING",
    ))
    db_session.commit()
    r = client.get(f"/api/v1/jobs/{job_id}/download")
    assert r.status_code == 400


def test_download_404_when_output_dir_missing(client, db_session, tmp_path):
    job_id = uuid.uuid4()
    db_session.add(AnalysisJob(
        id=job_id, user_email="u@test.com", job_name="J",
        input_filename="g.fna", input_file_path="/tmp/g.fna",
        status="COMPLETE",
        output_file_path="/nonexistent/path",
    ))
    db_session.commit()
    r = client.get(f"/api/v1/jobs/{job_id}/download")
    assert r.status_code == 404


def test_download_404_when_output_dir_empty(client, db_session, tmp_path):
    job_id = _make_complete_job(db_session, tmp_path, {})
    r = client.get(f"/api/v1/jobs/{job_id}/download")
    assert r.status_code == 404
