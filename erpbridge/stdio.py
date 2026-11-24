"""JSON-RPC over stdio.

The official MCP Python SDK exchanges newline-delimited JSON (one message
per line). Some older clients use LSP-style Content-Length framing. This
reader accepts both and replies in the same format as the request.
"""

from __future__ import annotations

import json
import sys
from typing import BinaryIO

from erpbridge.server import McpServer


def read_message(stream: BinaryIO) -> tuple[bytes | None, str]:
    """Read one JSON-RPC message. Returns (body, mode).

    mode is 'content-length' or 'ndjson'. On EOF, body is None.
    """
    line = stream.readline()
    if not line:
        return None, "ndjson"
    if line.lower().startswith(b"content-length:"):
        headers = {"content-length": line.split(b":", 1)[1].strip().decode("ascii", errors="replace")}
        while True:
            header_line = stream.readline()
            if not header_line or header_line in (b"\r\n", b"\n"):
                break
            try:
                key, value = header_line.decode("ascii", errors="replace").split(":", 1)
            except ValueError:
                continue
            headers[key.strip().lower()] = value.strip()
        try:
            length = int(headers["content-length"])
        except ValueError:
            return None, "content-length"
        body = stream.read(length)
        if len(body) < length:
            return None, "content-length"
        return body, "content-length"

    # Newline-delimited JSON. Skip blank lines that can appear around framed messages.
    while line in (b"\r\n", b"\n", b""):
        line = stream.readline()
        if not line:
            return None, "ndjson"
    return line.strip(), "ndjson"


def write_message(stream: BinaryIO, body: bytes, mode: str = "ndjson") -> None:
    if mode == "content-length":
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        stream.write(header + body)
    else:
        stream.write(body + b"\n")
    stream.flush()


def serve_stdio(server: McpServer | None = None, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> None:
    """Read JSON-RPC from stdin, write responses to stdout. Logs go to stderr."""
    mcp = server or McpServer()
    in_stream = stdin or sys.stdin.buffer
    out_stream = stdout or sys.stdout.buffer
    try:
        while True:
            raw, mode = read_message(in_stream)
            if raw is None:
                break
            if not raw:
                continue
            response = mcp.handle_raw(raw)
            if response is not None:
                payload = json.dumps(response, separators=(",", ":")).encode("utf-8")
                write_message(out_stream, payload, mode=mode)
    finally:
        mcp.close()
