"""Raw JSON-RPC 2.0 helpers. No MCP framework.

This is the protocol core the rest of the server sits on: parse a message,
echo ids, return standard error codes, and stay silent on notifications.
"""

from __future__ import annotations

import json
from typing import Any

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

JSONRPC = "2.0"


def error_object(code: int, message: str, data: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return err


def success(msg_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": msg_id, "result": result}


def failure(msg_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC, "id": msg_id, "error": error_object(code, message, data)}


def is_notification(message: dict[str, Any]) -> bool:
    # JSON-RPC 2.0: a Notification is a Request object without an "id" member.
    return "id" not in message


def parse_jsonrpc(raw: str | bytes) -> tuple[Any, dict[str, Any] | None]:
    """Parse a JSON-RPC message.

    Returns (payload, error_response). If parsing fails, payload is None and
    error_response is a JSON-RPC error with a null id.
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, failure(None, PARSE_ERROR, "Parse error", str(exc))
    return payload, None


def validate_request(message: Any) -> dict[str, Any] | None:
    """Return a JSON-RPC error response if this is not a valid Request, else None.

    Notifications (no id) that are otherwise valid return None as well.
    """
    if isinstance(message, list):
        return failure(None, INVALID_REQUEST, "Batch requests are not supported")
    if not isinstance(message, dict):
        return failure(None, INVALID_REQUEST, "Request must be a JSON object")
    if message.get("jsonrpc") != JSONRPC:
        msg_id = message.get("id") if "id" in message else None
        # Notifications with a bad jsonrpc field still get no response.
        if "id" not in message:
            return None
        return failure(msg_id, INVALID_REQUEST, "jsonrpc must be '2.0'")
    if "method" not in message or not isinstance(message.get("method"), str) or not message["method"]:
        if "id" not in message:
            return None
        return failure(message.get("id"), INVALID_REQUEST, "method must be a non-empty string")
    params = message.get("params", {})
    if "params" in message and not isinstance(params, (dict, list)):
        if "id" not in message:
            return None
        return failure(message.get("id"), INVALID_PARAMS, "params must be an object or array")
    return None
