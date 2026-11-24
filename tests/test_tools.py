"""Tool schemas, listing, and happy-path mapping of the four MCP tools."""

from __future__ import annotations

import json
import unittest

from erpbridge.tools import TOOLS, TOOLS_BY_NAME, validate_arguments
from tests.helpers import initialize, make_stack


class ToolSchemaTests(unittest.TestCase):
    def test_expected_tools_exist_with_json_schemas(self) -> None:
        names = [tool["name"] for tool in TOOLS]
        self.assertEqual(
            names,
            [
                "get_part_availability",
                "get_repair_order",
                "get_customer_vehicle",
                "create_parts_order",
            ],
        )
        for tool in TOOLS:
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertIn("properties", schema)
            self.assertIsInstance(tool["description"], str)
            self.assertTrue(tool["description"])

    def test_write_tool_documents_confirm(self) -> None:
        schema = TOOLS_BY_NAME["create_parts_order"]["inputSchema"]
        self.assertIn("confirm", schema["properties"])
        self.assertEqual(schema["properties"]["confirm"]["type"], "boolean")
        self.assertIn("confirm", schema["properties"]["confirm"]["description"].lower())

    def test_validate_arguments_catches_missing_and_types(self) -> None:
        self.assertIsNone(
            validate_arguments(
                "get_part_availability",
                {"store": "Lakeside Honda", "part_number": "12345"},
            )
        )
        self.assertIn(
            "Missing",
            validate_arguments("get_part_availability", {"store": "Lakeside Honda"}) or "",
        )
        self.assertIn(
            "integer",
            validate_arguments(
                "create_parts_order",
                {"store": "01", "part_number": "12345", "quantity": "1"},
            )
            or "",
        )
        self.assertIn(
            "vin or customer_number",
            validate_arguments("get_customer_vehicle", {}) or "",
        )


class ToolCallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state, self.app, self.soap, self.mcp = make_stack()
        initialize(self.mcp)

    def tearDown(self) -> None:
        self.mcp.close()

    def _call(self, name: str, arguments: dict, msg_id=20):
        return self.mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )

    def test_tools_list(self) -> None:
        response = self.mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in response["result"]["tools"]]
        self.assertEqual(names, [t["name"] for t in TOOLS])

    def test_part_availability_maps_string_quantities(self) -> None:
        response = self._call(
            "get_part_availability",
            {"store": "Lakeside Honda", "part_number": "12345"},
        )
        self.assertFalse(response["result"]["isError"])
        data = response["result"]["structuredContent"]
        self.assertEqual(data["store"], "Lakeside Honda")
        self.assertEqual(data["store_number"], "01")
        self.assertEqual(data["quantity_on_hand"], 14)
        self.assertEqual(data["list_price"], 12.85)
        self.assertEqual(data["bin_location"], "A-14-C")
        self.assertEqual(data["availability"], "in_stock")
        self.assertIsInstance(data["quantity_on_hand"], int)
        # The wire still used the quirky SOAP names.
        self.assertIn("StoreNum", self.soap.last_request_xml)
        self.assertIn("PartNo", self.soap.last_request_xml)
        self.assertIn("SessTok", self.soap.last_request_xml)
        self.assertIn("QtyOnHand", self.soap.last_response_xml)
        self.assertIn("14.0000", self.soap.last_response_xml)

    def test_repair_order_maps_codes_and_dates(self) -> None:
        response = self._call(
            "get_repair_order",
            {"store": "Lakeside Honda", "ro_number": "7781"},
        )
        data = response["result"]["structuredContent"]
        self.assertEqual(data["status"], "open")
        self.assertEqual(data["opened_on"], "2026-11-20")
        self.assertEqual(data["customer_name"], "Maya Elena Alvarez")
        self.assertEqual(data["vin"], "1LKSDM26XMCB00001")
        self.assertEqual(data["year"], 2023)
        self.assertEqual(data["make"], "HONDA")
        self.assertGreaterEqual(len(data["lines"]), 2)
        self.assertIn("RONum", self.soap.last_request_xml)

    def test_customer_vehicle_by_vin(self) -> None:
        response = self._call(
            "get_customer_vehicle",
            {"vin": "1LKSDM26XMCB00001"},
        )
        data = response["result"]["structuredContent"]
        self.assertEqual(data["customer_number"], "C-44108")
        self.assertEqual(data["stock_number"], "0007781")
        self.assertEqual(data["last_service_on"], "2026-11-20")

    def test_schema_error_is_tool_error_not_jsonrpc_error(self) -> None:
        response = self._call("get_part_availability", {"store": "Lakeside Honda"})
        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("Missing", response["result"]["content"][0]["text"])

    def test_resources_list_and_read(self) -> None:
        listed = self.mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
        uris = [r["uri"] for r in listed["result"]["resources"]]
        self.assertIn("dms://stores", uris)
        self.assertIn("dms://wsdl", uris)
        read = self.mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "resources/read",
                "params": {"uri": "dms://stores"},
            }
        )
        body = read["result"]["contents"][0]["text"]
        stores = json.loads(body)
        self.assertEqual(stores[0]["name"], "Lakeside Honda")


if __name__ == "__main__":
    unittest.main()
