"""Scripted demo client: an agent asks about part 12345 and RO 7781."""

from __future__ import annotations

import json
from typing import Any

from erpbridge.server import McpServer
from erpbridge.soap_client import SoapClient

DEMO_QUESTION = "Is part 12345 in stock at Lakeside Honda and what's on RO 7781?"


def _text(result: dict[str, Any]) -> str:
    content = result.get("content") or []
    if content and isinstance(content[0], dict):
        return content[0].get("text") or ""
    return ""


def _payload(result: dict[str, Any]) -> dict[str, Any] | None:
    if result.get("structuredContent"):
        return result["structuredContent"]
    raw = _text(result)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def run_demo(server: McpServer | None = None) -> dict[str, Any]:
    """Initialize the MCP server and run the two-tool demo question."""
    mcp = server or McpServer()
    init = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "erpbridge-demo", "version": "0.1.0"},
            },
        }
    )
    mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    part = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "get_part_availability",
                "arguments": {"store": "Lakeside Honda", "part_number": "12345"},
            },
        }
    )
    ro = mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "get_repair_order",
                "arguments": {"store": "Lakeside Honda", "ro_number": "7781"},
            },
        }
    )
    assert init and part and ro
    part_payload = _payload(part["result"]) if "result" in part else None
    ro_payload = _payload(ro["result"]) if "result" in ro else None
    answer = compose_answer(part_payload, ro_payload, part, ro)
    return {
        "question": DEMO_QUESTION,
        "answer": answer,
        "initialize": init,
        "part": part,
        "repair_order": ro,
        "part_payload": part_payload,
        "ro_payload": ro_payload,
    }


def compose_answer(
    part: dict[str, Any] | None,
    ro: dict[str, Any] | None,
    part_rpc: dict[str, Any] | None = None,
    ro_rpc: dict[str, Any] | None = None,
) -> str:
    lines: list[str] = []
    if part and not (part_rpc or {}).get("result", {}).get("isError"):
        qty = part.get("quantity_on_hand")
        store = part.get("store")
        desc = part.get("description")
        price = part.get("list_price")
        bin_loc = part.get("bin_location")
        avail = part.get("availability")
        if avail == "in_stock":
            stock = f"Yes. Part 12345 ({desc}) is in stock at {store}: {qty} on hand"
        elif avail == "superseded":
            stock = (
                f"Part 12345 is superseded at {store}. "
                f"Use {part.get('superseded_by')} instead."
            )
        else:
            stock = f"Part 12345 ({desc}) is not on the shelf at {store} right now."
        extras = []
        if price is not None:
            extras.append(f"list price ${price:.2f}" if isinstance(price, (int, float)) else f"list price {price}")
        if bin_loc:
            extras.append(f"bin {bin_loc}")
        if extras:
            stock += " (" + ", ".join(extras) + ")"
        stock += "."
        lines.append(stock)
    else:
        err = _text((part_rpc or {}).get("result") or {}) or "the part lookup failed"
        lines.append(f"I could not check part 12345: {err}")

    if ro and not (ro_rpc or {}).get("result", {}).get("isError"):
        vehicle = " ".join(
            str(bit) for bit in (ro.get("year"), ro.get("make"), ro.get("model")) if bit
        )
        lines.append(
            f"RO 7781 is {ro.get('status')} at {ro.get('store')} for {ro.get('customer_name')}'s "
            f"{vehicle} (VIN {ro.get('vin')}, {ro.get('mileage')} miles). "
            f"Advisor {ro.get('advisor')}. Labor ${ro.get('labor_amount'):.2f}, "
            f"parts ${ro.get('parts_amount'):.2f}."
        )
    else:
        err = _text((ro_rpc or {}).get("result") or {}) or "the repair-order lookup failed"
        lines.append(f"I could not load RO 7781: {err}")
    return " ".join(lines)


def print_demo(result: dict[str, Any]) -> None:
    print(f"Agent question: {result['question']}")
    print()
    print(result["answer"])
    print()
    print("The inspector UI shows the JSON-RPC, the SOAP XML that went to the")
    print("mock DMS, the raw SOAP response, and this clean JSON for each call.")


def run_and_print(client: SoapClient | None = None) -> int:
    server = McpServer(client=client) if client is not None else McpServer()
    try:
        result = run_demo(server)
    except Exception as exc:
        print(f"Demo failed: {exc}")
        print("Is the mock SOAP DMS running? Try ./run.sh or python -m erpbridge serve-soap")
        return 1
    print_demo(result)
    return 0
