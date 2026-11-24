"""JSON-RPC 2.0 conformance: ids, notifications, and standard error codes."""

from __future__ import annotations

import json
import unittest

from erpbridge.protocol import (
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
)
from tests.helpers import initialize, make_stack


class JsonRpcTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state, self.app, self.soap, self.mcp = make_stack()

    def tearDown(self) -> None:
        self.mcp.close()

    def test_numeric_id_is_echoed(self) -> None:
        response = initialize(self.mcp, msg_id=17)
        self.assertEqual(response["id"], 17)
        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertIn("result", response)
        self.assertEqual(response["result"]["serverInfo"]["name"], "lakeside-dms-bridge")

    def test_string_id_is_echoed(self) -> None:
        response = initialize(self.mcp, msg_id="abc-1")
        self.assertEqual(response["id"], "abc-1")

    def test_notification_has_no_response(self) -> None:
        initialize(self.mcp)
        response = self.mcp.handle(
            {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        self.assertIsNone(response)
        # An unknown notification must also stay silent.
        self.assertIsNone(
            self.mcp.handle({"jsonrpc": "2.0", "method": "notifications/cancelled"})
        )

    def test_method_not_found_is_32601(self) -> None:
        initialize(self.mcp)
        response = self.mcp.handle(
            {"jsonrpc": "2.0", "id": 9, "method": "tools/launch", "params": {}}
        )
        self.assertEqual(response["id"], 9)
        self.assertEqual(response["error"]["code"], METHOD_NOT_FOUND)
        self.assertIn("tools/launch", response["error"]["message"])

    def test_invalid_params_is_32602(self) -> None:
        initialize(self.mcp)
        response = self.mcp.handle(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {}}
        )
        self.assertEqual(response["error"]["code"], INVALID_PARAMS)
        self.assertEqual(response["id"], 4)

        response = self.mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "not_a_real_tool", "arguments": {}},
            }
        )
        self.assertEqual(response["error"]["code"], INVALID_PARAMS)

        response = self.mcp.handle(
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": ["oops"]}
        )
        self.assertEqual(response["error"]["code"], INVALID_PARAMS)

    def test_parse_error_is_32700(self) -> None:
        response = self.mcp.handle_raw("{not-json")
        self.assertEqual(response["id"], None)
        self.assertEqual(response["error"]["code"], PARSE_ERROR)

    def test_invalid_request_is_32600(self) -> None:
        response = self.mcp.handle_raw(json.dumps({"id": 1, "method": "ping"}))
        self.assertEqual(response["error"]["code"], INVALID_REQUEST)

        response = self.mcp.handle_raw(json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}]))
        self.assertEqual(response["error"]["code"], INVALID_REQUEST)

    def test_tools_require_initialize(self) -> None:
        response = self.mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response["error"]["code"], INVALID_PARAMS)
        self.assertIn("initialized", response["error"]["message"])


if __name__ == "__main__":
    unittest.main()
