"""FastAPI application: REST API + live WebSocket + static SPA serving."""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .poller import Poller
from .store import Store, resolve_db_path

DB_PATH = resolve_db_path(os.environ.get("WIFI_PRESENCE_DB"))
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

# Settings keys that must never be returned to the client.
_SECRET_KEYS = {"router_password"}


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self.active.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self.active.discard(ws)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self.active)
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                await self.disconnect(ws)


store = Store(DB_PATH)
manager = ConnectionManager()
poller = Poller(store, manager.broadcast)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await poller.start()
    try:
        yield
    finally:
        await poller.stop()
        store.close()


app = FastAPI(title="WiFi Presence Monitor", lifespan=lifespan)


# ---- models --------------------------------------------------------------
class PersonIn(BaseModel):
    name: str


class DevicePatch(BaseModel):
    label: Optional[str] = None
    person_id: Optional[int] = None
    ignored: Optional[bool] = None
    unassign: bool = False  # explicit clear of person_id


class SettingsIn(BaseModel):
    router_host: Optional[str] = None
    router_port: Optional[int] = None
    router_user: Optional[str] = None
    router_password: Optional[str] = None
    router_key_path: Optional[str] = None
    poll_interval: Optional[int] = None
    grace_minutes: Optional[int] = None
    cmd_ifnames: Optional[str] = None
    cmd_assoclist: Optional[str] = None
    cmd_neigh: Optional[str] = None
    cmd_leases: Optional[str] = None
    cmd_fdb: Optional[str] = None


def _redact(settings: dict[str, Any]) -> dict[str, Any]:
    out = dict(settings)
    for k in _SECRET_KEYS:
        out[k] = "********" if out.get(k) else ""
    return out


# ---- presence state ------------------------------------------------------
@app.get("/api/state")
def get_state() -> dict[str, Any]:
    return poller.current_state()


@app.websocket("/api/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        await ws.send_json(poller.current_state())  # immediate snapshot
        while True:
            await ws.receive_text()  # keep the socket open; ignore input
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception:
        await manager.disconnect(ws)


# ---- devices -------------------------------------------------------------
@app.get("/api/devices")
def list_devices() -> list[dict[str, Any]]:
    return store.list_devices()


@app.patch("/api/devices/{mac}")
def patch_device(mac: str, patch: DevicePatch) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if patch.label is not None:
        fields["label"] = patch.label
    if patch.ignored is not None:
        fields["ignored"] = patch.ignored
    if patch.unassign:
        fields["person_id"] = None
    elif patch.person_id is not None:
        fields["person_id"] = patch.person_id
    device = store.update_device(mac, fields)
    if device is None:
        raise HTTPException(404, "device not found")
    return device


# ---- people --------------------------------------------------------------
@app.get("/api/people")
def list_people() -> list[dict[str, Any]]:
    return store.list_people()


@app.post("/api/people")
def create_person(person: PersonIn) -> dict[str, Any]:
    return store.create_person(person.name)


@app.patch("/api/people/{person_id}")
def rename_person(person_id: int, person: PersonIn) -> dict[str, Any]:
    updated = store.rename_person(person_id, person.name)
    if updated is None:
        raise HTTPException(404, "person not found")
    return updated


@app.delete("/api/people/{person_id}")
def delete_person(person_id: int) -> dict[str, str]:
    store.delete_person(person_id)
    return {"status": "deleted"}


# ---- settings ------------------------------------------------------------
@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    return _redact(store.get_settings())


@app.put("/api/settings")
def put_settings(settings: SettingsIn) -> dict[str, Any]:
    updates = {k: v for k, v in settings.model_dump().items() if v is not None}
    # Never store the redaction placeholder back as the real password.
    if updates.get("router_password") == "********":
        updates.pop("router_password")
    store.update_settings(updates)
    poller.reload_router_settings()
    return _redact(store.get_settings())


@app.post("/api/router/test")
def test_router() -> dict[str, Any]:
    poller.reload_router_settings()
    return poller.router.test_connection()


# ---- static SPA ----------------------------------------------------------
if FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
