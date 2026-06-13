"""FastAPI dashboard backend.

Recomputes the disaggregation snapshot on a timer and serves it (plus a cheap
live-power endpoint) to the static frontend.
"""

from __future__ import annotations

import asyncio
import os
import traceback
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import compute

REFRESH_MINUTES = float(os.environ.get("DASHBOARD_REFRESH_MINUTES", "15"))
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Energy Dashboard")

# Cached snapshot shared across requests.
_state: dict = {"snapshot": None, "error": None}


async def _refresh_loop():
    while True:
        try:
            # compute_snapshot is blocking (pandas/HTTP); keep the loop responsive.
            snap = await asyncio.to_thread(compute.compute_snapshot)
            _state["snapshot"] = snap
            _state["error"] = None
        except Exception:  # noqa: BLE001 - surface any failure to the UI
            _state["error"] = traceback.format_exc(limit=3)
        await asyncio.sleep(REFRESH_MINUTES * 60)


@app.on_event("startup")
async def _startup():
    asyncio.create_task(_refresh_loop())


@app.get("/api/state")
async def api_state():
    if _state["snapshot"] is None:
        return JSONResponse(
            {"status": "warming_up", "error": _state["error"]}, status_code=503)
    return _state["snapshot"]


@app.get("/api/live")
async def api_live():
    try:
        return await asyncio.to_thread(compute.live_power)
    except Exception as err:  # noqa: BLE001
        return JSONResponse({"error": str(err)}, status_code=502)


@app.get("/api/healthz")
async def healthz():
    return {"ok": True, "has_snapshot": _state["snapshot"] is not None}


# Frontend (index.html etc.) at the root.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
