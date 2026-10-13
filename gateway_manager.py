"""
gateway_manager.py — shared singleton that owns the iroh node and the
embedded HTTP gateway that serves its blobs by hash.

Imported by BOTH halves of the plugin:
  - __init__.py (agent-side tools, run in the Hermes gateway process)
  - dashboard/plugin_api.py (desktop control-plane backend, FastAPI)
so they always observe/drive the same running node — there is exactly one
GatewayManager instance per Hermes process (module-level singleton below).

Design notes
-------------
The iroh Python bindings (iroh-ffi, uniffi-rs) are async. Tool handlers in
the agent-plugin API are synchronous (`def handler(args: dict) -> str`), and
FastAPI route handlers in this codebase are written as plain `def` (FastAPI
runs sync routes in its threadpool automatically) so neither caller needs to
be async-aware. To bridge that, this module runs its OWN dedicated asyncio
event loop in a background thread — a small actor — and every public method
is a plain blocking call that round-trips through that loop via
`asyncio.run_coroutine_threadsafe`. This also decouples the iroh node's
lifecycle from whatever event loop happens to be running the Hermes gateway
or dashboard process, which matters because this manager starts a SECOND,
independent uvicorn HTTP server (the actual "iroh http gateway", on its own
host:port) in addition to Hermes's own web server.

Verified against the real installed `iroh` package (not guessed):
  pip install iroh==0.35.0
  iroh.Iroh.persistent(path)         -> awaitable, opens/creates a node
  node.blobs()                       -> Blobs
  await blobs.add_bytes(data)        -> BlobAddOutcome(hash, format, size, tag)
  await blobs.read_to_bytes(hash)    -> bytes
  await blobs.list()                 -> list[Hash]
  await blobs.size(hash)             -> int
  Hash.from_string(hex) / .to_hex()
  node.node().status() / .shutdown() -> both awaitable
See scripts/probe_iroh_api.py and scripts/smoke_test.py for the verification
harness — re-run both whenever bumping the `iroh` version pin.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import iroh

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8088


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()


def _plugin_data_dir() -> Path:
    d = _hermes_home() / "plugins" / "hermes-iroh-gateway" / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


async def _maybe_await(value: Any) -> Any:
    """Await `value` if the installed iroh version made this call async;
    pass it through unchanged otherwise. Defensive against binding drift."""
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass
class GatewayConfig:
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    data_dir: str = field(default_factory=lambda: str(_plugin_data_dir() / "node"))

    @classmethod
    def load(cls, path: Path) -> "GatewayConfig":
        if path.exists():
            try:
                return cls(**json.loads(path.read_text()))
            except Exception:
                pass
        return cls()

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(self.__dict__, indent=2))


class GatewayManager:
    """Owns at most one running iroh node + one embedded HTTP gateway server."""

    def __init__(self) -> None:
        self._config_path = _plugin_data_dir() / "config.json"
        self.config = GatewayConfig.load(self._config_path)

        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

        self._node: Any | None = None  # iroh.Iroh
        self._uv_server: Any | None = None  # uvicorn.Server
        self._serve_task: asyncio.Task | None = None
        self._started_at: float | None = None
        self._last_error: str | None = None

    # -- background loop plumbing -----------------------------------------

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                self._loop = loop
                self._thread = threading.Thread(
                    target=loop.run_forever, name="iroh-gateway-loop", daemon=True
                )
                self._thread.start()
            return self._loop

    def _run(self, coro, timeout: float = 30.0):
        loop = self._ensure_loop()
        fut = asyncio.run_coroutine_threadsafe(coro, loop)
        return fut.result(timeout=timeout)

    # -- public sync API (safe to call from any thread) --------------------

    def start(self) -> dict:
        return self._run(self._astart())

    def stop(self) -> dict:
        return self._run(self._astop())

    def restart(self) -> dict:
        self.stop()
        return self.start()

    def status(self) -> dict:
        return self._run(self._astatus())

    def configure(self, host: str | None = None, port: int | None = None,
                  data_dir: str | None = None) -> dict:
        if host is not None:
            self.config.host = host
        if port is not None:
            self.config.port = int(port)
        if data_dir is not None:
            self.config.data_dir = data_dir
        self.config.save(self._config_path)
        return self.config.__dict__

    def put_bytes(self, data: bytes) -> dict:
        return self._run(self._aput(data))

    def get_bytes(self, hash_hex: str) -> bytes | None:
        return self._run(self._aget(hash_hex))

    def list_blobs(self) -> list[dict]:
        return self._run(self._alist())

    # -- async implementations ----------------------------------------------

    async def _astart(self) -> dict:
        import uvicorn  # local import: only needed when actually serving

        if self._node is not None:
            return await self._astatus()

        try:
            Path(self.config.data_dir).mkdir(parents=True, exist_ok=True)
            self._node = await _maybe_await(iroh.Iroh.persistent(self.config.data_dir))

            app = self._build_gateway_app()
            uv_config = uvicorn.Config(
                app, host=self.config.host, port=self.config.port,
                log_level="warning", lifespan="off",
            )
            self._uv_server = uvicorn.Server(uv_config)
            self._serve_task = asyncio.create_task(self._uv_server.serve())
            # Give the server a moment to bind so start() reports a real error
            # (e.g. port already in use) instead of racing the caller.
            for _ in range(50):
                if getattr(self._uv_server, "started", False):
                    break
                if self._serve_task.done():
                    self._serve_task.result()  # re-raise bind errors
                await asyncio.sleep(0.05)

            self._started_at = time.time()
            self._last_error = None
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._node = None
            self._uv_server = None
            self._serve_task = None
            raise

        return await self._astatus()

    async def _astop(self) -> dict:
        if self._uv_server is not None:
            self._uv_server.should_exit = True
            if self._serve_task is not None:
                try:
                    await asyncio.wait_for(self._serve_task, timeout=10)
                except Exception:  # noqa: BLE001
                    pass
        if self._node is not None:
            try:
                node_obj = await _maybe_await(self._node.node())
                await _maybe_await(node_obj.shutdown())
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"shutdown error: {exc}"
        self._node = None
        self._uv_server = None
        self._serve_task = None
        self._started_at = None
        return await self._astatus()

    async def _astatus(self) -> dict:
        running = self._node is not None
        out = {
            "running": running,
            "host": self.config.host,
            "port": self.config.port,
            "data_dir": self.config.data_dir,
            "gateway_url": f"http://{self.config.host}:{self.config.port}",
            "started_at": self._started_at,
            "uptime_s": (time.time() - self._started_at) if self._started_at else None,
            "last_error": self._last_error,
            "node_id": None,
            "blob_count": None,
        }
        if running:
            try:
                node_obj = await _maybe_await(self._node.node())
                endpoint = await _maybe_await(node_obj.endpoint())
                out["node_id"] = await _maybe_await(endpoint.node_id())
            except Exception as exc:  # noqa: BLE001
                out["node_id"] = f"<error: {exc}>"
            try:
                blobs = await _maybe_await(self._node.blobs())
                out["blob_count"] = len(await _maybe_await(blobs.list()))
            except Exception as exc:  # noqa: BLE001
                out["blob_count"] = f"<error: {exc}>"
        return out

    async def _aput(self, data: bytes) -> dict:
        if self._node is None:
            raise RuntimeError("gateway is not running — call start() first")
        blobs = await _maybe_await(self._node.blobs())
        outcome = await _maybe_await(blobs.add_bytes(data))
        hash_hex = outcome.hash.to_hex()
        return {
            "hash": hash_hex,
            "size": outcome.size,
            "url": f"http://{self.config.host}:{self.config.port}/blobs/{hash_hex}",
        }

    async def _aget(self, hash_hex: str) -> bytes | None:
        if self._node is None:
            raise RuntimeError("gateway is not running — call start() first")
        blobs = await _maybe_await(self._node.blobs())
        h = iroh.Hash.from_string(hash_hex)
        has = await _maybe_await(blobs.has(h))
        if not has:
            return None
        return await _maybe_await(blobs.read_to_bytes(h))

    async def _alist(self) -> list[dict]:
        if self._node is None:
            return []
        blobs = await _maybe_await(self._node.blobs())
        hashes = await _maybe_await(blobs.list())
        out = []
        for h in hashes:
            try:
                size = await _maybe_await(blobs.size(h))
            except Exception:  # noqa: BLE001
                size = None
            out.append({"hash": h.to_hex(), "size": size})
        return out

    # -- the actual "iroh http gateway" (its own port, own ASGI app) --------

    def _build_gateway_app(self):
        """The managed gateway itself: GET/PUT blobs by hash over HTTP.
        This is deliberately separate from the Hermes dashboard's own FastAPI
        app in dashboard/plugin_api.py — that one is the control plane
        (start/stop/status); this one is the thing being controlled.
        """
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import JSONResponse, Response

        app = FastAPI(title="iroh-http-gateway")

        @app.get("/")
        async def root():
            st = await self._astatus()
            return JSONResponse({"service": "iroh-http-gateway", **st})

        @app.get("/blobs")
        async def list_blobs_route():
            return JSONResponse(await self._alist())

        @app.get("/blobs/{hash_hex}")
        async def get_blob(hash_hex: str):
            try:
                h = iroh.Hash.from_string(hash_hex)
            except Exception:
                raise HTTPException(status_code=400, detail="invalid blake3 hash")
            blobs = await _maybe_await(self._node.blobs())
            if not await _maybe_await(blobs.has(h)):
                raise HTTPException(status_code=404, detail="blob not found")
            data = await _maybe_await(blobs.read_to_bytes(h))
            return Response(content=data, media_type="application/octet-stream")

        @app.put("/blobs")
        @app.post("/blobs")
        async def put_blob(request: Request):
            data = await request.body()
            if not data:
                raise HTTPException(status_code=400, detail="empty body")
            result = await self._aput(data)
            return JSONResponse(result)

        return app


# Module-level singleton — the one instance both plugin halves import.
manager = GatewayManager()
