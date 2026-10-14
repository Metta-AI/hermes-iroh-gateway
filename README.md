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

## Installing on a nix/home-manager-managed Hermes

This repo's flake exposes a ready-to-import home-manager module:

```nix
# in your nixos-config / home-manager flake:
inputs.hermes-iroh-gateway.url = "github:<owner>/hermes-iroh-gateway"; # not pushed yet — see Status
# ...
imports = [ inputs.hermes-iroh-gateway.homeManagerModules.default ];
```

It wires up `services.hermes-agent.extraPlugins` (symlinks this repo into
`$HERMES_HOME/plugins/`), `extraPythonPackages` (`iroh` wrapped from a real
PyPI wheel + `fastapi`/`uvicorn` from nixpkgs), and
`settings.plugins.enabled`. See `nix/home-manager-module.nix` for exactly
which inputs are verified vs. just wired-in-unverified — and the Status
section below before trusting it blindly.

### Why a nix module, not `hermes plugins enable`

On a nix/home-manager-managed Hermes install, `config.yaml` is rendered
declaratively and the CLI refuses to mutate it at runtime —
`hermes plugins enable` and even plain `hermes config set` both fail with
"this Hermes installation is managed by home-manager." This isn't a
dependency problem, it's a different install model: Nix owns the config and
the Python environment, so provisioning has to happen at the nix level
(`extraPythonPackages`/`extraPlugins`/`settings.plugins.enabled`), not
through any hermes subcommand. On a plain pip/source Hermes install, none of
this applies — `hermes plugins install --enable` (optionally with
`--yes-deps`) handles it through Hermes's own package manager instead.

## Status — what's verified, what isn't (read this before integrating)

**Verified for real, with evidence, inside a flake devShell + against the
real `hermes` binary of a nix-managed Hermes install:**

- `gateway_manager.py`: full round trip against the actual installed
  `iroh==0.35.0` package — started a persistent node, booted its own
  embedded uvicorn HTTP gateway, stored and fetched a blob both through the
  control-plane passthrough *and* by hitting the gateway's own port
  directly, listed blobs, stopped cleanly, confirmed blobs persist across
  separate process runs.
- `dashboard/plugin_api.py`: every route exercised via FastAPI's
  `TestClient` (start/stop/status/config/blobs/blobs-text/blobs/{hash}).
- Agent tools (`__init__.py`/`tools.py`) and the dashboard backend confirmed
  to share the **same** `GatewayManager` singleton even when loaded through
  two different, unrelated import mechanisms (a real bug was caught and
  fixed here — a bare `import gateway_manager` would otherwise silently
  create two disconnected instances with two disconnected iroh nodes).
- `hermes plugins doctor hermes-iroh-gateway --ci`, run against the actual
  sandbox's real Hermes binary (not a simulation): clean pass, manifest
  parses, all 4 tools register. Achieved by building a Python-3.14-matched
  venv with this repo's own flake + `uv` (matching Hermes's own interpreter
  exactly) and pointing `PYTHONPATH` at it — proves the plugin code is
  correct against Hermes's real discovery/import/registration pipeline.
- `desktop/plugin.js` is syntax-valid (`node --check`). Two real bugs were
  caught and fixed while writing it: a dead/broken wrapper component, and a
  closure variable that the SDK's own docs warn gets wiped on re-render
  (fixed with the SDK's `atom`/`useValue` pattern instead).
- `flake.nix`'s `homeManagerModules.default` output evaluates to a
  well-formed function (`nix flake check` passes; `nix eval` confirms it's
  a lambda). Every URL + SHA256 for the `iroh` wheel (all 4 platforms) and
  the `fastapi`/`uvicorn` nixpkgs attribute paths were pulled from PyPI's
  JSON API / a live `nix eval` against `nixos-unstable`, not guessed — one
  fabricated PyPI URL path was caught and corrected before it shipped.

**NOT done / explicitly unverified — pick up here:**

1. **The plugin has never been enabled and run inside a live Hermes
   process.** No real chat turn ever called `iroh_gateway_start` through an
   actual LLM tool call; the desktop pane was never rendered in a running
   Hermes Desktop app. This sandbox's Hermes install refuses imperative
   `plugins enable`/`config set` by design (see above), so there was no way
   to flip it on here. Everything above was validated through harnesses
   that mimic Hermes's real loading mechanics (doctor, TestClient, a
   package-loader simulation for `__init__.py`) — not a live run. **This is
   the main gap — do this first.**
2. **`nix/home-manager-module.nix` has never been evaluated against a real
   `services.hermes-agent` home-manager module** — only checked in
   isolation as a well-typed function. `config.services.hermes-agent.package
   .python.pkgs` is assumed to have that shape; verify against the actual
   hermes-agent home-manager module source before trusting it.
3. **No git remote.** This repo is local-only on one machine
   (`/home/malcolm/Projects/softmax/hermes-iroh-gateway`, confirmed to be
   real persistent disk, not a container layer). Push it somewhere before
   `inputs.hermes-iroh-gateway.url = "github:..."` can work; use a local
   `path:` flake input override until then.
4. **`iroh` wheels for aarch64-linux / x86_64-darwin / aarch64-darwin** are
   wired into the nix module from the same verified PyPI listing as the
   x86_64-linux one (correct per-file URL + hash), but were never actually
   fetched/installed/imported on those platforms — only x86_64-linux was
   exercised live.
5. **No automated tests/CI.** `scripts/smoke_test.py`,
   `scripts/probe_iroh_api.py`, and the `TestClient` snippet above are
   manual dev-loop scripts; nothing runs them automatically.
6. **No version/tag strategy.** Two commits, no tags — consumers have
   nothing stable to pin a flake input `rev` or `hermes plugins install
   --ref` to yet.
7. **No collision-avoidance or multi-instance story** for the gateway's
   default bind (`127.0.0.1:8088`) — fine for one user, undocumented beyond
   that.
8. `plugin.yaml`'s `python_dependencies` field is informational only on a
   nix-managed install (Hermes's PM-based auto-install doesn't apply there —
   see above); `nix/home-manager-module.nix` is the actual provisioning
   mechanism for that case, and it's gap #2 above that needs closing to
   trust it fully.
