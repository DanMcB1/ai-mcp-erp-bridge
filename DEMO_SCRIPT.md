# Demo script (~1 minute)

A talk track you can say out loud in an interview. Plain language. Practice it once with the app open. You do not need to memorize it word for word.

**Setup:** `./run.sh` is already running. The four panels should already be filled with the Lakeside Honda part lookup (or click **Run the agent question** if they are not).

---

## The talk track

“When I was selling dealer software, the hardest integrations were never the new APIs. They were the DMS — the system of record for parts, repair orders, and inventory. Those systems still speak SOAP. The field names look like `StoreNum` and `QtyOnHand`, the quantities come back as strings like `14.0000`, and you have to keep a session token alive.

An AI agent can’t speak that natively, and you don’t want it to. MCP is a clean contract: here are the tools, here is the JSON schema. This bridge is the translator.

The question I ran is, ‘Is part 12345 in stock at Lakeside Honda, and what’s on RO 7781?’ The left panel is the JSON-RPC the agent sent. Next to it is the SOAP that actually went to the mock DMS — `SessTok`, `StoreNum`, `PartNo`. Then the raw SOAP response. And on the right, the clean JSON the agent gets back: 14 on hand, bin A-14-C, list price $12.85. The same pattern runs for the repair order: Maya Alvarez’s 2023 CR-V, still open, oil service on the lines.

The write path is locked down. Creating a parts order is a real side effect in a dealership. This tool will not call the DMS unless you pass `confirm=true`. That’s the same instinct as a parts counter that doesn’t special-order until you say go.”

---

## Timing notes

Spoken at a normal pace, that is about 50–60 seconds. If you have a few extra seconds, point at one concrete pair — `QtyOnHand` `14.0000` in the SOAP response and `quantity_on_hand: 14` in the clean JSON — then stop and let them ask questions.

If you have two minutes, switch the sidebar tool to **create_parts_order**, leave confirm unchecked, click **Call tool**, and show that the SOAP panel says no SOAP was sent. Then check confirm and run it again so a `PoNum` appears.

## If they ask a follow-up

- **“What is MCP?”**  
  “Model Context Protocol. It’s a JSON-RPC contract so an agent can discover tools and call them in a standard way. I’m not married to the acronym. The idea is: don’t make every model vendor learn your DMS.”

- **“Why implement it raw, instead of using a framework?”**  
  “Because on a real engagement you’re going to end up looking at the wire anyway — a bad id, a missing method, a notification that must not get a response. I wanted to show I understand that contract. The tests still use the official Python SDK as a client, so it’s not just talking to itself.”

- **“Why not just give the agent the WSDL?”**  
  “You can, and it will get lost in `StoreNum` and session tokens, or worse, it will call `CreatePartsOrder` because the WSDL said it could. A small tool list with validation, retries, and a confirm flag is a much safer thing to put in front of a model.”

- **“Is this a real CDK or Reynolds integration?”**  
  “No, and I label it as a mock. A real vendor WSDL is bigger and usually under NDA. What I’m showing is the pattern: sit a bridge in front of the old system, map the quirks, and keep writes from going out by accident.”

- **“What would you do on a real dealer group?”**  
  “Start with the operations the service and parts teams actually ask for — on-hand quantity, open ROs, vehicle by VIN — against their sandbox. Put real credentials in a vault. Add store-level authorization so Honda can’t write Toyota’s inventory. And put a human approval step in front of anything that creates an order or changes a customer record.”

- **“Does this work with Claude or Cursor?”**  
  “The stdio server speaks the same Content-Length JSON-RPC those clients use. You’d still need to point it at a real DMS and add auth. I would not hook this demo up to a production rooftop.”
