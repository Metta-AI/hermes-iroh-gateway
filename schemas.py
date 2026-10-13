"""Tool schemas — what the LLM sees when deciding to call iroh gateway tools."""

IROH_GATEWAY_STATUS = {
    "name": "iroh_gateway_status",
    "description": (
        "Check whether the managed iroh content-addressed HTTP gateway is "
        "running, and if so its host:port, node id, and blob count."
    ),
    "parameters": {"type": "object", "properties": {}},
}

IROH_GATEWAY_START = {
    "name": "iroh_gateway_start",
    "description": (
        "Start the managed iroh HTTP gateway: opens (or creates) a persistent "
        "iroh node and serves its blobs over HTTP at the configured host:port. "
        "No-op if already running."
    ),
    "parameters": {"type": "object", "properties": {}},
}

IROH_GATEWAY_STOP = {
    "name": "iroh_gateway_stop",
    "description": "Stop the managed iroh HTTP gateway and shut down its node.",
    "parameters": {"type": "object", "properties": {}},
}

IROH_GATEWAY_PUT = {
    "name": "iroh_gateway_put",
    "description": (
        "Add content to the running iroh gateway's blob store, by inline text "
        "or by reading a local file, and return its BLAKE3 hash plus the HTTP "
        "URL it's now servable at (gateway must be running — call "
        "iroh_gateway_start first if needed)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Inline text content to store as a blob (UTF-8).",
            },
            "file_path": {
                "type": "string",
                "description": "Absolute path of a local file to read and store as a blob.",
            },
        },
    },
}
