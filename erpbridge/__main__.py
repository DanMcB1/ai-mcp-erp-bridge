"""CLI: python -m erpbridge serve-soap | serve-http | stdio | demo."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="erpbridge",
        description="Raw MCP-to-ERP bridge (portfolio demo for Lakeside Auto Group).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    soap = sub.add_parser("serve-soap", help="Start the mock SOAP 1.1 DMS")
    soap.add_argument("--host", default=None)
    soap.add_argument("--port", type=int, default=None)

    http = sub.add_parser("serve-http", help="Start the optional MCP HTTP JSON-RPC endpoint")
    http.add_argument("--host", default=None)
    http.add_argument("--port", type=int, default=None)

    sub.add_parser("stdio", help="Start the MCP server over stdio (Content-Length framing)")
    sub.add_parser("demo", help="Run the scripted agent question about part 12345 and RO 7781")

    args = parser.parse_args(argv)

    if args.cmd == "serve-soap":
        import uvicorn

        from erpbridge.settings import soap_host, soap_port

        uvicorn.run(
            "erpbridge.soap_server:app",
            host=args.host or soap_host(),
            port=args.port or soap_port(),
            reload=False,
        )
        return 0

    if args.cmd == "serve-http":
        import uvicorn

        from erpbridge.settings import soap_host, mcp_http_port

        uvicorn.run(
            "erpbridge.http_transport:app",
            host=args.host or soap_host(),
            port=args.port or mcp_http_port(),
            reload=False,
        )
        return 0

    if args.cmd == "stdio":
        from erpbridge.stdio import serve_stdio

        serve_stdio()
        return 0

    if args.cmd == "demo":
        from erpbridge.demo import run_and_print

        return run_and_print()

    return 1


if __name__ == "__main__":
    sys.exit(main())
