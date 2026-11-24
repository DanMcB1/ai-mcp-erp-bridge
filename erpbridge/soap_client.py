"""HTTP SOAP 1.1 client for the mock Lakeside DMS.

Handles Login / SessTok, retries on transient faults and timeouts, and
maps the odd SOAP field names into clean JSON.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from erpbridge import catalog
from erpbridge.settings import (
    DEMO_PASSWORD,
    DEMO_USER,
    SOAP_RETRIES,
    SOAP_TIMEOUT_SECONDS,
    soap_url,
)
from erpbridge.soap_xml import (
    DMS_NS,
    build_envelope,
    parse_envelope,
    pretty_xml,
)

TRANSIENT_CODES = {"TRANSIENT"}


class SoapError(Exception):
    """A SOAP fault or transport error, already mapped to a short message."""

    def __init__(
        self,
        message: str,
        *,
        err_cd: str = "SOAP_ERROR",
        transient: bool = False,
        request_xml: str = "",
        response_xml: str = "",
    ) -> None:
        super().__init__(message)
        self.err_cd = err_cd
        self.transient = transient
        self.request_xml = request_xml
        self.response_xml = response_xml


def _format_qty(value: Any) -> int | float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if number.is_integer():
        return int(number)
    return round(number, 4)


def _format_money(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return value


def _format_date(value: str) -> str:
    text = (value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text


class SoapClient:
    def __init__(
        self,
        base_url: str | None = None,
        http: httpx.Client | None = None,
        timeout: float = SOAP_TIMEOUT_SECONDS,
        retries: int = SOAP_RETRIES,
        user: str = DEMO_USER,
        password: str = DEMO_PASSWORD,
    ) -> None:
        self.base_url = (base_url or soap_url()).rstrip("/")
        self._owns_http = http is None
        self.http = http or httpx.Client(timeout=timeout)
        self.timeout = timeout
        self.retries = retries
        self.user = user
        self.password = password
        self.session_token: str | None = None
        self.last_request_xml = ""
        self.last_response_xml = ""
        self.last_retries = 0

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def login(self) -> str:
        xml, _parsed = self._call("Login", {"UserID": self.user, "Password": self.password}, authed=False)
        parsed = parse_envelope(xml)
        if parsed["fault"]:
            fault = parsed["fault"]
            raise SoapError(
                fault["err_msg"] or fault["faultstring"],
                err_cd=fault["err_cd"] or "BAD_CREDENTIALS",
                request_xml=self.last_request_xml,
                response_xml=self.last_response_xml,
            )
        token = parsed["fields"].get("SessTok") or ""
        if not token:
            raise SoapError("Login succeeded but no SessTok was returned.")
        self.session_token = token
        return token

    def ensure_session(self) -> str:
        if not self.session_token:
            self.login()
        assert self.session_token is not None
        return self.session_token

    def get_part_availability(self, store: str, part_number: str, manufacturer: str | None = None) -> dict[str, Any]:
        store_num = self._store_num(store)
        fields = {"StoreNum": store_num, "PartNo": part_number}
        if manufacturer:
            fields["MfrCode"] = manufacturer
        raw = self._call_authed("GetPartAvailability", fields)
        data = raw["fields"]
        return {
            "store": catalog.STORES.get(store_num, {}).get("name", store),
            "store_number": store_num,
            "part_number": data.get("PartNo", part_number),
            "description": data.get("PartDesc", ""),
            "manufacturer": data.get("MfrCode", manufacturer or ""),
            "quantity_on_hand": _format_qty(data.get("QtyOnHand")),
            "quantity_on_order": _format_qty(data.get("QtyOnOrder")),
            "quantity_allocated": _format_qty(data.get("QtyAlloc")),
            "list_price": _format_money(data.get("ListPrice")),
            "cost": _format_money(data.get("CostAmt")),
            "bin_location": data.get("BinLoc") or None,
            "superseded_by": data.get("SupersedeTo") or None,
            "availability": catalog.AVAIL_LABELS.get(data.get("AvailStat", ""), data.get("AvailStat")),
            "availability_code": data.get("AvailStat"),
            "lead_time_days": _format_qty(data.get("LeadTimeDays")),
        }

    def get_repair_order(self, store: str, ro_number: str) -> dict[str, Any]:
        store_num = self._store_num(store)
        raw = self._call_authed("GetRepairOrder", {"StoreNum": store_num, "RONum": str(ro_number)})
        data = raw["fields"]
        lines = []
        operation = raw.get("operation")
        if operation is not None:
            from erpbridge.soap_xml import local_name

            for child in list(operation):
                if local_name(child.tag) != "ROLine":
                    continue
                line = {local_name(item.tag): (item.text or "") for item in list(child)}
                clean: dict[str, Any] = {
                    "line_number": _format_qty(line.get("LineNo")),
                    "opcode": line.get("OpCode") or None,
                    "description": line.get("OpDesc") or line.get("PartDesc") or "",
                    "part_number": line.get("PartNo") or None,
                    "quantity": _format_qty(line["Qty"]) if line.get("Qty") else None,
                    "labor_amount": _format_money(line["LaborAmt"]) if "LaborAmt" in line else None,
                    "parts_amount": _format_money(line["PartsAmt"]) if "PartsAmt" in line else None,
                    "technician": line.get("TechInit") or None,
                }
                lines.append({k: v for k, v in clean.items() if v is not None and v != ""})

        opcodes = [code for code in (data.get("OpCodes") or "").split(";") if code]
        return {
            "store": catalog.STORES.get(store_num, {}).get("name", store),
            "store_number": store_num,
            "ro_number": data.get("RONum", str(ro_number)),
            "status": catalog.RO_STATUS_LABELS.get(data.get("StatCd", ""), data.get("StatCd")),
            "status_code": data.get("StatCd"),
            "opened_on": _format_date(data.get("OpenDt", "")),
            "promised_on": _format_date(data.get("PromisedDt", "")),
            "customer_number": data.get("CustNo"),
            "customer_name": data.get("CustName"),
            "vin": data.get("VIN"),
            "year": _format_qty(data.get("VehYr")),
            "make": data.get("VehMake"),
            "model": data.get("VehMod"),
            "mileage": _format_qty(data.get("Mileage")),
            "tag_number": data.get("TagNo"),
            "advisor": data.get("AdvisorNm"),
            "opcodes": opcodes,
            "labor_amount": _format_money(data.get("LaborAmt")),
            "parts_amount": _format_money(data.get("PartsAmt")),
            "lines": lines,
        }

    def create_parts_order(
        self,
        store: str,
        part_number: str,
        quantity: int | float,
        charge_to_ro: str | None = None,
        vendor: str | None = None,
    ) -> dict[str, Any]:
        store_num = self._store_num(store)
        fields = {
            "StoreNum": store_num,
            "PartNo": part_number,
            "Qty": f"{float(quantity):.4f}",
        }
        if charge_to_ro:
            fields["ChargeToRO"] = str(charge_to_ro)
        if vendor:
            fields["VendCd"] = vendor
        raw = self._call_authed("CreatePartsOrder", fields)
        data = raw["fields"]
        return {
            "order_number": data.get("PoNum"),
            "store": catalog.STORES.get(store_num, {}).get("name", store),
            "store_number": store_num,
            "part_number": data.get("PartNo", part_number),
            "quantity": _format_qty(data.get("Qty", quantity)),
            "charge_to_ro": data.get("ChargeToRO") or None,
            "vendor": data.get("VendCd") or vendor,
            "status": catalog.RO_STATUS_LABELS.get(data.get("StatCd", ""), data.get("StatCd") or "open"),
            "simulated": True,
        }

    def get_customer_vehicle(self, vin: str | None = None, customer_number: str | None = None) -> dict[str, Any]:
        fields: dict[str, str] = {}
        if vin:
            fields["VIN"] = vin
        if customer_number:
            fields["CustNo"] = customer_number
        raw = self._call_authed("GetCustomerVehicle", fields)
        data = raw["fields"]
        store_num = data.get("StoreNum", "")
        return {
            "vin": data.get("VIN"),
            "customer_number": data.get("CustNo"),
            "customer_name": data.get("CustName"),
            "year": _format_qty(data.get("VehYr")),
            "make": data.get("VehMake"),
            "model": data.get("VehMod"),
            "mileage": _format_qty(data.get("Mileage")),
            "last_service_on": _format_date(data.get("LastSvcDt", "")),
            "stock_number": data.get("StockNo"),
            "store": catalog.STORES.get(store_num, {}).get("name"),
            "store_number": store_num or None,
        }

    def _store_num(self, store: str) -> str:
        resolved = catalog.resolve_store(store)
        if not resolved:
            raise SoapError(
                f"Unknown store {store!r}. Try 'Lakeside Honda' or a store number like '01'.",
                err_cd="BAD_STORE",
            )
        return resolved

    def _call_authed(self, operation: str, fields: dict[str, str]) -> dict[str, Any]:
        self.ensure_session()
        try:
            _xml, parsed = self._call(operation, fields, authed=True)
        except SoapError as exc:
            if exc.err_cd in {"NO_SESSION", "SESSION_EXPIRED"}:
                self.login()
                _xml, parsed = self._call(operation, fields, authed=True)
            else:
                raise
        if parsed["fault"]:
            fault = parsed["fault"]
            raise SoapError(
                fault["err_msg"] or fault["faultstring"],
                err_cd=fault["err_cd"] or "SOAP_FAULT",
                transient=fault["err_cd"] in TRANSIENT_CODES,
                request_xml=self.last_request_xml,
                response_xml=self.last_response_xml,
            )
        return parsed

    def _call(self, operation: str, fields: dict[str, str], authed: bool) -> tuple[str, dict[str, Any]]:
        token = self.session_token if authed else None
        request_xml = build_envelope(operation, fields, session_token=token)
        self.last_request_xml = pretty_xml(request_xml)
        action = f"{DMS_NS}/{operation}"
        last_error: SoapError | None = None
        attempts = self.retries + 1
        self.last_retries = 0

        for attempt in range(attempts):
            if attempt:
                self.last_retries = attempt
                time.sleep(0.05 * attempt)
            try:
                response = self.http.post(
                    self.base_url,
                    content=request_xml.encode("utf-8"),
                    headers={
                        "Content-Type": "text/xml; charset=utf-8",
                        "SOAPAction": f'"{action}"',
                    },
                )
            except httpx.TimeoutException as exc:
                last_error = SoapError(
                    f"DMS timed out calling {operation}.",
                    err_cd="TIMEOUT",
                    transient=True,
                    request_xml=self.last_request_xml,
                )
                continue
            except httpx.HTTPError as exc:
                last_error = SoapError(
                    f"Could not reach the DMS at {self.base_url}: {exc}",
                    err_cd="TRANSPORT",
                    transient=True,
                    request_xml=self.last_request_xml,
                )
                continue

            self.last_response_xml = pretty_xml(response.text)
            try:
                parsed = parse_envelope(response.text)
            except Exception as exc:
                last_error = SoapError(
                    f"DMS returned XML that could not be parsed: {exc}",
                    err_cd="BAD_RESPONSE",
                    request_xml=self.last_request_xml,
                    response_xml=self.last_response_xml,
                )
                continue

            if parsed["fault"]:
                fault = parsed["fault"]
                err_cd = fault["err_cd"] or "SOAP_FAULT"
                err = SoapError(
                    fault["err_msg"] or fault["faultstring"],
                    err_cd=err_cd,
                    transient=err_cd in TRANSIENT_CODES,
                    request_xml=self.last_request_xml,
                    response_xml=self.last_response_xml,
                )
                if err.transient and attempt < attempts - 1:
                    last_error = err
                    continue
                raise err
            return response.text, parsed

        assert last_error is not None
        raise last_error
