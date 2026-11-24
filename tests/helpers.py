"""Shared test helpers: an isolated mock DMS and an MCP server pointed at it."""

from __future__ import annotations

from fastapi.testclient import TestClient

from erpbridge.server import McpServer
from erpbridge.soap_client import SoapClient
from erpbridge.soap_server import DmsState, create_app


def make_stack():
    state = DmsState()
    app = create_app(state)
    http = TestClient(app)
    soap = SoapClient(base_url="http://testserver/dms", http=http, timeout=2.0, retries=2)
    mcp = McpServer(client=soap)
    return state, app, soap, mcp


def initialize(mcp: McpServer, msg_id=1):
    response = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "tests", "version": "0"},
            },
        }
    )
    mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return response
