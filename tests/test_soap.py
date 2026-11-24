"""SOAP mapping, faults, session handling, retries, and WSDL."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from erpbridge.catalog import PARTS
from erpbridge.settings import FLAKY_PART_NUMBER, SLOW_PART_NUMBER
from erpbridge.soap_client import SoapError
from erpbridge.soap_server import WSDL, create_app
from tests.helpers import initialize, make_stack


class SoapMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state, self.app, self.soap, self.mcp = make_stack()
        initialize(self.mcp)

    def tearDown(self) -> None:
        self.mcp.close()

    def test_wsdl_is_served(self) -> None:
        http = TestClient(self.app)
        response = http.get("/dms?wsdl")
        self.assertEqual(response.status_code, 200)
        self.assertIn("GetPartAvailability", response.text)
        self.assertIn("GetRepairOrder", response.text)
        self.assertIn("CreatePartsOrder", response.text)
        self.assertIn("GetCustomerVehicle", response.text)
        self.assertIn("Login", response.text)
        self.assertIn("wsdl:definitions", WSDL)

    def test_unknown_part_becomes_tool_error(self) -> None:
        response = self.mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "get_part_availability",
                    "arguments": {"store": "Lakeside Honda", "part_number": "NO-SUCH"},
                },
            }
        )
        self.assertTrue(response["result"]["isError"])
        text = response["result"]["content"][0]["text"]
        self.assertIn("PART_NOT_FOUND", text)
        self.assertIn("faultstring", self.soap.last_response_xml.lower() + self.soap.last_response_xml)
        self.assertIn("PART_NOT_FOUND", self.soap.last_response_xml)

    def test_unknown_repair_order_fault(self) -> None:
        response = self.mcp.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "get_repair_order",
                    "arguments": {"store": "Lakeside Honda", "ro_number": "0000"},
                },
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("RO_NOT_FOUND", response["result"]["content"][0]["text"])

    def test_unknown_store_is_mapped(self) -> None:
        with self.assertRaises(SoapError) as ctx:
            self.soap.get_part_availability("No Such Rooftop", "12345")
        self.assertEqual(ctx.exception.err_cd, "BAD_STORE")

    def test_zero_quantity_at_other_store(self) -> None:
        data = self.soap.get_part_availability("Westbrook Chevrolet", "12345")
        self.assertEqual(data["quantity_on_hand"], 0)
        self.assertEqual(data["availability"], "not_in_stock")

    def test_superseded_part(self) -> None:
        data = self.soap.get_part_availability("Lakeside Honda", "15400RTA")
        self.assertEqual(data["availability"], "superseded")
        self.assertEqual(data["superseded_by"], "12345")

    def test_missing_soapaction_is_a_fault(self) -> None:
        http = TestClient(self.app)
        # A body that would otherwise be a valid Login, but no SOAPAction header.
        body = (
            '<?xml version="1.0"?>'
            '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:dms="http://lakeside.example/dms">'
            "<soap:Body><dms:Login><dms:UserID>LAKESIDE_SVC</dms:UserID>"
            "<dms:Password>demo-not-a-secret</dms:Password></dms:Login></soap:Body>"
            "</soap:Envelope>"
        )
        response = http.post("/dms", content=body, headers={"Content-Type": "text/xml"})
        self.assertEqual(response.status_code, 500)
        self.assertIn("MISSING_SOAPACTION", response.text)

    def test_session_required_then_relogin_on_expiry(self) -> None:
        self.soap.login()
        token = self.soap.session_token
        self.assertTrue(token.startswith("SESS-"))
        self.state.expire_session(token)
        # The client should re-Login and still succeed.
        data = self.soap.get_part_availability("01", "12345")
        self.assertEqual(data["quantity_on_hand"], 14)
        self.assertNotEqual(self.soap.session_token, token)

    def test_flaky_part_is_retried(self) -> None:
        data = self.soap.get_part_availability("Lakeside Honda", FLAKY_PART_NUMBER)
        self.assertEqual(data["part_number"], FLAKY_PART_NUMBER)
        self.assertGreaterEqual(self.soap.last_retries, 1)

    def test_slow_part_still_returns(self) -> None:
        data = self.soap.get_part_availability("Lakeside Honda", SLOW_PART_NUMBER)
        self.assertEqual(data["bin_location"], "B-02-A")
        self.assertIn(SLOW_PART_NUMBER, PARTS[("01", SLOW_PART_NUMBER)]["PartNo"])


if __name__ == "__main__":
    unittest.main()
