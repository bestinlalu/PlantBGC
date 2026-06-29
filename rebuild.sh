#!/bin/bash
set -e  # Exit immediately if any command fails

echo "==> Stopping and removing existing containers and volumes..."
docker compose down -v

echo "==> Building all images (no cache)..."
docker compose build # --no-cache

echo "==> Starting all services with 2 bgc_workers..."
docker compose up -d --scale bgc_worker=2

echo "==> Running containers:"
docker compose ps

echo ""
echo "Done! Run 'docker compose logs -f' to follow logs."
