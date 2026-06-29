#!/bin/bash
set -e  # Exit immediately if any command fails

# Production-safe redeploy: rebuilds images and recreates containers
# WITHOUT touching volumes (postgres_data, uploads), and WITHOUT killing
# in-progress jobs. Use this instead of rebuild.sh whenever there are jobs
# in the database / running analyses you don't want to lose.
#
# How it stays safe:
#   - No `down -v` — volumes (postgres_data, uploads) are never touched.
#   - bgc_worker has stop_grace_period: 12h in docker-compose.yml, and
#     bgc_runner.py catches SIGTERM to stop claiming new jobs while letting
#     the current one finish. `docker compose up` will wait for that exit
#     before starting the replacement container with the new image.
#   - bgc_web is stateless, so a few seconds of downtime while it restarts
#     is fine — in-flight uploads will just need to be retried by the client.

echo "==> Building updated images..."
docker compose build

echo "==> Recreating services with new images (old workers finish current jobs first)..."
docker compose up -d --scale bgc_worker=2

echo "==> Running containers:"
docker compose ps

echo ""
echo "Done! Run 'docker compose logs -f' to follow logs."
