"""Stdio Content-Length framing, plus an optional official MCP SDK interop test."""

from __future__ import annotations

import asyncio
import io
import json
import os
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

from erpbridge.protocol import METHOD_NOT_FOUND
from erpbridge.stdio import read_message, write_message
from tests.helpers import initialize, make_stack

ROOT = Path(__file__).resolve().parents[1]

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    HAS_MCP_SDK = True
except ImportError:
    HAS_MCP_SDK = False


class StdioFramingTests(unittest.TestCase):
    def test_round_trip_content_length(self) -> None:
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 3, "method": "ping", "params": {}},
            separators=(",", ":"),
        ).encode("utf-8")
        buf = io.BytesIO()
        write_message(buf, payload, mode="content-length")
        buf.seek(0)
        body, mode = read_message(buf)
        self.assertEqual(mode, "content-length")
        self.assertEqual(body, payload)
        self.assertEqual(json.loads(body)["id"], 3)

    def test_round_trip_ndjson(self) -> None:
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": 4, "method": "ping", "params": {}},
            separators=(",", ":"),
        ).encode("utf-8")
        buf = io.BytesIO()
        write_message(buf, payload, mode="ndjson")
        buf.seek(0)
        body, mode = read_message(buf)
        self.assertEqual(mode, "ndjson")
        self.assertEqual(body, payload)
        self.assertEqual(json.loads(body)["id"], 4)

    def test_handle_raw_framed_style_body(self) -> None:
        _state, _app, _soap, mcp = make_stack()
        self.addCleanup(mcp.close)
        initialize(mcp)
        raw = json.dumps({"jsonrpc": "2.0", "id": 8, "method": "nope"})
        response = mcp.handle_raw(raw)
        self.assertEqual(response["error"]["code"], METHOD_NOT_FOUND)
        self.assertEqual(response["id"], 8)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _wait_port(port: int, timeout: float = 8.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            connected = socket.create_connection(("127.0.0.1", port), 0.2)
            connected.close()
            return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError(f"Port {port} did not open")


@unittest.skipUnless(HAS_MCP_SDK, "official mcp Python SDK is not installed")
class OfficialSdkInteropTests(unittest.TestCase):
    def test_sdk_client_lists_and_calls_tools(self) -> None:
        import uvicorn

        from erpbridge.soap_server import DmsState, create_app

        port = _free_port()
        state = DmsState()
        app = create_app(state)
        config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        http_server = uvicorn.Server(config)
        thread = threading.Thread(target=http_server.run, daemon=True)
        thread.start()
        _wait_port(port)

        env = os.environ.copy()
        env["ERPBRIDGE_SOAP_URL"] = f"http://127.0.0.1:{port}/dms"
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "erpbridge", "stdio"],
            env=env,
            cwd=str(ROOT),
        )

        async def scenario() -> None:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    init = await session.initialize()
                    server_info = getattr(init, "server_info", None) or init.serverInfo
                    self.assertEqual(server_info.name, "lakeside-dms-bridge")
                    tools = await session.list_tools()
                    names = [tool.name for tool in tools.tools]
                    self.assertIn("get_part_availability", names)
                    self.assertIn("create_parts_order", names)
                    result = await session.call_tool(
                        "get_part_availability",
                        arguments={"store": "Lakeside Honda", "part_number": "12345"},
                    )
                    is_error = getattr(result, "is_error", getattr(result, "isError", False))
                    self.assertFalse(is_error)
                    text = result.content[0].text
                    data = json.loads(text)
                    self.assertEqual(data["quantity_on_hand"], 14)
                    blocked = await session.call_tool(
                        "create_parts_order",
                        arguments={
                            "store": "Lakeside Honda",
                            "part_number": "12345",
                            "quantity": 1,
                        },
                    )
                    blocked_error = getattr(blocked, "is_error", getattr(blocked, "isError", False))
                    self.assertTrue(blocked_error)

        try:
            asyncio.run(asyncio.wait_for(scenario(), timeout=25))
        finally:
            http_server.should_exit = True


class DemoClientTests(unittest.TestCase):
    def test_scripted_question(self) -> None:
        from erpbridge.demo import DEMO_QUESTION, run_demo

        _state, _app, soap, mcp = make_stack()
        self.addCleanup(mcp.close)
        result = run_demo(mcp)
        self.assertEqual(result["question"], DEMO_QUESTION)
        self.assertIn("in stock", result["answer"])
        self.assertIn("14", result["answer"])
        self.assertIn("Maya Elena Alvarez", result["answer"])
        self.assertIn("7781", result["answer"])
        self.assertIn("CR-V", result["answer"])


if __name__ == "__main__":
    unittest.main()
