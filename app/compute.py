"""Run the disaggregation pipeline and shape the results for the dashboard.

The heavy work (breakdown + fingerprint matching over a multi-day window) is
done once per refresh cycle and cached by main.py. Live power figures are
cheap and fetched separately on demand.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pandas as pd

from energy_analytics import config, decompose, disaggregate, fingerprint, matcher, report
from energy_analytics.loader import InfluxLoader

# Selectable periods: key -> (label, days, grid). The grid stays fine for
# short windows (full spike/cycle detection) and coarsens for long ones so
# InfluxDB downsamples to a few thousand points instead of millions. Energy
# totals stay accurate; only fine-grained detection degrades on long windows.
PERIODS: dict[str, tuple[str, float, str]] = {
    "1u":  ("laatste uur",     1 / 24, "30s"),
    "6u":  ("laatste 6 uur",   0.25,   "30s"),
    "24u": ("laatste 24 uur",  1,      "60s"),
    "7d":  ("laatste 7 dagen", 7,      "60s"),
    "30d": ("laatste 30 dagen", 30,    "300s"),
    "90d": ("laatste 90 dagen", 90,    "1h"),
    "1j":  ("laatste jaar",    365,    "3h"),
}
# Human-readable grid for the UI.
_GRID_LABEL = {"30s": "30 sec", "60s": "1 min", "120s": "2 min",
               "300s": "5 min", "900s": "15 min", "1h": "1 uur", "3h": "3 uur"}
DEFAULT_PERIOD = os.environ.get("DASHBOARD_PERIOD", "7d")
# Pseudo-rows breakdown_kwh appends that are not real devices.
_PSEUDO_ROWS = {"— TOTAL consumption —", "(solar produced)"}


def resolve_period(key: str | None) -> str:
    return key if key in PERIODS else DEFAULT_PERIOD


def _loader() -> InfluxLoader:
    return InfluxLoader.from_env()


def compute_snapshot(period_key: str | None = None) -> dict:
    """Full recompute for a period: breakdown, recognised devices, library."""
    key = resolve_period(period_key)
    label, days, freq = PERIODS[key]
    loader_obj = _loader()
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(days=days)

    frame = decompose.build_power_frame(loader_obj, start, end, freq)
    frame = disaggregate.disaggregate(frame, freq)

    bk = report.breakdown_kwh(frame, freq)
    total_cons = float(bk.loc["— TOTAL consumption —", "kWh"])
    solar = float(bk.loc["(solar produced)", "kWh"])
    breakdown = [
        {"name": name, "kwh": float(row["kWh"]),
         "pct": None if pd.isna(row["%_of_consumption"]) else float(row["%_of_consumption"])}
        for name, row in bk.iterrows()
        if name not in _PSEUDO_ROWS and float(row["kWh"]) > 0.0005
    ]

    matches = matcher.match(frame["other"], freq)
    recognized = [
        {"device": dev, "matched_cycles": int(r["matched_cycles"]),
         "kwh": float(r["kwh"]), "mean_score": float(r["mean_score"])}
        for dev, r in matches.iterrows()
    ]
    other_kwh = next((b["kwh"] for b in breakdown if b["name"].startswith("Other")), 0.0)

    fingerprints = _fingerprint_cards()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "period": {"key": key, "label": label, "days": days,
                   "resolution": _GRID_LABEL.get(freq, freq),
                   "coarse": days >= 30},
        "window": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "totals": {"consumption_kwh": round(total_cons, 2),
                   "solar_kwh": round(solar, 2),
                   "other_kwh": round(other_kwh, 2),
                   "recognized_in_other_kwh": round(sum(r["kwh"] for r in recognized), 2)},
        "breakdown": breakdown,
        "recognized": recognized,
        "fingerprints": fingerprints,
    }


def _fingerprint_cards() -> list[dict]:
    cards = []
    for dev, fp in sorted(fingerprint.load_all().items()):
        sc = fp.get("scalar", {})
        cy = fp.get("cycles", {})
        cards.append({
            "device": dev,
            "entity": fp.get("entity"),
            "running_w": sc.get("running_w"),
            "standby_w": sc.get("standby_w"),
            "duty_cycle": sc.get("duty_cycle"),
            "kwh_per_day": sc.get("kwh_per_day"),
            "cycles_per_day": cy.get("per_day"),
            "on_duration_h": (cy.get("on_duration_h") or {}).get("median"),
            "shape_w": cy.get("shape_w") or [],
            "per_state_w": fp.get("per_state_w"),
            "period": fp.get("period"),
            "history_count": len(fp.get("history", [])),
        })
    return cards


def discover_plugs() -> list[str]:
    """All power (W) sensors in InfluxDB, as candidate plug entities."""
    loader_obj = _loader()
    q = 'SHOW TAG VALUES FROM "W" WITH KEY = "entity_id"'
    resp = loader_obj.session.get(
        loader_obj.url, params={**loader_obj.params, "q": q}, timeout=30)
    resp.raise_for_status()
    series = resp.json().get("results", [{}])[0].get("series", [])
    oids = {row[1] for s in series for row in s.get("values", [])}
    return sorted(f"sensor.{o}" for o in oids)


def live_power() -> dict:
    """Cheap latest-value read: house consumption, solar, grid net."""
    loader_obj = _loader()
    end = pd.Timestamp.now(tz="UTC")
    start = end - pd.Timedelta(minutes=10)

    def last(series):
        s = series.dropna()
        return float(s.iloc[-1]) if len(s) else 0.0

    grid = last(loader_obj.load(config.GRID_POWER, start, end))
    solar = 0.0
    for eid in config.SOLAR_POWER:
        solar += last(loader_obj.load(eid, start, end))
    consumption = grid + solar
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "consumption_w": round(consumption),
        "solar_w": round(solar),
        "grid_w": round(grid),
        "importing": grid > 0,
    }
