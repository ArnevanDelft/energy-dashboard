# energy-dashboard

Web dashboard for the per-device energy disaggregation. Runs as a single
Docker container on the Synology, reads Home Assistant data straight from
InfluxDB, recomputes the breakdown on a timer, and shows:

- **Live power** — house consumption, solar, grid import/export (updates every 5 s)
- **Device energy breakdown** — kWh per device over the last N days (donut + table)
- **Recognized via fingerprints** — devices found in the “other” remainder without a plug
- **Fingerprint library** — running watts, duty cycle, cycles/day and the cycle-shape curve per device

It depends on the [ha-energy-analytics](../ha-energy-analytics) package for all
the heavy lifting.

## Run on Synology

```sh
git clone https://github.com/ArnevanDelft/energy-dashboard.git
cd energy-dashboard
cp .env.example .env          # edit if needed
# put your fingerprint JSONs where FINGERPRINT_HOST_DIR points (default ./fingerprints)
docker compose up -d --build
```

Open `http://<synology>:8088`. To update later:

```sh
./update.sh
```

`update.sh` does `git pull`, rebuilds (re-pulling the latest analytics package
from GitHub), and restarts the container.

## Local development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ../ha-energy-analytics fastapi "uvicorn[standard]"
export INFLUX_USERNAME="" ENERGY_FINGERPRINT_DIR=../ha-energy-analytics/fingerprints
uvicorn app.main:app --reload --port 8088
```

## Configuration

All via environment (see `.env.example`): `INFLUX_*` for the data source,
`DASHBOARD_DAYS` for the window, `DASHBOARD_REFRESH_MINUTES` for the recompute
cadence, and `ENERGY_FINGERPRINT_DIR` for the shared fingerprint store.

## Endpoints

| Path | Purpose |
|---|---|
| `/` | dashboard UI |
| `/api/state` | cached snapshot (breakdown, recognized, fingerprints); `503` while warming up |
| `/api/live` | latest consumption / solar / grid |
| `/api/healthz` | liveness + whether a snapshot exists |

## Fingerprints

The dashboard only **reads** fingerprints. Generate them from the calibration
host with the package CLI:

```sh
energy-analysis --source influx --days 7 --save-fingerprint
```

and make that directory available to the container (the `FINGERPRINT_HOST_DIR`
volume). If you run calibration on the Synology too, point both at the same
shared folder.
