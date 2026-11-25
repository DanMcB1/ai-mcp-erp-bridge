# Raw MCP-to-ERP Bridge

**Portfolio project #5 of 12** from [@suraj_sharma14's FDE project list](https://x.com/suraj_sharma14/status/2125197762752806998).

A small, local demo of a **bridge** that lets an AI agent talk to a legacy dealership system. The agent speaks **MCP** (JSON-RPC 2.0 tools with clean JSON). The system of record still speaks **SOAP 1.1**, with odd field names, string-encoded quantities, and a session token from a Login call. This repo is the translator in the middle.

This is a **portfolio demo**, not production software and not a real DMS integration. The ERP/DMS is a **mock SOAP service** that runs on this machine. It is not CDK, Reynolds, Dealertrack, or any vendor system. Placing a parts order only writes a simulated record locally. No paid APIs are used. The MCP protocol itself is implemented **by hand** — that is the “raw” in the name — and tests can cross-check it with the official Python MCP SDK client.

Built for **Daniel McBrearty** as part of a Forward Deployed Engineer / solutions engineer portfolio. The sample company is **Lakeside Auto Group**, the same fictional mid-size dealer group used in the other portfolio demos.

## Why this matters for FDE work

Enterprise data rarely lives in a clean new API. In a dealer group it lives in the **DMS**: parts inventory, open repair orders, customer vehicles. Those integrations are the ones that slip timelines, because the field names are 20 years old, the numbers come back as strings, and you need a session token that expires mid-call.

An FDE is often the person who has to make an assistant *usable* against that system without asking the customer to rewrite it, and without letting the model fire a write it did not mean to fire. MCP is a good contract for that: here are the tools, here is the schema, here is a flag that a parts order will not go through unless you confirm it.

This demo shows that translation on one screen, using a Lakeside Honda oil filter and repair order 7781.

## Quick start

You need Python 3.10+ (3.13 is fine) and a network connection the first time (to install packages). No cloud account, no vendor DMS, no signup.

```bash
git clone https://github.com/DanMcB1/ai-mcp-erp-bridge.git
cd ai-mcp-erp-bridge
./run.sh
```

Then open [http://127.0.0.1:8505](http://127.0.0.1:8505). The script creates a local virtualenv, starts the mock SOAP DMS on port **8005**, and starts the Streamlit inspector on port **8505**. The featured agent question runs on first load so the four panels are already filled.

Useful one-liners, once the venv exists and the mock DMS is running:

```bash
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m erpbridge demo
.venv/bin/python -m erpbridge stdio
.venv/bin/python -m erpbridge serve-http
```

`demo` prints a plain-English answer to *“Is part 12345 in stock at Lakeside Honda and what's on RO 7781?”*. `stdio` is the MCP server over standard input and output. It speaks newline-delimited JSON-RPC (what the official Python SDK uses) and also accepts LSP-style Content-Length framing. `serve-http` is an optional POST `/mcp` JSON-RPC endpoint on port **8105**.

## What’s on the screen

- An honest banner that this is a demo, and that the DMS is a mock
- The scripted agent question and a plain-English answer
- Four panels side by side: **JSON-RPC request**, **SOAP XML sent to the DMS**, **raw SOAP response**, and **clean JSON returned to the agent**
- A request log so you can flip between the part lookup, the repair order, and a write
- A sidebar to run one tool at a time, including `create_parts_order` with a `confirm` checkbox that stays off until you turn it on

## How it works

```
Agent / inspector
    │  JSON-RPC 2.0 (MCP: initialize, tools/list, tools/call)
    ▼
MCP bridge  (this repo; protocol written by hand)
    │  maps clean JSON ↔ quirky SOAP
    │  Login / SessTok, retries, timeouts
    │  create_parts_order requires confirm=true
    ▼
Mock DMS  (SOAP 1.1 + WSDL on /dms)
    │
    ▼
Parts, repair orders, customer vehicles
```

1. **Mock DMS.** A FastAPI endpoint accepts SOAP 1.1 envelopes and serves a WSDL at `/dms?wsdl`. Operations are `Login`, `GetPartAvailability`, `GetRepairOrder`, `CreatePartsOrder`, and `GetCustomerVehicle`. The quirks are intentional: a required `SOAPAction` header, a `SessTok` from Login, field names like `StoreNum` and `QtyOnHand`, quantities as strings (`"14.0000"`), dates as `YYYYMMDD`, status codes like `"O"`, a slow part number, a flaky part that fails once and then succeeds, and SOAP 1.1 faults with an `ErrCd`.
2. **Raw MCP server.** `erpbridge/protocol.py` and `erpbridge/server.py` speak JSON-RPC 2.0 directly. There is no high-level MCP framework on the server path. The server implements `initialize`, `notifications/initialized`, `tools/list`, `tools/call`, `resources/list`, `resources/read`, and `ping`. Transport is stdio with Content-Length framing, plus an optional HTTP JSON-RPC endpoint.
3. **Tools.** Each SOAP operation is wrapped in a clean JSON schema (`store` and `part_number`, not `StoreNum` and `PartNo`). Arguments are validated. SOAP faults become MCP tool errors (`isError: true`) with the `ErrCd` in the message. The SOAP client logs in on first use, re-logins if the session expired, and retries transient faults and timeouts.
4. **Write guard.** `create_parts_order` is read-blocked by default. Unless `confirm` is the boolean `true`, the tool returns an error and **does not send SOAP**. That is the same instinct as a parts counter that does not special-order until you say go.
5. **Inspector and demo client.** The Streamlit app shows the four layers of a call. `python -m erpbridge demo` runs the scripted question without the UI.

## Honest limitations

- This is a **demo**. Lakeside Auto Group is fictional. The oil filter SKU `12345`, RO `7781`, and VIN `1LKSDM26XMCB00001` are sample data, reused across these portfolio projects.
- The DMS is **not** a vendor product. The WSDL was written for this repo. A real CDK or Reynolds WSDL is larger, stricter, and usually under NDA.
- The MCP server is a **hand-rolled subset** of the spec: the methods above, standard JSON-RPC error codes, stdio framing, and a simple HTTP POST. It does not implement every MCP feature (prompts, sampling, completions, the full streamable-HTTP / SSE path, OAuth).
- The optional HTTP MCP endpoint has **no authentication**.
- Demo Login credentials (`LAKESIDE_SVC` / `demo-not-a-secret`) are in the source on purpose and are not a secret.
- “Placing an order” appends a row in memory and decrements a mock on-hand quantity. Nothing is purchased and no parts counter is notified.
- Timeouts, retries, and the flaky/slow part numbers are small and deterministic so the tests stay fast. They are not a production resilience design.
- Identity is whatever the local process is. There is no SSO, no per-store authorization, and no audit export beyond a local JSONL log.

## What a production version would add

- The customer’s real WSDL, generated client stubs, and a written mapping of every field, including the ones that do not fit a clean JSON type
- Authentication to both the MCP front door (OAuth, mTLS, or a network policy) and the DMS (service accounts in a vault, not a demo password)
- Rate limits, a circuit breaker, and backoff that respects the vendor’s published limits
- Observability: traces that tie one agent tool call to the SOAP request, latency, and fault code, plus alerts when Login starts failing
- A stronger write path: role checks, an approval gate for irreversible orders, and idempotency keys so a retried tool call does not double-order
- Store-level authorization so a Lakeside Honda advisor cannot write to another rooftop’s inventory
- Contract tests against a vendor sandbox, and a staging environment that is not this mock

## Project layout

```
ai-mcp-erp-bridge/
  app.py                 Streamlit inspector (JSON-RPC / SOAP / JSON panels)
  run.sh                 Starts the mock DMS and the UI
  requirements.txt
  README.md
  LICENSE                MIT, Copyright (c) 2026 Daniel McBrearty
  DEMO_SCRIPT.md
  erpbridge/             Raw JSON-RPC MCP server, SOAP client, mock DMS
  tests/
  examples/
  screenshots/
  data/                  Request log and process ids (gitignored)
```

## For interviewers

Start `./run.sh` and look at the four panels already filled for part 12345 and RO 7781. Point at `StoreNum`, `SessTok`, and `QtyOnHand` in the SOAP, then at `quantity_on_hand: 14` in the clean JSON. If there is time, use the sidebar to call `create_parts_order` with the confirm box off, then on, and show that SOAP only appears when confirm is true. The talk track is in [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

Daniel’s background is car sales, F&I, and auto software sales (Dealr.cloud), not professional protocol engineering. This project is meant to show he understands **why enterprise data still lives in SOAP, how MCP gives an agent a safe contract in front of it, and why a parts order should not go through until someone confirms it**.

## License

This project is released under the [MIT License](LICENSE). Copyright (c) 2026 Daniel McBrearty.
