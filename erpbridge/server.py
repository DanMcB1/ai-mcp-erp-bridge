"""Raw MCP server: JSON-RPC methods on top of protocol.py, no MCP SDK.

Implements initialize, notifications/initialized, tools/list, tools/call,
resources/list, resources/read, and ping. SOAP faults become MCP tool
errors (isError=true). Protocol mistakes use JSON-RPC error codes.
"""

from __future__ import annotations

import json
from typing import Any

from erpbridge import catalog, log
from erpbridge.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    METHOD_NOT_FOUND,
    failure,
    is_notification,
    parse_jsonrpc,
    success,
    validate_request,
)
from erpbridge.settings import (
    COMPANY,
    PREFERRED_PROTOCOL_VERSION,
    SERVER_NAME,
    SERVER_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from erpbridge.soap_client import SoapClient, SoapError
from erpbridge.soap_server import WSDL
from erpbridge.tools import (
    TOOLS,
    TOOLS_BY_NAME,
    WriteGuardError,
    call_tool,
    dump_result,
    validate_arguments,
)


class McpServer:
    def __init__(self, client: SoapClient | None = None) -> None:
        self.client = client or SoapClient()
        self.initialized = False
        self.protocol_version = PREFERRED_PROTOCOL_VERSION
        self.client_info: dict[str, Any] = {}

    def close(self) -> None:
        self.client.close()

    def handle_raw(self, raw: str | bytes) -> dict[str, Any] | None:
        payload, error = parse_jsonrpc(raw)
        if error is not None:
            return error
        invalid = validate_request(payload)
        if invalid is not None:
            return invalid
        assert isinstance(payload, dict)
        return self.handle(payload)

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch one already-parsed JSON-RPC message. Notifications return None."""
        invalid = validate_request(message)
        if invalid is not None:
            return invalid
        method = message["method"]
        params = message.get("params") or {}
        if not isinstance(params, dict):
            if is_notification(message):
                return None
            return failure(message.get("id"), INVALID_PARAMS, "params must be an object")
        notify = is_notification(message)
        msg_id = message.get("id") if not notify else None

        try:
            result = self._dispatch(method, params, notify=notify)
        except KeyError:
            if notify:
                return None
            return failure(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        except ValueError as exc:
            if notify:
                return None
            return failure(msg_id, INVALID_PARAMS, str(exc))
        except Exception as exc:
            if notify:
                return None
            return failure(msg_id, INTERNAL_ERROR, "Internal error", str(exc))

        if notify:
            return None
        return success(msg_id, result)

    def _dispatch(self, method: str, params: dict[str, Any], notify: bool) -> Any:
        if method == "initialize":
            return self._initialize(params)
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return {}
        if method == "tools/list":
            self._require_initialized()
            return {"tools": TOOLS}
        if method == "tools/call":
            self._require_initialized()
            return self._call_tool(params)
        if method == "resources/list":
            self._require_initialized()
            return {"resources": _RESOURCES}
        if method == "resources/read":
            self._require_initialized()
            return self._read_resource(params)
        if method.startswith("notifications/"):
            return None
        raise KeyError(method)

    def _require_initialized(self) -> None:
        if not self.initialized:
            raise ValueError("Server is not initialized. Send initialize first.")

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion") or PREFERRED_PROTOCOL_VERSION
        if requested in SUPPORTED_PROTOCOL_VERSIONS:
            self.protocol_version = requested
        else:
            self.protocol_version = PREFERRED_PROTOCOL_VERSION
        self.client_info = params.get("clientInfo") or {}
        self.initialized = True
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
            "instructions": (
                f"Demo MCP bridge for {COMPANY}. Tools talk to a mock SOAP DMS. "
                "Data is fictional. create_parts_order is a write and requires confirm=true."
            ),
        }

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name or not isinstance(name, str):
            raise ValueError("tools/call requires params.name")
        if name not in TOOLS_BY_NAME:
            raise ValueError(f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise ValueError("params.arguments must be an object")

        schema_error = validate_arguments(name, arguments)
        if schema_error:
            return _tool_error(schema_error)

        jsonrpc_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        request_xml = ""
        response_xml = ""
        retries = 0
        error_text = None
        is_error = False
        payload: dict[str, Any] | None = None

        try:
            payload = call_tool(name, arguments, self.client)
            text = dump_result(payload)
        except WriteGuardError as exc:
            is_error = True
            error_text = str(exc)
            text = error_text
        except SoapError as exc:
            is_error = True
            error_text = f"DMS error {exc.err_cd}: {exc}"
            text = error_text
            request_xml = exc.request_xml or self.client.last_request_xml
            response_xml = exc.response_xml or self.client.last_response_xml
        else:
            request_xml = self.client.last_request_xml
            response_xml = self.client.last_response_xml
        retries = self.client.last_retries

        result: dict[str, Any] = {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        }
        if payload is not None and not is_error:
            result["structuredContent"] = payload

        log.record(
            {
                "tool": name,
                "jsonrpc_request": jsonrpc_request,
                "arguments": arguments,
                "soap_request": request_xml,
                "soap_response": response_xml,
                "result": payload,
                "error": error_text,
                "is_error": is_error,
                "retries": retries,
            }
        )
        return result

    def _read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri")
        if not uri:
            raise ValueError("resources/read requires params.uri")
        for resource in _RESOURCES:
            if resource["uri"] == uri:
                text = _resource_text(uri)
                return {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": resource["mimeType"],
                            "text": text,
                        }
                    ]
                }
        raise ValueError(f"Unknown resource: {uri}")


_RESOURCES = [
    {
        "uri": "dms://stores",
        "name": "Lakeside Auto Group stores",
        "description": "The fictional rooftops in this demo DMS, with their StoreNum values.",
        "mimeType": "application/json",
    },
    {
        "uri": "dms://wsdl",
        "name": "Mock DMS WSDL",
        "description": "The WSDL served by the mock SOAP endpoint at /dms?wsdl.",
        "mimeType": "text/xml",
    },
]


def _resource_text(uri: str) -> str:
    if uri == "dms://stores":
        stores = [
            {"store_number": num, "name": meta["name"], "city": meta["city"]}
            for num, meta in catalog.STORES.items()
        ]
        return json.dumps(stores, indent=2)
    if uri == "dms://wsdl":
        return WSDL
    return ""


def _tool_error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }


def new_server(client: SoapClient | None = None) -> McpServer:
    return McpServer(client=client)
