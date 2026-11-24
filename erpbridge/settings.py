"""Demo settings and environment knobs."""

from __future__ import annotations

import os

COMPANY = "Lakeside Auto Group (sample)"
SERVER_NAME = "lakeside-dms-bridge"
SERVER_VERSION = "0.1.0"

# MCP protocol versions this raw server will negotiate.
SUPPORTED_PROTOCOL_VERSIONS = (
    "2024-11-05",
    "2025-03-26",
    "2025-06-18",
    "2025-11-25",
)
PREFERRED_PROTOCOL_VERSION = "2025-06-18"

# Demo DMS credentials. Obviously not a secret — labeled as such in the UI and README.
DEMO_USER = "LAKESIDE_SVC"
DEMO_PASSWORD = "demo-not-a-secret"

DEFAULT_SOAP_HOST = "127.0.0.1"
DEFAULT_SOAP_PORT = 8005
DEFAULT_UI_PORT = 8505
DEFAULT_MCP_HTTP_PORT = 8105

SOAP_TIMEOUT_SECONDS = 2.0
SOAP_RETRIES = 2  # retries after the first attempt (3 tries total) on transient faults/timeouts
SESSION_TTL_SECONDS = 900

# Intentional quirk: one part number is slow on the mock DMS.
SLOW_PART_NUMBER = "SLOW99"
SLOW_PART_DELAY_SECONDS = 0.35
# Intentional quirk: this part faults once, then succeeds, to show retries.
FLAKY_PART_NUMBER = "FLAKY99"


def soap_host() -> str:
    return os.environ.get("ERPBRIDGE_SOAP_HOST", DEFAULT_SOAP_HOST)


def soap_port() -> int:
    return int(os.environ.get("ERPBRIDGE_SOAP_PORT", str(DEFAULT_SOAP_PORT)))


def soap_url() -> str:
    if os.environ.get("ERPBRIDGE_SOAP_URL"):
        return os.environ["ERPBRIDGE_SOAP_URL"]
    return f"http://{soap_host()}:{soap_port()}/dms"


def ui_port() -> int:
    return int(os.environ.get("ERPBRIDGE_UI_PORT", str(DEFAULT_UI_PORT)))


def mcp_http_port() -> int:
    return int(os.environ.get("ERPBRIDGE_MCP_HTTP_PORT", str(DEFAULT_MCP_HTTP_PORT)))


def data_dir() -> str:
    override = os.environ.get("ERPBRIDGE_DATA_DIR")
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
