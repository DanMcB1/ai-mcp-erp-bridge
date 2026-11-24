"""MCP tool definitions and handlers that wrap the SOAP DMS operations."""

from __future__ import annotations

import json
from typing import Any, Callable

from erpbridge.soap_client import SoapClient, SoapError

ToolHandler = Callable[[dict[str, Any], SoapClient], dict[str, Any]]


def _schema(properties: dict, required: list[str], description: str) -> dict:
    return {
        "type": "object",
        "description": description,
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_part_availability",
        "description": (
            "Look up parts inventory at a Lakeside Auto Group store. "
            "Use a store name like 'Lakeside Honda' or a store number like '01'. "
            "Returns on-hand quantity, price, bin location, and whether the part is superseded."
        ),
        "inputSchema": _schema(
            {
                "store": {
                    "type": "string",
                    "description": "Store name or number, e.g. 'Lakeside Honda' or '01'.",
                },
                "part_number": {
                    "type": "string",
                    "description": "Part number as used in the DMS, e.g. '12345'.",
                },
                "manufacturer": {
                    "type": "string",
                    "description": "Optional manufacturer code, e.g. 'HON'.",
                },
            },
            ["store", "part_number"],
            "Part availability lookup.",
        ),
    },
    {
        "name": "get_repair_order",
        "description": (
            "Fetch a service repair order (RO) including vehicle, customer, "
            "opcodes, labor and parts totals, and line items."
        ),
        "inputSchema": _schema(
            {
                "store": {
                    "type": "string",
                    "description": "Store name or number, e.g. 'Lakeside Honda' or '01'.",
                },
                "ro_number": {
                    "type": "string",
                    "description": "Repair order number, e.g. '7781'.",
                },
            },
            ["store", "ro_number"],
            "Repair order lookup.",
        ),
    },
    {
        "name": "get_customer_vehicle",
        "description": (
            "Look up a customer vehicle by VIN or customer number. "
            "Returns year, make, model, mileage, and last service date."
        ),
        "inputSchema": _schema(
            {
                "vin": {"type": "string", "description": "17-character VIN."},
                "customer_number": {
                    "type": "string",
                    "description": "DMS customer number, e.g. 'C-44108'.",
                },
            },
            [],
            "Customer vehicle lookup. Provide vin or customer_number.",
        ),
    },
    {
        "name": "create_parts_order",
        "description": (
            "Place a parts order at a Lakeside store. This is a WRITE. "
            "It will not call the DMS unless confirm is true. "
            "Use get_part_availability first to check stock."
        ),
        "inputSchema": _schema(
            {
                "store": {
                    "type": "string",
                    "description": "Store name or number, e.g. 'Lakeside Honda' or '01'.",
                },
                "part_number": {"type": "string", "description": "Part number to order."},
                "quantity": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "How many units to order. Must be at least 1.",
                },
                "charge_to_ro": {
                    "type": "string",
                    "description": "Optional repair order to charge, e.g. '7781'.",
                },
                "vendor": {"type": "string", "description": "Optional vendor code, e.g. 'HON'."},
                "confirm": {
                    "type": "boolean",
                    "description": (
                        "Must be confirm=true to actually place the order. "
                        "The tool refuses and does not call the DMS if this is missing or false."
                    ),
                },
            },
            ["store", "part_number", "quantity"],
            "Write tool. Requires confirm=true.",
        ),
    },
]

TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def validate_arguments(name: str, arguments: dict[str, Any]) -> str | None:
    """Return a human-readable schema error, or None if the arguments are ok."""
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    schema = tool["inputSchema"]
    required = schema.get("required") or []
    properties = schema.get("properties") or {}
    if not isinstance(arguments, dict):
        return "arguments must be an object"
    missing = [key for key in required if key not in arguments or arguments[key] in (None, "")]
    if missing:
        return f"Missing required field(s): {', '.join(missing)}"
    if schema.get("additionalProperties") is False:
        unknown = [key for key in arguments if key not in properties]
        if unknown:
            return f"Unexpected field(s): {', '.join(unknown)}"
    for key, value in arguments.items():
        if key not in properties:
            continue
        expected = properties[key].get("type")
        if expected == "string" and not isinstance(value, str):
            return f"{key} must be a string"
        if expected == "integer" and not (isinstance(value, int) and not isinstance(value, bool)):
            return f"{key} must be an integer"
        if expected == "boolean" and not isinstance(value, bool):
            return f"{key} must be a boolean"
        if expected == "integer" and "minimum" in properties[key] and value < properties[key]["minimum"]:
            return f"{key} must be at least {properties[key]['minimum']}"
    if name == "get_customer_vehicle":
        if not (arguments.get("vin") or arguments.get("customer_number")):
            return "Provide vin or customer_number"
    return None


def _get_part(arguments: dict[str, Any], client: SoapClient) -> dict[str, Any]:
    return client.get_part_availability(
        store=arguments["store"],
        part_number=arguments["part_number"],
        manufacturer=arguments.get("manufacturer"),
    )


def _get_ro(arguments: dict[str, Any], client: SoapClient) -> dict[str, Any]:
    return client.get_repair_order(
        store=arguments["store"],
        ro_number=str(arguments["ro_number"]),
    )


def _get_vehicle(arguments: dict[str, Any], client: SoapClient) -> dict[str, Any]:
    return client.get_customer_vehicle(
        vin=arguments.get("vin"),
        customer_number=arguments.get("customer_number"),
    )


def _create_order(arguments: dict[str, Any], client: SoapClient) -> dict[str, Any]:
    if arguments.get("confirm") is not True:
        raise WriteGuardError(
            "create_parts_order is a write tool. It will not call the DMS "
            "unless you pass confirm=true. No parts order was placed."
        )
    return client.create_parts_order(
        store=arguments["store"],
        part_number=arguments["part_number"],
        quantity=arguments["quantity"],
        charge_to_ro=arguments.get("charge_to_ro"),
        vendor=arguments.get("vendor"),
    )


class WriteGuardError(Exception):
    """Raised when a write tool is called without an explicit confirm=true."""


HANDLERS: dict[str, ToolHandler] = {
    "get_part_availability": _get_part,
    "get_repair_order": _get_ro,
    "get_customer_vehicle": _get_vehicle,
    "create_parts_order": _create_order,
}


def call_tool(name: str, arguments: dict[str, Any], client: SoapClient) -> dict[str, Any]:
    """Run a tool and return either a clean payload or raise SoapError / WriteGuardError."""
    handler = HANDLERS[name]
    return handler(arguments, client)


def dump_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2)
