"""Raw MCP-to-ERP Bridge — Streamlit inspector UI.

Run with ./run.sh  (starts the mock SOAP DMS and this app)
"""

from __future__ import annotations

import json

import httpx
import streamlit as st

from erpbridge import log
from erpbridge.demo import DEMO_QUESTION, run_demo
from erpbridge.server import McpServer
from erpbridge.settings import COMPANY, soap_url
from erpbridge.soap_client import SoapClient
from erpbridge.soap_xml import pretty_xml
from erpbridge.tools import TOOLS

st.set_page_config(
    page_title="MCP-to-ERP Bridge",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
  .block-container { padding-top: 1.2rem; max-width: 1440px; }
  .demo-banner {
    background: #fff6e5;
    border: 1px solid #e6d2a8;
    color: #5a4500;
    padding: 0.7rem 1rem;
    border-radius: 8px;
    font-size: 0.95rem;
    margin-bottom: 0.8rem;
  }
  .panel {
    background: #fff;
    border: 1px solid #d5dbe3;
    border-radius: 10px;
    padding: 0.75rem 0.9rem 0.6rem;
    margin-bottom: 0.7rem;
    min-height: 12rem;
  }
  .panel-label {
    font-size: 11px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #4a5a70;
    font-weight: 700;
    margin: 0 0 0.4rem;
  }
  .panel pre {
    white-space: pre !important;
    word-break: normal !important;
    overflow-wrap: normal !important;
    font-size: 0.75rem;
    line-height: 1.4;
    margin: 0;
    color: #1c2430;
    max-height: 22rem;
    overflow: auto;
  }
  .answer-box {
    background: #eef5f2;
    border: 1px solid #b7d4c8;
    color: #1c2430;
    padding: 0.8rem 1rem;
    border-radius: 8px;
    margin-bottom: 0.9rem;
  }
  .ok { color: #2a7f6f; font-weight: 700; }
  .warn { color: #8a5a00; font-weight: 700; }
  .bad { color: #9b2c2c; font-weight: 700; }
  h1 { letter-spacing: -0.02em; }
  div[data-testid="stMetric"] {
    background: #f3f5f8;
    border: 1px solid #d5dbe3;
    border-radius: 10px;
    padding: 8px 12px;
  }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _panel(label: str, text: str, language: str = "text") -> None:
    st.markdown(f'<div class="panel-label">{label}</div>', unsafe_allow_html=True)
    st.code(text or "(none)", language=language)


def _pretty_json(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return value
    return json.dumps(value, indent=2)


@st.cache_resource
def _server() -> McpServer:
    return McpServer(client=SoapClient())


def _soap_up() -> bool:
    try:
        resp = httpx.get(soap_url().rsplit("/", 1)[0] + "/health", timeout=0.6)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _ensure_init(server: McpServer) -> None:
    if server.initialized:
        return
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": "ui-init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "erpbridge-inspector", "version": "0.1.0"},
            },
        }
    )
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})


def _call_tool(server: McpServer, name: str, arguments: dict) -> dict:
    _ensure_init(server)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": f"ui-{name}",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    return response or {}


server = _server()
soap_up = _soap_up()

with st.sidebar:
    st.header("How this works")
    st.markdown(
        """
A dealership's system of record — the **DMS** — often still speaks **SOAP**,
with odd field names, string-encoded quantities, and a session token.

This **MCP bridge** is the translator. An agent sends a clean JSON-RPC tool
call. The bridge turns that into SOAP, talks to a mock Lakeside DMS, and
hands back clean JSON. Writes stay off unless you pass `confirm=true`.
        """
    )
    st.markdown("---")
    st.markdown("**Scripted agent question**")
    st.caption(DEMO_QUESTION)
    if st.button("Run the agent question", type="primary", use_container_width=True):
        st.session_state["autorun"] = True
    st.markdown("---")
    st.subheader("Try one tool")
    tool_names = [t["name"] for t in TOOLS]
    tool = st.selectbox("Tool", tool_names, index=0)
    store = st.text_input("Store", value="Lakeside Honda")
    if tool == "get_part_availability":
        part_number = st.text_input("Part number", value="12345")
        args = {"store": store, "part_number": part_number}
    elif tool == "get_repair_order":
        ro_number = st.text_input("RO number", value="7781")
        args = {"store": store, "ro_number": ro_number}
    elif tool == "get_customer_vehicle":
        vin = st.text_input("VIN", value="1LKSDM26XMCB00001")
        args = {"vin": vin}
    else:
        part_number = st.text_input("Part number", value="12345")
        quantity = st.number_input("Quantity", min_value=1, value=1, step=1)
        charge_to_ro = st.text_input("Charge to RO (optional)", value="7781")
        confirm = st.checkbox("confirm=true (required to actually order)", value=False)
        args = {
            "store": store,
            "part_number": part_number,
            "quantity": int(quantity),
            "charge_to_ro": charge_to_ro or None,
            "confirm": confirm,
        }
        args = {k: v for k, v in args.items() if v is not None}
    if st.button("Call tool", use_container_width=True):
        _call_tool(server, tool, args)
        st.session_state["autorun"] = False
        st.session_state["demo_answer"] = None
        st.session_state["focus"] = 0
        st.rerun()
    st.markdown("---")
    st.markdown("**DMS status**")
    if soap_up:
        st.markdown(f'<span class="ok">Mock SOAP DMS is up</span> at `{soap_url()}`', unsafe_allow_html=True)
        st.caption("WSDL: " + soap_url() + "?wsdl")
    else:
        st.markdown('<span class="bad">Mock SOAP DMS is not reachable.</span> Start with `./run.sh`.', unsafe_allow_html=True)
    st.markdown("---")
    st.caption(f"Portfolio demo for Daniel McBrearty · {COMPANY}")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Raw MCP-to-ERP Bridge")
st.caption(
    "A raw JSON-RPC MCP server that translates clean tool calls into the "
    "quirky SOAP a dealership DMS still speaks."
)
st.markdown(
    '<div class="demo-banner">'
    "<strong>Honest label:</strong> this is a demo for "
    f"{COMPANY}. The DMS is a <em>mock</em> SOAP 1.1 service on this machine, "
    "not CDK, Reynolds, or any real dealer system. Placing a parts order only "
    "writes a simulated record locally. No paid APIs are used. The MCP protocol "
    "is implemented by hand over JSON-RPC 2.0, not through a high-level SDK."
    "</div>",
    unsafe_allow_html=True,
)

# Auto-run the featured question once so the four panels are filled on first open.
if "did_autorun" not in st.session_state:
    st.session_state["did_autorun"] = False
if (not st.session_state["did_autorun"] or st.session_state.get("autorun")) and soap_up:
    demo = run_demo(server)
    st.session_state["demo_answer"] = demo["answer"]
    st.session_state["did_autorun"] = True
    st.session_state["autorun"] = False
    # Prefer the part lookup in the talk-track screenshot and first view.
    focus = 0
    for i, item in enumerate(log.entries()):
        if item.get("tool") == "get_part_availability" and not item.get("is_error"):
            focus = i
            break
    st.session_state["focus"] = focus

answer = st.session_state.get("demo_answer")
if answer:
    st.markdown(
        f'<div class="answer-box"><strong>Agent question:</strong> { _escape(DEMO_QUESTION) }'
        f"<br><strong>Answer:</strong> {_escape(answer)}</div>",
        unsafe_allow_html=True,
    )

entries = log.entries()
if not entries:
    st.info("No calls yet. Run the agent question or call a tool from the sidebar.")
else:
    labels = []
    for item in entries:
        name = item.get("tool") or "call"
        status = "error" if item.get("is_error") else "ok"
        labels.append(f"#{item.get('id')}  {name}  ({status})")
    default = st.session_state.get("focus", 0)
    if default >= len(labels):
        default = 0
    chosen = st.selectbox("Request log (newest first)", labels, index=default)
    entry = entries[labels.index(chosen)]

    jsonrpc = _pretty_json(entry.get("jsonrpc_request"))
    soap_req = pretty_xml(entry.get("soap_request") or "") or (entry.get("soap_request") or "")
    soap_resp = pretty_xml(entry.get("soap_response") or "") or (entry.get("soap_response") or "")
    if entry.get("is_error"):
        clean = entry.get("error") or "Tool error"
    else:
        clean = _pretty_json(entry.get("result"))
    if not soap_req and entry.get("is_error"):
        soap_req = "(no SOAP was sent)"
    if not soap_resp and entry.get("is_error"):
        soap_resp = "(no SOAP response)"

    top_left, top_right = st.columns(2)
    with top_left:
        _panel("JSON-RPC request", jsonrpc, "json")
    with top_right:
        _panel("SOAP XML sent to the DMS", soap_req, "xml")
    bottom_left, bottom_right = st.columns(2)
    with bottom_left:
        _panel("Raw SOAP response", soap_resp, "xml")
    with bottom_right:
        _panel("Clean JSON returned to the agent", clean, "json")

    if entry.get("retries"):
        st.caption(f"The SOAP client retried {entry['retries']} time(s) before this result.")
