#!/usr/bin/env sh
# Run the roaming-plug calibration and write the device fingerprint straight
# into the dashboard's fingerprint store. Reuses the dashboard image (which
# already has the ha-energy-analytics package and InfluxDB access), so nothing
# extra needs installing on the Synology.
#
# Usage:
#   ./calibrate.sh           # last 7 days
#   ./calibrate.sh 14        # last 14 days
#
# Schedule it weekly via Synology Task Scheduler (user-defined script):
#   sh /volume1/.../energy-dashboard/calibrate.sh
set -eu

cd "$(dirname "$0")"

# Pull INFLUX_* and FINGERPRINT_HOST_DIR from the same .env the dashboard uses.
set -a
. ./.env
set +a

DAYS="${1:-7}"
DATA_DIR="${DATA_HOST_DIR:-./data}"
mkdir -p "$DATA_DIR/fingerprints"

echo "==> calibrating over the last ${DAYS} days, writing to ${DATA_DIR}/fingerprints"
docker run --rm \
  --env-file .env \
  -e ENERGY_FINGERPRINT_DIR=/data/fingerprints \
  -e ENERGY_ASSIGNMENTS_FILE=/data/assignments.json \
  -v "$(cd "$DATA_DIR" && pwd):/data" \
  energy-dashboard:latest \
  energy-analysis --source influx --days "$DAYS" --calibrate --save-fingerprint

echo "==> done. Current fingerprints:"
ls -1 "$DATA_DIR/fingerprints"
