"""FastAPI dashboard backend.

Recomputes the disaggregation snapshot on a timer (and immediately after any
plug-assignment edit) and serves it, plus a cheap live-power endpoint and a
small CRUD API for managing devices / plug assignments, to the static frontend.
"""

from __future__ import annotations

import asyncio
import os
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from energy_analytics import assignments

from . import compute

REFRESH_MINUTES = float(os.environ.get("DASHBOARD_REFRESH_MINUTES", "15"))
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Energy Dashboard")

# Cached snapshot shared across requests.
_state: dict = {"snapshot": None, "error": None}
_recompute_lock = asyncio.Lock()


async def _recompute():
    """Recompute the snapshot and update the cache (serialised)."""
    async with _recompute_lock:
        try:
            snap = await asyncio.to_thread(compute.compute_snapshot)
            _state["snapshot"] = snap
            _state["error"] = None
        except Exception:  # noqa: BLE001 - surface any failure to the UI
            _state["error"] = traceback.format_exc(limit=3)


async def _refresh_loop():
    while True:
        await _recompute()
        await asyncio.sleep(REFRESH_MINUTES * 60)


@app.on_event("startup")
async def _startup():
    # Migrate the config seed into the editable store on first run.
    assignments.ensure_seeded()
    asyncio.create_task(_refresh_loop())


# --- read endpoints --------------------------------------------------------

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


@app.get("/api/plugs")
async def api_plugs():
    try:
        return {"plugs": await asyncio.to_thread(compute.discover_plugs)}
    except Exception as err:  # noqa: BLE001
        return JSONResponse({"error": str(err)}, status_code=502)


@app.get("/api/healthz")
async def healthz():
    return {"ok": True, "has_snapshot": _state["snapshot"] is not None}


# --- assignment CRUD -------------------------------------------------------

class AssignmentIn(BaseModel):
    plug: str
    device: str
    start: str
    end: str | None = None


class AssignmentPatch(BaseModel):
    end: str | None = None


@app.get("/api/assignments")
async def api_assignments():
    return {"assignments": assignments.load()}


@app.post("/api/assignments")
async def api_assignment_create(body: AssignmentIn):
    try:
        item = assignments.add(body.plug, body.device, body.start, body.end)
    except (ValueError, KeyError) as err:
        raise HTTPException(status_code=400, detail=str(err))
    await _recompute()
    return item


@app.patch("/api/assignments/{assignment_id}")
async def api_assignment_update(assignment_id: str, body: AssignmentPatch):
    item = assignments.update(assignment_id, end=body.end)
    if item is None:
        raise HTTPException(status_code=404, detail="assignment not found")
    await _recompute()
    return item


@app.delete("/api/assignments/{assignment_id}")
async def api_assignment_delete(assignment_id: str):
    if not assignments.delete(assignment_id):
        raise HTTPException(status_code=404, detail="assignment not found")
    await _recompute()
    return {"deleted": assignment_id}


# Frontend (index.html etc.) at the root.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
