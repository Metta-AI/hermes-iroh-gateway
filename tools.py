"""Tool handlers — thin wrappers around the shared GatewayManager singleton.

Every handler follows the plugin contract: `def handler(args: dict, **kwargs)
-> str`, never raises, always returns a JSON string.
"""
import json
import sys
from pathlib import Path

# gateway_manager.py lives at the plugin root (sibling of this file) and is
# imported by name (not relatively) so that this agent-tools half and the
# dashboard/plugin_api.py backend half — two separate, unrelated loaders —
# both resolve the SAME module object in sys.modules, and therefore share
# the one process-wide GatewayManager singleton instead of each getting its
# own disconnected copy.
_PLUGIN_ROOT = str(Path(__file__).resolve().parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from gateway_manager import manager  # noqa: E402


def status(args: dict, **kwargs) -> str:
    try:
        return json.dumps(manager.status())
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def start(args: dict, **kwargs) -> str:
    try:
        return json.dumps(manager.start())
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def stop(args: dict, **kwargs) -> str:
    try:
        return json.dumps(manager.stop())
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})


def put(args: dict, **kwargs) -> str:
    text = args.get("text")
    file_path = args.get("file_path")
    if not text and not file_path:
        return json.dumps({"error": "Provide either 'text' or 'file_path'"})
    try:
        if file_path:
            with open(file_path, "rb") as f:
                data = f.read()
        else:
            data = text.encode("utf-8")
        return json.dumps(manager.put_bytes(data))
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)})
