# energy-dashboard

Web dashboard for the per-device energy disaggregation. Runs as a single
Docker container on the Synology, reads Home Assistant data straight from
InfluxDB, recomputes the breakdown on a timer, and shows:

- **Live power** — house consumption, solar, grid import/export (updates every 5 s)
- **Device energy breakdown** — kWh per device over the last N days (donut + table)
- **Recognized via fingerprints** — devices found in the “other” remainder without a plug
- **Fingerprint library** — running watts, duty cycle, cycles/day and the cycle-shape curve per device
- **Devices & plug assignments** — create a device and couple the metering plug
  to it for the period it was attached, straight from the UI (no code edits)

It depends on the [ha-energy-analytics](../ha-energy-analytics) package for all
the heavy lifting.

## Run on Synology

```sh
git clone https://github.com/ArnevanDelft/energy-dashboard.git
cd energy-dashboard
cp .env.example .env          # edit if needed
docker compose up -d --build
```

All runtime data (fingerprint JSONs under `fingerprints/`, and the editable
`assignments.json`) lives in the writable `./data` volume (`DATA_HOST_DIR`).

Open `http://<synology>:8088`. To update later:

```sh
./update.sh
```

`update.sh` does `git pull`, rebuilds (forcing a refresh of the
`ha-energy-analytics` package layer via a `CACHEBUST` build-arg), and restarts
the container. **Always update via `./update.sh`** — a plain
`docker compose build` would reuse the cached, possibly stale, package layer.
If you ever rebuild by hand after a package change, use
`docker compose build --no-cache`.

## Local development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -e ../ha-energy-analytics fastapi "uvicorn[standard]"
mkdir -p data/fingerprints
export INFLUX_USERNAME="" \
  ENERGY_FINGERPRINT_DIR=$PWD/data/fingerprints \
  ENERGY_ASSIGNMENTS_FILE=$PWD/data/assignments.json
uvicorn app.main:app --reload --port 8088
```

## Configuration

All via environment (see `.env.example`): `INFLUX_*` for the data source,
`DASHBOARD_DAYS` for the window, `DASHBOARD_REFRESH_MINUTES` for the recompute
cadence, and `ENERGY_FINGERPRINT_DIR` / `ENERGY_ASSIGNMENTS_FILE` for the shared
writable data store.

> The write endpoints (plug assignments) are **unauthenticated** — fine on a
> trusted LAN; don't expose the dashboard to the internet without a proxy/auth.

## Endpoints

| Path | Purpose |
|---|---|
| `/` | dashboard UI |
| `/api/state` | cached snapshot (breakdown, recognized, fingerprints); `503` while warming up |
| `/api/live` | latest consumption / solar / grid |
| `/api/plugs` | power (W) sensors discovered in InfluxDB (for the assignment form) |
| `/api/assignments` | GET list · POST create · PATCH `{end}` · DELETE — manage plug↔device couplings |
| `/api/healthz` | liveness + whether a snapshot exists |

## Fingerprints

The dashboard only **reads** fingerprints (its volume is mounted read-only).
The easiest way to generate them on the Synology is `calibrate.sh`, which runs
a throwaway container from the dashboard image with the fingerprint folder
mounted **writable**:

```sh
./calibrate.sh           # calibrate over the last 7 days
./calibrate.sh 14        # ... or 14
```

It writes (e.g.) `data/fingerprints/fridge.json` straight into the folder the
dashboard reads, so the device shows up after the next snapshot refresh. No
extra Python install is needed — it reuses the image and your `.env`.

Schedule it weekly in **Synology Task Scheduler** (user-defined script):

```sh
sh /volume1/path/to/energy-dashboard/calibrate.sh
```

You can also run the CLI directly anywhere the package is installed:

```sh
energy-analysis --source influx --days 7 --save-fingerprint
```
