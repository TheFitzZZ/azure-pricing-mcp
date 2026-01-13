#!/usr/bin/env python3
"""
Quick probe script that behaves like an MCP SSE client and lists the server's tools.

Flow:
- Opens the SSE stream (GET /sse by default)
- Reads the endpoint event to learn the POST URL (includes session_id)
- Sends initialize + tools/list requests to that endpoint
- Prints the returned tools
"""

import argparse
import json
import sys
import time
from typing import Generator, Iterable, Tuple
from urllib.parse import unquote, urljoin

import requests


def iter_sse_lines(resp: requests.Response) -> Generator[Tuple[str, str], None, None]:
    """Minimal SSE parser yielding (event, data) pairs."""
    event = None
    data_lines = []
    for raw in resp.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        line = raw.strip()
        if not line:  # blank line signals dispatch
            if event or data_lines:
                yield event or "message", "\n".join(data_lines)
            event, data_lines = None, []
            continue
        if line.startswith(":"):
            continue  # comment/heartbeat
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    if event or data_lines:
        yield event or "message", "\n".join(data_lines)


def post_json(session: requests.Session, url: str, payload: dict, timeout: float) -> requests.Response:
    return session.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=timeout)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe MCP SSE server and list tools")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Server base URL (no trailing slash)")
    parser.add_argument("--sse-path", default="/sse", help="SSE path (default: /sse)")
    parser.add_argument("--protocol-version", default="2024-11-05", help="Protocol version to send in initialize")
    parser.add_argument("--timeout", type=float, default=10.0, help="Connect timeout in seconds")
    parser.add_argument("--read-timeout", type=float, default=60.0, help="Read timeout for SSE stream")
    parser.add_argument("--max-wait", type=float, default=15.0, help="Overall wait limit for responses")
    parser.add_argument("--verbose", action="store_true", help="Print raw SSE events")
    args = parser.parse_args(argv)

    sse_url = urljoin(args.base_url, args.sse_path)
    init_id = "init-1"
    list_id = "list-1"

    print(f"Opening SSE stream at {sse_url} ...")
    start = time.time()

    try:
        with requests.Session() as session:
            with session.get(
                sse_url,
                headers={"Accept": "text/event-stream"},
                stream=True,
                timeout=(args.timeout, args.read_timeout),
            ) as resp:
                resp.raise_for_status()

                message_url = None
                tools_result = None

                for event, data in iter_sse_lines(resp):
                    if args.verbose:
                        print(f"[event={event}] {data}")

                    if event == "endpoint" and message_url is None:
                        message_path = unquote(data)
                        message_url = urljoin(args.base_url, message_path)
                        if args.verbose:
                            print(f"Resolved message URL: {message_url}")

                        init_body = {
                            "jsonrpc": "2.0",
                            "id": init_id,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": args.protocol_version,
                                "capabilities": {},
                                "clientInfo": {"name": "sse-list-tools", "version": "0.1.0"},
                            },
                        }
                        post_json(session, message_url, init_body, args.timeout)

                        list_body = {
                            "jsonrpc": "2.0",
                            "id": list_id,
                            "method": "tools/list",
                            "params": {},
                        }
                        post_json(session, message_url, list_body, args.timeout)
                        continue

                    if event == "message":
                        try:
                            msg = json.loads(data)
                        except json.JSONDecodeError:
                            print(f"Received non-JSON message: {data}")
                            continue

                        if msg.get("id") == list_id and "result" in msg:
                            tools_result = msg["result"].get("tools", [])
                            break

                    if time.time() - start > args.max_wait:
                        print("Timed out waiting for tools response")
                        break

                if tools_result is None:
                    print("No tools received.")
                    return 1

                print(f"Received {len(tools_result)} tools:")
                for tool in tools_result:
                    name = tool.get("name", "<unknown>")
                    desc = tool.get("description") or "(no description)"
                    print(f"- {name}: {desc}")
                return 0
    except requests.HTTPError as http_err:
        print(f"HTTP error: {http_err}")
    except requests.RequestException as req_err:
        print(f"Request error: {req_err}")
    except KeyboardInterrupt:
        print("Interrupted by user")

    return 1


if __name__ == "__main__":
    sys.exit(main())
