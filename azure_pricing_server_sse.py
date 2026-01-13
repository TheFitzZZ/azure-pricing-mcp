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
from starlette.responses import Response
from starlette.routing import Mount, Route

from azure_pricing_server import server

# Default endpoints (configurable via env vars)
SSE_PATH = os.getenv("MCP_SSE_PATH", "/sse")
MESSAGE_PATH = os.getenv("MCP_MESSAGE_PATH", "/mcp")


def create_app() -> Starlette:
    """Create a Starlette app that serves the MCP server over SSE."""
    transport = SseServerTransport(MESSAGE_PATH)

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

    routes = [
        Route(SSE_PATH, endpoint=sse_endpoint, methods=["GET"]),
        Mount(MESSAGE_PATH, app=transport.handle_post_message),
    ]

    return Starlette(debug=False, routes=routes)


def main() -> None:
    """Run the SSE server using uvicorn."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    app = create_app()
    uvicorn.run(app, host=host, port=port, log_level=os.getenv("UVICORN_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
