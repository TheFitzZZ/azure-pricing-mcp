"""SSE transport for Azure Pricing MCP server.

Exposes the MCP server over HTTP using Server-Sent Events (GET /sse) and
an accompanying POST endpoint for client messages (default /mcp).
"""

import os
from typing import Tuple

import uvicorn
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

from azure_pricing_server import server

# Default endpoints (configurable via env vars)
# NOTE: Many MCP clients expect POST at /messages or /messages/. We mount both.
SSE_PATH = os.getenv("MCP_SSE_PATH", "/sse")
MESSAGE_PATH = os.getenv("MCP_MESSAGE_PATH", "/messages")


def create_app() -> Starlette:
    """Create a Starlette app that serves the MCP server over SSE."""
    # Allow both /messages and /messages/ to work for POST
    message_path = MESSAGE_PATH if MESSAGE_PATH.startswith("/") else f"/{MESSAGE_PATH}"
    message_path_slash = message_path if message_path.endswith("/") else f"{message_path}/"

    transport = SseServerTransport(message_path)

    class MessageEndpoint:
        """ASGI wrapper so we can register an endpoint without double responses."""

        def __init__(self, handler):
            self.handler = handler

        async def __call__(self, scope, receive, send):
            await self.handler(scope, receive, send)

    async def message_asgi(scope, receive, send):  # ASGI app to avoid double responses
        try:
            await transport.handle_post_message(scope, receive, send)
        except Exception as exc:  # noqa: BLE001
            import logging
            import traceback

            logging.error("POST /messages handler error: %s", exc)
            logging.error("Traceback:\n%s", traceback.format_exc())
            resp = PlainTextResponse("Internal Server Error", status_code=500)
            await resp(scope, receive, send)

    async def sse_endpoint(request: Request) -> Response:
        """Handle SSE GET requests and run the MCP server over the stream."""
        async with transport.connect_sse(request.scope, request.receive, request._send) as streams:  # type: ignore[arg-type]
            read_stream, write_stream = streams  # type: Tuple ignored; Starlette types are compatible
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
        return Response()

    async def health(_: Request) -> Response:
        return PlainTextResponse("ok")

    message_endpoint = MessageEndpoint(message_asgi)

    routes = [
        Route("/health", endpoint=health, methods=["GET"]),
        Route(SSE_PATH, endpoint=sse_endpoint, methods=["GET"]),
        Route(message_path, endpoint=message_endpoint, methods=["POST"]),
        Route(message_path_slash, endpoint=message_endpoint, methods=["POST"]),
    ]

    app = Starlette(debug=False, routes=routes)
    # Disable automatic slash redirects so both /messages and /messages/ work without 307s
    app.router.redirect_slashes = False
    return app


def main() -> None:
    """Run the SSE server using uvicorn."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("UVICORN_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
