"""hermes-iroh-gateway — agent-side plugin half.

Registers tools so the agent itself can drive the same GatewayManager
singleton that the desktop control pane (dashboard/plugin_api.py +
desktop/plugin.js) talks to — both halves import `gateway_manager.manager`,
so starting the gateway from a chat tool call makes the desktop status pane
reflect it immediately, and vice versa.
"""
import logging

from . import schemas, tools

logger = logging.getLogger(__name__)


def register(ctx):
    ctx.register_tool(
        name="iroh_gateway_status", toolset="iroh-gateway",
        schema=schemas.IROH_GATEWAY_STATUS, handler=tools.status,
    )
    ctx.register_tool(
        name="iroh_gateway_start", toolset="iroh-gateway",
        schema=schemas.IROH_GATEWAY_START, handler=tools.start,
    )
    ctx.register_tool(
        name="iroh_gateway_stop", toolset="iroh-gateway",
        schema=schemas.IROH_GATEWAY_STOP, handler=tools.stop,
    )
    ctx.register_tool(
        name="iroh_gateway_put", toolset="iroh-gateway",
        schema=schemas.IROH_GATEWAY_PUT, handler=tools.put,
    )
    logger.info("hermes-iroh-gateway: registered 4 tools")
