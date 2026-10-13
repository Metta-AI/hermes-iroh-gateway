"""
dashboard/plugin_api.py — control-plane backend for the hermes-iroh-gateway
plugin. Mounted (by the dashboard/desktop backend host) under
`/api/plugins/hermes-iroh-gateway/`.

This is the CONTROL plane (start/stop/status/upload). The gateway it
controls — the actual "iroh http gateway" that serves blobs by hash over
HTTP — is a second, independent FastAPI/uvicorn server that GatewayManager
starts on its own configurable host:port (see gateway_manager.py).

Must export a module-level `router = APIRouter()` — that's the only
contract the host checks (see Hermes docs: Extending the Dashboard).
"""
import asyncio
import json
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

# Same sys.path bootstrap as tools.py, and for the same reason: this file is
# loaded by a totally different import mechanism than the agent-plugin half
# (__init__.py / tools.py), so without this, `import gateway_manager` here
# could resolve to a second, disconnected module+singleton instead of the
# one the agent tools are driving. Plugin root is two levels up from this
# file (dashboard/plugin_api.py -> plugin root).
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from gateway_manager import manager  # noqa: E402

router = APIRouter()


@router.get("/status")
def get_status():
    return manager.status()


@router.post("/start")
def start():
    try:
        return manager.start()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop")
def stop():
    return manager.stop()


@router.post("/restart")
def restart():
    try:
        return manager.restart()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/config")
def get_config():
    return manager.config.__dict__


@router.post("/config")
async def set_config(request: Request):
    body = await request.json()
    return manager.configure(
        host=body.get("host"), port=body.get("port"), data_dir=body.get("data_dir")
    )


@router.get("/blobs")
def list_blobs():
    return manager.list_blobs()


@router.post("/blobs")
async def upload_blob(request: Request):
    """Raw-bytes upload — for curl/scripts: `curl --data-binary @file ...`."""
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="empty body")
    try:
        return manager.put_bytes(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/blobs/text")
async def upload_text_blob(request: Request):
    """JSON upload — what the desktop pane's textarea uses: {"text": "..."}."""
    body = await request.json()
    text = body.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    try:
        return manager.put_bytes(text.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/blobs/{hash_hex}")
def get_blob(hash_hex: str):
    try:
        data = manager.get_bytes(hash_hex)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))
    if data is None:
        raise HTTPException(status_code=404, detail="blob not found")
    return Response(content=data, media_type="application/octet-stream")


@router.websocket("/events")
async def events_ws(websocket):
    """Live status push for ctx.socket — polls the manager every 2s and
    pushes on change (and at least once every 10s as a heartbeat), since
    GatewayManager has no internal pubsub of its own."""
    await websocket.accept()
    last_payload = None
    last_sent = 0.0
    try:
        while True:
            st = manager.status()
            payload = json.dumps(st, sort_keys=True)
            now = asyncio.get_event_loop().time()
            if payload != last_payload or (now - last_sent) > 10:
                await websocket.send_json(st)
                last_payload = payload
                last_sent = now
            await asyncio.sleep(2)
    except Exception:  # noqa: BLE001
        # Client disconnected or socket error — just stop pushing.
        return
