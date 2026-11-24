"""Optional streamable-HTTP style endpoint for the same raw MCP server.

This is a simplified POST /mcp JSON in, JSON out transport. It is not a
full replica of every header and SSE path in the MCP HTTP spec, and it
is unauthenticated — fine for a local demo, not for production.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from erpbridge.server import McpServer
from erpbridge.settings import COMPANY, SERVER_NAME


def create_http_app(server: McpServer | None = None) -> FastAPI:
    mcp = server or McpServer()
    app = FastAPI(
        title=f"{SERVER_NAME} (MCP HTTP)",
        description=f"Optional HTTP JSON-RPC front door for the {COMPANY} demo MCP server.",
        docs_url=None,
        redoc_url=None,
    )
    app.state.mcp = mcp

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "transport": "http-jsonrpc", "server": SERVER_NAME}

    @app.post("/mcp")
    async def mcp_endpoint(request: Request) -> Response:
        raw = await request.body()
        response = mcp.handle_raw(raw)
        if response is None:
            return Response(status_code=202)
        return JSONResponse(response)

    return app


app = create_http_app()
