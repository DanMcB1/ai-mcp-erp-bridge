"""Mock Lakeside Auto Group SOAP 1.1 DMS / ERP service.

This is a hand-rolled FastAPI XML endpoint, not a real CDK or Reynolds
system. It deliberately keeps a few legacy quirks: a session token from
Login, odd field names, quantities as strings, and SOAP 1.1 faults.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

from erpbridge import catalog
from erpbridge.settings import (
    DEMO_PASSWORD,
    DEMO_USER,
    FLAKY_PART_NUMBER,
    SESSION_TTL_SECONDS,
    SLOW_PART_DELAY_SECONDS,
    SLOW_PART_NUMBER,
    COMPANY,
)
from erpbridge.soap_xml import (
    DMS_NS,
    build_fault,
    build_response,
    dms_element,
    parse_envelope,
    pretty_xml,
)

WSDL = f'''<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    name="LakesideDms"
    targetNamespace="{DMS_NS}"
    xmlns:tns="{DMS_NS}"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <wsdl:documentation>
    Mock WSDL for {COMPANY}. Not a vendor WSDL. Operations and field
    names are invented for this portfolio demo.
  </wsdl:documentation>
  <wsdl:types>
    <xsd:schema targetNamespace="{DMS_NS}" elementFormDefault="qualified">
      <xsd:element name="Login">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="UserID" type="xsd:string"/>
            <xsd:element name="Password" type="xsd:string"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
      <xsd:element name="LoginResponse">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="SessTok" type="xsd:string"/>
            <xsd:element name="ExpiresIn" type="xsd:string"/>
            <xsd:element name="UserID" type="xsd:string"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
      <xsd:element name="GetPartAvailability">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="StoreNum" type="xsd:string"/>
            <xsd:element name="PartNo" type="xsd:string"/>
            <xsd:element name="MfrCode" type="xsd:string" minOccurs="0"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
      <xsd:element name="GetRepairOrder">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="StoreNum" type="xsd:string"/>
            <xsd:element name="RONum" type="xsd:string"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
      <xsd:element name="CreatePartsOrder">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="StoreNum" type="xsd:string"/>
            <xsd:element name="PartNo" type="xsd:string"/>
            <xsd:element name="Qty" type="xsd:string"/>
            <xsd:element name="ChargeToRO" type="xsd:string" minOccurs="0"/>
            <xsd:element name="VendCd" type="xsd:string" minOccurs="0"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
      <xsd:element name="GetCustomerVehicle">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="VIN" type="xsd:string" minOccurs="0"/>
            <xsd:element name="CustNo" type="xsd:string" minOccurs="0"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>
    </xsd:schema>
  </wsdl:types>
  <wsdl:message name="LoginRequest"><wsdl:part name="body" element="tns:Login"/></wsdl:message>
  <wsdl:message name="LoginResponse"><wsdl:part name="body" element="tns:LoginResponse"/></wsdl:message>
  <wsdl:message name="GetPartAvailabilityRequest"><wsdl:part name="body" element="tns:GetPartAvailability"/></wsdl:message>
  <wsdl:message name="GetRepairOrderRequest"><wsdl:part name="body" element="tns:GetRepairOrder"/></wsdl:message>
  <wsdl:message name="CreatePartsOrderRequest"><wsdl:part name="body" element="tns:CreatePartsOrder"/></wsdl:message>
  <wsdl:message name="GetCustomerVehicleRequest"><wsdl:part name="body" element="tns:GetCustomerVehicle"/></wsdl:message>
  <wsdl:portType name="LakesideDmsPortType">
    <wsdl:operation name="Login"><wsdl:input message="tns:LoginRequest"/><wsdl:output message="tns:LoginResponse"/></wsdl:operation>
    <wsdl:operation name="GetPartAvailability"><wsdl:input message="tns:GetPartAvailabilityRequest"/></wsdl:operation>
    <wsdl:operation name="GetRepairOrder"><wsdl:input message="tns:GetRepairOrderRequest"/></wsdl:operation>
    <wsdl:operation name="CreatePartsOrder"><wsdl:input message="tns:CreatePartsOrderRequest"/></wsdl:operation>
    <wsdl:operation name="GetCustomerVehicle"><wsdl:input message="tns:GetCustomerVehicleRequest"/></wsdl:operation>
  </wsdl:portType>
  <wsdl:binding name="LakesideDmsSoapBinding" type="tns:LakesideDmsPortType">
    <soap:binding style="document" transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="Login"><soap:operation soapAction="http://lakeside.example/dms/Login"/></wsdl:operation>
    <wsdl:operation name="GetPartAvailability"><soap:operation soapAction="http://lakeside.example/dms/GetPartAvailability"/></wsdl:operation>
    <wsdl:operation name="GetRepairOrder"><soap:operation soapAction="http://lakeside.example/dms/GetRepairOrder"/></wsdl:operation>
    <wsdl:operation name="CreatePartsOrder"><soap:operation soapAction="http://lakeside.example/dms/CreatePartsOrder"/></wsdl:operation>
    <wsdl:operation name="GetCustomerVehicle"><soap:operation soapAction="http://lakeside.example/dms/GetCustomerVehicle"/></wsdl:operation>
  </wsdl:binding>
  <wsdl:service name="LakesideDmsService">
    <wsdl:documentation>Mock SOAP endpoint at POST /dms. WSDL at GET /dms?wsdl.</wsdl:documentation>
    <wsdl:port name="LakesideDmsPort" binding="tns:LakesideDmsSoapBinding">
      <soap:address location="http://127.0.0.1:8005/dms"/>
    </wsdl:port>
  </wsdl:service>
</wsdl:definitions>
'''


class SoapFault(Exception):
    def __init__(self, err_cd: str, err_msg: str, fault_code: str = "soap:Client") -> None:
        super().__init__(err_msg)
        self.err_cd = err_cd
        self.err_msg = err_msg
        self.fault_code = fault_code

    def as_xml(self) -> str:
        fault_string = f"{self.err_cd}: {self.err_msg}"
        return build_fault(self.fault_code, fault_string, self.err_cd, self.err_msg)


class DmsState:
    """In-memory sessions, inventory copy, and parts orders for one process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.sessions: dict[str, float] = {}
        self.parts: dict[tuple[str, str], dict] = {
            key: dict(value) for key, value in catalog.PARTS.items()
        }
        self.orders: list[dict] = []
        self.flaky_failures: dict[str, int] = {}
        self._order_seq = 10040

    def reset(self) -> None:
        with self._lock:
            self.sessions.clear()
            self.parts = {key: dict(value) for key, value in catalog.PARTS.items()}
            self.orders.clear()
            self.flaky_failures.clear()
            self._order_seq = 10040

    def new_session(self) -> str:
        token = "SESS-" + uuid.uuid4().hex[:20].upper()
        with self._lock:
            self.sessions[token] = time.time() + SESSION_TTL_SECONDS
        return token

    def check_session(self, token: str) -> None:
        if not token:
            raise SoapFault("NO_SESSION", "SessTok is missing. Call Login first.")
        with self._lock:
            expires = self.sessions.get(token)
            if expires is None:
                raise SoapFault("NO_SESSION", "SessTok is not recognized. Call Login again.")
            if expires < time.time():
                self.sessions.pop(token, None)
                raise SoapFault("SESSION_EXPIRED", "SessTok has expired. Call Login again.")

    def expire_session(self, token: str) -> None:
        with self._lock:
            self.sessions.pop(token, None)

    def should_flaky_fail(self, part_no: str) -> bool:
        with self._lock:
            count = self.flaky_failures.get(part_no, 0)
            if count == 0:
                self.flaky_failures[part_no] = 1
                return True
            return False

    def next_po(self) -> str:
        with self._lock:
            self._order_seq += 1
            return f"PO-{self._order_seq}"

    def place_order(self, record: dict) -> dict:
        with self._lock:
            self.orders.append(record)
            key = (record["StoreNum"], record["PartNo"])
            part = self.parts.get(key)
            if part is not None:
                on_hand = _as_float(part["QtyOnHand"])
                qty = _as_float(record["Qty"])
                part["QtyOnHand"] = f"{max(0.0, on_hand - qty):.4f}"
            return record


STATE = DmsState()


def _as_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _qty_string(value: Any) -> str:
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return "0.0000"


def handle_soap(xml_text: str, soap_action: str | None = None, state: DmsState | None = None) -> tuple[str, int]:
    """Process one SOAP 1.1 envelope. Returns (xml, http_status).

    SOAP 1.1 faults use HTTP 500. Login and the four business operations
    use HTTP 200.
    """
    dms = state or STATE
    try:
        parsed = parse_envelope(xml_text)
    except Exception:
        fault = SoapFault("BAD_ENVELOPE", "The request was not a valid SOAP 1.1 envelope.")
        return fault.as_xml(), 500

    body_name = parsed["body_name"]
    fields = parsed["fields"]
    token = parsed["session_token"]

    # Quirk: a SOAPAction header is required, the way many older stacks do it.
    # Login is included so a forgotten header fails loudly.
    expected_action = f"{DMS_NS}/{body_name}" if body_name else ""
    action = (soap_action or "").strip().strip('"')
    if not action:
        fault = SoapFault("MISSING_SOAPACTION", "SOAPAction header is required.")
        return fault.as_xml(), 500
    if body_name and action not in {expected_action, body_name}:
        # Be slightly lenient: either the full URI or the bare operation name.
        fault = SoapFault(
            "BAD_SOAPACTION",
            f"SOAPAction {action!r} does not match operation {body_name}.",
        )
        return fault.as_xml(), 500

    try:
        if body_name == "Login":
            xml = _login(fields, dms)
        elif body_name == "GetPartAvailability":
            dms.check_session(token)
            xml = _get_part(fields, dms)
        elif body_name == "GetRepairOrder":
            dms.check_session(token)
            xml = _get_ro(fields)
        elif body_name == "CreatePartsOrder":
            dms.check_session(token)
            xml = _create_order(fields, dms)
        elif body_name == "GetCustomerVehicle":
            dms.check_session(token)
            xml = _get_vehicle(fields)
        elif not body_name:
            raise SoapFault("EMPTY_BODY", "SOAP Body did not contain a recognized operation.")
        else:
            raise SoapFault("UNKNOWN_OPERATION", f"Operation {body_name} is not supported.")
        return xml, 200
    except SoapFault as fault:
        return fault.as_xml(), 500


def _login(fields: dict[str, str], dms: DmsState) -> str:
    user = fields.get("UserID", "")
    password = fields.get("Password", "")
    if user != DEMO_USER or password != DEMO_PASSWORD:
        raise SoapFault("BAD_CREDENTIALS", "UserID or Password is not valid.")
    token = dms.new_session()
    return build_response(
        "LoginResponse",
        {
            "SessTok": token,
            "ExpiresIn": str(SESSION_TTL_SECONDS),
            "UserID": user,
        },
    )


def _require_store(fields: dict[str, str]) -> str:
    raw = fields.get("StoreNum", "")
    store = catalog.resolve_store(raw) if raw else None
    if not store:
        raise SoapFault("BAD_STORE", f"StoreNum {raw!r} is not a Lakeside rooftop.")
    return store


def _get_part(fields: dict[str, str], dms: DmsState) -> str:
    store = _require_store(fields)
    part_no = (fields.get("PartNo") or "").strip()
    if not part_no:
        raise SoapFault("BAD_PART", "PartNo is required.")

    if part_no == SLOW_PART_NUMBER:
        time.sleep(SLOW_PART_DELAY_SECONDS)

    if part_no == FLAKY_PART_NUMBER and dms.should_flaky_fail(part_no):
        raise SoapFault(
            "TRANSIENT",
            "Inventory service timed out (simulated flaky call).",
            fault_code="soap:Server",
        )

    record = dms.parts.get((store, part_no))
    if record is None:
        raise SoapFault(
            "PART_NOT_FOUND",
            f"No inventory record for PartNo {part_no} at StoreNum {store}.",
        )

    payload = dict(record)
    payload["StoreNum"] = store
    return build_response("GetPartAvailabilityResponse", payload)


def _get_ro(fields: dict[str, str]) -> str:
    store = _require_store(fields)
    ro_num = (fields.get("RONum") or "").strip()
    if not ro_num:
        raise SoapFault("BAD_RO", "RONum is required.")
    record = catalog.REPAIR_ORDERS.get((store, ro_num))
    if record is None:
        raise SoapFault("RO_NOT_FOUND", f"No repair order {ro_num} at StoreNum {store}.")

    fields_out = {k: v for k, v in record.items() if k != "lines" and not isinstance(v, (list, dict))}
    children = []
    for line in record.get("lines", []):
        line_el = dms_element("ROLine")
        for key, value in line.items():
            child = dms_element(key, value)
            line_el.append(child)
        children.append(line_el)
    return build_response("GetRepairOrderResponse", fields_out, extra_children=children)


def _create_order(fields: dict[str, str], dms: DmsState) -> str:
    store = _require_store(fields)
    part_no = (fields.get("PartNo") or "").strip()
    qty = _qty_string(fields.get("Qty") or "0")
    if not part_no:
        raise SoapFault("BAD_PART", "PartNo is required.")
    if _as_float(qty) <= 0:
        raise SoapFault("BAD_QTY", "Qty must be a number greater than zero.")

    part = dms.parts.get((store, part_no))
    if part is None:
        raise SoapFault(
            "PART_NOT_FOUND",
            f"No inventory record for PartNo {part_no} at StoreNum {store}.",
        )
    on_hand = _as_float(part["QtyOnHand"])
    if _as_float(qty) > on_hand:
        raise SoapFault(
            "INSUFFICIENT_QTY",
            f"Qty {qty} is greater than QtyOnHand {part['QtyOnHand']}.",
        )

    po_num = dms.next_po()
    record = {
        "PoNum": po_num,
        "StoreNum": store,
        "PartNo": part_no,
        "Qty": qty,
        "ChargeToRO": (fields.get("ChargeToRO") or "").strip(),
        "VendCd": (fields.get("VendCd") or "HON").strip(),
        "StatCd": "O",
    }
    dms.place_order(record)
    return build_response("CreatePartsOrderResponse", record)


def _get_vehicle(fields: dict[str, str]) -> str:
    vin = (fields.get("VIN") or "").strip()
    cust_no = (fields.get("CustNo") or "").strip()
    record = None
    if vin:
        record = catalog.VEHICLES.get(vin)
    elif cust_no:
        record = catalog.VEHICLE_BY_CUSTOMER.get(cust_no)
    else:
        raise SoapFault("BAD_LOOKUP", "VIN or CustNo is required.")
    if record is None:
        raise SoapFault("VEHICLE_NOT_FOUND", "No customer vehicle matched that VIN or CustNo.")
    return build_response("GetCustomerVehicleResponse", dict(record))


def create_app(state: DmsState | None = None) -> FastAPI:
    dms = state or STATE
    app = FastAPI(
        title="Lakeside Auto Group mock DMS",
        description="Portfolio demo SOAP 1.1 endpoint. Not a real dealer system.",
        docs_url=None,
        redoc_url=None,
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "company": COMPANY, "service": "mock-dms"}

    @app.get("/dms")
    @app.get("/dms.wsdl")
    def wsdl(wsdl: str | None = None) -> Response:
        return Response(content=WSDL, media_type="text/xml; charset=utf-8")

    @app.post("/dms")
    async def dms_endpoint(request: Request) -> Response:
        body = (await request.body()).decode("utf-8", errors="replace")
        soap_action = request.headers.get("SOAPAction") or request.headers.get("soapaction")
        xml, status = handle_soap(body, soap_action=soap_action, state=dms)
        return Response(content=xml, status_code=status, media_type="text/xml; charset=utf-8")

    @app.get("/demo/orders")
    def list_orders() -> dict:
        return {"orders": list(dms.orders), "note": "Simulated parts orders only."}

    @app.get("/")
    def root() -> PlainTextResponse:
        return PlainTextResponse(
            f"{COMPANY} mock SOAP DMS. WSDL at /dms?wsdl. POST SOAP 1.1 to /dms.\n"
        )

    # Expose helpers for tests and the inspector.
    app.state.dms = dms
    app.state.wsdl = WSDL
    app.state.pretty = pretty_xml
    return app


app = create_app()
