# PlantBGC Web Service

A web service wrapper around [PlantBGC](https://github.com/Yuhanzhao-233/PlantBGC) — a Transformer-based framework for predicting Biosynthetic Gene Clusters (BGCs) in plant genomes.

## Architecture

| Component | Description |
|-----------|-------------|
| `bgc_web` | FastAPI web server (Python 3.12) — serves the UI and REST API |
| `bgc_worker` | Analysis worker (Python 3.7) — polls the DB and runs plantbgc |
| `postgres` | PostgreSQL 15 — job queue and metadata store |

Uploaded files and results are stored in `/PlantBGC/uploads/` on the host, bind-mounted into both containers at `/app/shared_uploads`.

## Public URL

The service is accessible at **https://plantbgc.csc.ncsu.edu**

Traffic flows: `User → CSC proxy (port 443) → lin-zguo32-01:8000 → bgc_web container`

Port 8000 on the server is firewalled — only the CSC proxy IPs can reach it directly.

> **Note:** Large result downloads (up to ~256 MB) go through the proxy. If downloads time out, ask the sysadmin to increase the proxy timeout and max response size.

## Prerequisites

- Docker with Compose plugin
- A `.env` file in the repo root (never committed):

```
SMTP_USER=bestinlalu@gmail.com
SMTP_PASSWORD=<gmail-app-password>
```

To create a Gmail App Password: Google Account → Security → 2-Step Verification → App Passwords.

## Deployment

### First-time setup (on the VM)

```bash
cd /PlantBGC
git clone https://github.com/bestinlalu/PlantBGC.git repo
cd repo
cp .env.example .env      # then fill in SMTP_PASSWORD
sudo mkdir -p /PlantBGC/uploads/raw /PlantBGC/uploads/results /PlantBGC/uploads/training
sudo chmod -R 755 /PlantBGC/uploads
sudo ./deploy.sh
```

### Redeploy (production-safe)

Rebuilds images and recreates containers without touching volumes or killing in-progress jobs. Workers finish their current job before the new image takes over.

```bash
sudo ./deploy.sh
```

### Full reset (dev only — destroys all data)

```bash
sudo ./rebuild.sh
```

> ⚠️ This runs `docker compose down -v` — all database records and uploaded files are lost.

## Running Tests

Tests run inside Docker against a real Postgres instance. The test container stops automatically after the run.

```bash
sudo docker compose --profile test run --rm test
```

### What is tested

| File | Coverage |
|------|----------|
| `tests/test_api.py` | Homepage, job submission validation, file saving, queue position, download zip filtering |
| `tests/test_email_utils.py` | All email functions, attachments, admin failure email |
| `tests/test_bgc_runner.py` | Command building, job status transitions, admin email on failure |

## API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Web UI |
| `POST` | `/api/v1/analyze` | Submit a genome analysis job |
| `GET` | `/api/v1/jobs/{job_id}/download` | Download results as a ZIP |

### POST `/api/v1/analyze`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `email` | string | yes | Notification email address |
| `job_name` | string | no | Human-readable name (defaults to filename) |
| `file` | file | yes | Genome file (`.fna`, `.fa`, `.fasta`, `.gbk`, `.gbff`) |
| `input_type` | string | no | `genome_dna` (default), `cds_nucleotide`, `protein_fasta` |
| `use_for_training` | bool | no | Contribute file to future model training |

### Download ZIP contents

Only the following file types are included in the download:

| File | Description |
|------|-------------|
| `*.bgc.tsv` | BGC prediction table with locus coordinates and scores |
| `*.pfam.tsv` | Per-protein Pfam domain annotation |
| `*.bgc.gbk` | GenBank file filtered to BGC candidate regions |
| `*.json` | Structured prediction output |

`*.full.gbk` is excluded (too large — hundreds of MB).

## Email Notifications

Users receive three emails per job:

1. **Queued** — confirms submission and queue position
2. **Started** — notifies when processing begins
3. **Complete / Failed** — includes download link on success

On failure, the admin (`SMTP_USER`) also receives an email with `LOG.txt` and the input file attached.

## Contact

- Bestin Lalu — blalu@ncsu.edu
- Yuhan Zhao — yzhao66@ncsu.edu
