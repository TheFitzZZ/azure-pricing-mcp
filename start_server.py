"""Transport switcher for Azure Pricing MCP server."""

import asyncio
import os

from azure_pricing_server import main as stdio_main
from azure_pricing_server_sse import main as sse_main


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "sse").lower()

    if transport == "stdio":
        asyncio.run(stdio_main())
    elif transport == "sse":
        sse_main()
    else:
        raise ValueError(f"Unsupported MCP_TRANSPORT: {transport}")


if __name__ == "__main__":
    main()
