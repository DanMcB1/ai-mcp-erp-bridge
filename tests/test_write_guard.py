"""create_parts_order must not touch the DMS without confirm=true."""

from __future__ import annotations

import unittest

from tests.helpers import initialize, make_stack


class WriteGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state, self.app, self.soap, self.mcp = make_stack()
        initialize(self.mcp)

    def tearDown(self) -> None:
        self.mcp.close()

    def _call(self, arguments: dict, msg_id=30):
        return self.mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "method": "tools/call",
                "params": {"name": "create_parts_order", "arguments": arguments},
            }
        )

    def test_missing_confirm_does_not_create_an_order(self) -> None:
        before = len(self.state.orders)
        response = self._call(
            {"store": "Lakeside Honda", "part_number": "12345", "quantity": 1}
        )
        self.assertTrue(response["result"]["isError"])
        text = response["result"]["content"][0]["text"]
        self.assertIn("confirm=true", text)
        self.assertIn("No parts order was placed", text)
        self.assertEqual(len(self.state.orders), before)
        # And no SOAP envelope was sent for CreatePartsOrder.
        self.assertNotIn("CreatePartsOrder", self.soap.last_request_xml or "")

    def test_confirm_false_is_also_blocked(self) -> None:
        before = len(self.state.orders)
        response = self._call(
            {
                "store": "Lakeside Honda",
                "part_number": "12345",
                "quantity": 1,
                "confirm": False,
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(len(self.state.orders), before)

    def test_confirm_string_true_is_not_enough(self) -> None:
        response = self._call(
            {
                "store": "Lakeside Honda",
                "part_number": "12345",
                "quantity": 1,
                "confirm": "true",
            }
        )
        # Type check rejects a string; still no write.
        self.assertTrue(response["result"]["isError"])
        self.assertEqual(self.state.orders, [])

    def test_confirm_true_places_a_simulated_order(self) -> None:
        on_hand_before = float(self.state.parts[("01", "12345")]["QtyOnHand"])
        response = self._call(
            {
                "store": "Lakeside Honda",
                "part_number": "12345",
                "quantity": 2,
                "charge_to_ro": "7781",
                "confirm": True,
            }
        )
        self.assertFalse(response["result"]["isError"])
        data = response["result"]["structuredContent"]
        self.assertTrue(data["order_number"].startswith("PO-"))
        self.assertEqual(data["quantity"], 2)
        self.assertEqual(data["charge_to_ro"], "7781")
        self.assertTrue(data["simulated"])
        self.assertEqual(len(self.state.orders), 1)
        self.assertIn("CreatePartsOrder", self.soap.last_request_xml)
        self.assertIn("2.0000", self.soap.last_request_xml)
        on_hand_after = float(self.state.parts[("01", "12345")]["QtyOnHand"])
        self.assertEqual(on_hand_after, on_hand_before - 2)

    def test_insufficient_quantity_is_a_soap_fault(self) -> None:
        response = self._call(
            {
                "store": "Lakeside Honda",
                "part_number": "12345",
                "quantity": 999,
                "confirm": True,
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("INSUFFICIENT_QTY", response["result"]["content"][0]["text"])
        self.assertEqual(self.state.orders, [])


if __name__ == "__main__":
    unittest.main()
