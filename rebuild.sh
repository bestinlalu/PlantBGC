#!/bin/bash
set -e  # Exit immediately if any command fails

echo "==> Stopping and removing existing containers and volumes..."
sudo docker compose down -v

echo "==> Building all images (no cache)..."
sudo docker compose build # --no-cache

echo "==> Starting all services with 2 bgc_workers..."
sudo docker compose up -d --scale bgc_worker=2

echo "==> Running containers:"
sudo docker compose ps

echo ""
echo "Done! Run 'docker compose logs -f' to follow logs."
