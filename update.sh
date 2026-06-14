#!/usr/bin/env sh
# Pull the latest dashboard, rebuild the image (picking up any new version of
# the ha-energy-analytics package from GitHub), and restart the container.
# Run this on the Synology, e.g. via Task Scheduler or by hand.
set -eu

cd "$(dirname "$0")"

echo "==> git pull"
git pull --ff-only

echo "==> docker compose build (refreshing the analytics package layer)"
# CACHEBUST forces the (small) ha-energy-analytics install to re-run so a new
# version of the package is always picked up; base deps stay cached.
docker compose build --pull --build-arg CACHEBUST="$(date +%s)"

echo "==> docker compose up -d"
docker compose up -d

echo "==> pruning dangling images"
docker image prune -f >/dev/null 2>&1 || true

echo "Done. Dashboard: http://<synology>:${DASHBOARD_PORT:-8088}"
