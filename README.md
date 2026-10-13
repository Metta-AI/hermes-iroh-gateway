# hermes-iroh-gateway

A Hermes plugin that manages an embedded [iroh](https://docs.iroh.computer/)
content-addressed HTTP gateway: start/stop/configure a persistent iroh node,
add and fetch blobs by BLAKE3 hash over plain HTTP, from both a native
Hermes Desktop control pane and Hermes agent tool calls.

## Architecture

Two independent HTTP servers run inside the Hermes process once this plugin
is enabled:

1. **The managed gateway itself** (`gateway_manager.py: _build_gateway_app`)
   — a small FastAPI/uvicorn server bound to its own `host:port` (default
   `127.0.0.1:8088`). This is "the iroh http gateway": `GET /blobs/<hash>`
   returns the raw bytes, `POST /blobs` adds a blob and returns its hash.
2. **The control plane** (`dashboard/plugin_api.py`) — mounted by Hermes
   under `/api/plugins/hermes-iroh-gateway/*`. Exposes start/stop/status/
   configure/list/upload, and a `/events` websocket for live status.

Both halves — plus the agent-side tools in `__init__.py`/`tools.py` — import
one shared `GatewayManager` singleton from `gateway_manager.py`. That
manager owns a dedicated background asyncio event loop (a small actor
thread), so every public method is a plain blocking call safe to invoke from
sync tool handlers, sync FastAPI routes, or anywhere else — see the module
docstring for why.

```
hermes-iroh-gateway/
├── flake.nix              # devShell: python, uv, rustc/cargo (sdist fallback), node, curl/jq
├── pyproject.toml         # iroh, fastapi, uvicorn
├── plugin.yaml            # agent-side manifest (tools, python_dependencies)
├── gateway_manager.py     # the shared singleton — node + embedded gateway lifecycle
├── __init__.py            # agent tools: iroh_gateway_{status,start,stop,put}
├── schemas.py / tools.py
├── dashboard/
│   ├── manifest.json      # hidden tab, "api": "plugin_api.py"
│   ├── plugin_api.py      # control-plane FastAPI router
│   └── dist/index.js      # no-op placeholder (manifest requires an entry bundle)
├── desktop/
│   └── plugin.js          # native control pane + statusbar chip
└── scripts/
    ├── probe_iroh_api.py  # introspect the installed iroh package's real API
    └── smoke_test.py      # round-trip a blob against the real iroh node
```

## Why the `iroh` Python package, not the separate `iroh-gateway` Rust binary

`pip install iroh` ships the real Rust iroh core (uniffi-rs bindings) as
prebuilt native wheels — macOS (arm64/x86_64), Linux x86_64/aarch64
(**glibc only**), Windows x86_64. That gives a full node (`iroh.Iroh`) with
a blob store directly callable from Python, so the "gateway" is just our own
thin FastAPI layer over it — no separate Rust binary to vendor, build, or
subprocess-manage. See `scripts/probe_iroh_api.py`'s output for the full
confirmed API surface (re-run it after bumping the `iroh` version pin —
these bindings are young and evolve).

## Dev loop

```bash
nix develop                        # python3.12, uv, rustc/cargo fallback toolchain, node, curl/jq
uv venv -p 3.12 .venv && source .venv/bin/activate
uv pip install -e ".[test]"

python scripts/probe_iroh_api.py   # introspect the installed iroh API before trusting any assumption
python scripts/smoke_test.py       # round-trip a blob against a real in-memory node

# Exercise the control-plane router + the real embedded gateway end-to-end,
# the way Hermes itself will, without needing a live Hermes process:
python - <<'PY'
import sys, importlib.util
sys.path.insert(0, ".")
spec = importlib.util.spec_from_file_location("plugin_api", "dashboard/plugin_api.py")
plugin_api = importlib.util.module_from_spec(spec); spec.loader.exec_module(plugin_api)
from fastapi import FastAPI
from fastapi.testclient import TestClient
app = FastAPI(); app.include_router(plugin_api.router, prefix="/api/plugins/hermes-iroh-gateway")
client = TestClient(app)
print(client.post("/api/plugins/hermes-iroh-gateway/start").json())
print(client.post("/api/plugins/hermes-iroh-gateway/blobs/text", json={"text": "hi"}).json())
PY
```

Syntax-check the desktop pane without a full Hermes app running:
`node --check desktop/plugin.js`.

## Installing into a real Hermes

```bash
ln -s "$(pwd)" ~/.hermes/plugins/hermes-iroh-gateway   # symlink, not a copy — git stays the source of truth
hermes plugins doctor ~/.hermes/plugins/hermes-iroh-gateway --ci
hermes plugins enable hermes-iroh-gateway               # adds it to plugins.enabled in config.yaml
```

Then in the desktop app: **Settings → Plugins → Iroh Gateway → enable**
(the Python backend and the desktop UI toggle are independent gates — both
must be on), then **⌘K → Reload desktop plugins** if the pane doesn't
appear within a few seconds.

### ⚠ Known gap on nix/home-manager-managed Hermes installs

`plugin.yaml`'s `python_dependencies` (`iroh`, `fastapi`, `uvicorn`) is
**declare-and-surface only** — `hermes plugins doctor` reports what's
missing, but Hermes never runs `pip install` for you. On a normal
pip/pyenv/venv-based Hermes install, you'd just `pip install iroh fastapi
uvicorn` into that same environment. On a **nix/home-manager-managed**
install (confirmed to be the case in this project's target environment —
`hermes doctor` reports a "virtual environment" that is actually an
immutable `/nix/store` path), there is no writable site-packages to pip
install into, and `iroh` is not currently packaged in nixpkgs (it's a
PyPI-only prebuilt wheel with a native extension — see
`scripts/probe_iroh_api.py` output for proof it installs cleanly via
`uv pip install`/wheel, just not via nixpkgs). Getting it onto Hermes's own
interpreter declaratively needs either:

1. A nix derivation wrapping the `iroh` PyPI wheel (`buildPythonPackage
   { format = "wheel"; }` fetching the right platform tag from PyPI) added
   to whatever home-manager option builds `hermes-agent-env`'s Python
   package set, or
2. Hermes gaining a per-plugin venv/interpreter override (not available
   today — `python_dependencies` isolation is explicitly called out as
   deferred in the upstream docs).

Until one of those lands, `hermes plugins doctor` on this plugin will report
`No module named 'iroh'` on a nix-managed install even though the plugin
code itself is correct — verified independently against the real installed
`iroh==0.35.0` package inside this repo's own flake devShell (see Dev loop
above).
