#!/usr/bin/env python3
"""Introspect the installed `iroh` package's real API surface.

The iroh-ffi Python bindings are uniffi-generated: every class/method carries
a docstring. Run this inside the flake devShell after `uv pip install -e .`
whenever iroh releases a new version, and diff the output against
gateway_manager.py's assumptions before trusting it in the gateway.
"""
import inspect
import sys


def describe(obj, name, depth=0, seen=None):
    seen = seen if seen is not None else set()
    indent = "  " * depth
    if name in seen or depth > 2:
        return
    seen.add(name)
    doc = (inspect.getdoc(obj) or "").strip().splitlines()
    first_doc_line = doc[0] if doc else ""
    print(f"{indent}{name}: {type(obj).__name__}  {first_doc_line}")
    if inspect.isclass(obj) or inspect.ismodule(obj):
        for attr_name in sorted(dir(obj)):
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(obj, attr_name)
            except Exception as exc:  # noqa: BLE001
                print(f"{indent}  {attr_name}: <error getting attr: {exc}>")
                continue
            if inspect.isroutine(attr):
                try:
                    sig = str(inspect.signature(attr))
                except (TypeError, ValueError):
                    sig = "(...)"
                adoc = (inspect.getdoc(attr) or "").strip().splitlines()
                first = adoc[0] if adoc else ""
                print(f"{indent}  {attr_name}{sig}  {first}")
            elif inspect.isclass(attr):
                describe(attr, attr_name, depth + 1, seen)


def main():
    try:
        import iroh
    except ImportError as exc:
        print(f"iroh is not importable: {exc}", file=sys.stderr)
        print("Run `uv pip install -e .` in the flake devShell first.", file=sys.stderr)
        sys.exit(1)

    print(f"iroh module: {getattr(iroh, '__file__', '?')}")
    print(f"iroh version attr: {getattr(iroh, '__version__', 'unknown')}")
    print()
    top_level = [n for n in dir(iroh) if not n.startswith("_")]
    print(f"Top-level names ({len(top_level)}):")
    for n in sorted(top_level):
        print(f"  {n}")
    print()

    # Classes most likely relevant to a blob-serving HTTP gateway.
    interesting = [
        "Iroh", "Node", "Endpoint", "EndpointOptions",
        "Blobs", "BlobTicket", "Hash", "NodeAddr", "EndpointId",
    ]
    for name in interesting:
        obj = getattr(iroh, name, None)
        if obj is not None:
            print(f"=== {name} ===")
            describe(obj, name)
            print()


if __name__ == "__main__":
    main()
