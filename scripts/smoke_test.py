#!/usr/bin/env python3
"""Smoke test: prove the confirmed iroh API round-trips a blob.

Run inside the flake devShell after `uv pip install -e .`:
    source .venv/bin/activate && python scripts/smoke_test.py
"""
import asyncio
import inspect

import iroh


async def main():
    print("Iroh.memory is coroutine function:", inspect.iscoroutinefunction(iroh.Iroh.memory))

    node = await iroh.Iroh.memory()
    print("node:", node)

    blobs = node.blobs()
    print("blobs:", blobs, "add_bytes is coroutine:", inspect.iscoroutinefunction(blobs.add_bytes))

    outcome = await blobs.add_bytes(b"hello from hermes-iroh-gateway\n")
    print("add_bytes outcome:", outcome, dir(outcome))

    h = outcome.hash
    print("hash:", h, "hex:", h.to_hex())

    data = await blobs.read_to_bytes(h)
    print("round-tripped bytes:", data)
    assert data == b"hello from hermes-iroh-gateway\n"

    all_blobs = await blobs.list()
    print("list():", [b.to_hex() for b in all_blobs])

    node_obj = node.node()
    status = await node_obj.status()
    print("node status:", status)

    await node_obj.shutdown()
    print("OK - round trip verified")


if __name__ == "__main__":
    asyncio.run(main())
