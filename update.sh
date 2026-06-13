#!/usr/bin/env sh
# Pull the latest dashboard, rebuild the image (picking up any new version of
# the ha-energy-analytics package from GitHub), and restart the container.
# Run this on the Synology, e.g. via Task Scheduler or by hand.
set -eu

cd "$(dirname "$0")"

echo "==> git pull"
git pull --ff-only

echo "==> docker compose build (no cache for the package layer)"
docker compose build --pull

echo "==> docker compose up -d"
docker compose up -d

echo "==> pruning dangling images"
docker image prune -f >/dev/null 2>&1 || true

echo "Done. Dashboard: http://<synology>:${DASHBOARD_PORT:-8088}"
