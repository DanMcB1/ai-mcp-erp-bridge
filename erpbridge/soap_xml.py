"""Build and parse SOAP 1.1 envelopes for the mock Lakeside DMS.

Field names and types follow the quirks of the mock service: SessTok,
StoreNum, PartNo, string-encoded quantities, YYYYMMDD dates.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from xml.dom import minidom

SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
DMS_NS = "http://lakeside.example/dms"
SOAP_ENV_PREFIX = "soap"
DMS_PREFIX = "dms"

ET.register_namespace(SOAP_ENV_PREFIX, SOAP_NS)
ET.register_namespace(DMS_PREFIX, DMS_NS)


def q(ns_uri: str, tag: str) -> str:
    return f"{{{ns_uri}}}{tag}"


def local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def find_local(element: ET.Element | None, name: str) -> ET.Element | None:
    if element is None:
        return None
    if local_name(element.tag) == name:
        return element
    for child in element.iter():
        if local_name(child.tag) == name:
            return child
    return None


def child_text(element: ET.Element | None, name: str, default: str = "") -> str:
    found = find_local(element, name)
    if found is None or found.text is None:
        return default
    return found.text


def pretty_xml(xml_text: str) -> str:
    """Pretty-print XML for the inspector. Falls back to the raw string."""
    text = (xml_text or "").strip()
    if not text:
        return ""
    try:
        root = ET.fromstring(text)
        rough = ET.tostring(root, encoding="unicode")
        parsed = minidom.parseString(rough)
        pretty = parsed.toprettyxml(indent="  ")
        # minidom adds an XML declaration and blank lines; tidy them.
        pretty = re.sub(r"<\?xml[^>]*\?>\n?", "", pretty).strip()
        pretty = "\n".join(line for line in pretty.splitlines() if line.strip())
        return pretty
    except (ET.ParseError, Exception):
        return text


def build_envelope(
    body_local_name: str,
    fields: dict[str, str] | None = None,
    session_token: str | None = None,
    extra_children: list[ET.Element] | None = None,
) -> str:
    envelope = ET.Element(q(SOAP_NS, "Envelope"))
    header = ET.SubElement(envelope, q(SOAP_NS, "Header"))
    if session_token:
        sess = ET.SubElement(header, q(DMS_NS, "SessionHeader"))
        tok = ET.SubElement(sess, q(DMS_NS, "SessTok"))
        tok.text = session_token
    body = ET.SubElement(envelope, q(SOAP_NS, "Body"))
    op = ET.SubElement(body, q(DMS_NS, body_local_name))
    for key, value in (fields or {}).items():
        if value is None:
            continue
        node = ET.SubElement(op, q(DMS_NS, key))
        node.text = str(value)
    for child in extra_children or []:
        op.append(child)
    return ET.tostring(envelope, encoding="unicode", xml_declaration=True)


def build_fault(fault_code: str, fault_string: str, err_cd: str, err_msg: str) -> str:
    envelope = ET.Element(q(SOAP_NS, "Envelope"))
    ET.SubElement(envelope, q(SOAP_NS, "Header"))
    body = ET.SubElement(envelope, q(SOAP_NS, "Body"))
    fault = ET.SubElement(body, q(SOAP_NS, "Fault"))
    fc = ET.SubElement(fault, "faultcode")
    fc.text = fault_code
    fs = ET.SubElement(fault, "faultstring")
    fs.text = fault_string
    detail = ET.SubElement(fault, "detail")
    err = ET.SubElement(detail, q(DMS_NS, "Error"))
    cd = ET.SubElement(err, q(DMS_NS, "ErrCd"))
    cd.text = err_cd
    msg = ET.SubElement(err, q(DMS_NS, "ErrMsg"))
    msg.text = err_msg
    return ET.tostring(envelope, encoding="unicode", xml_declaration=True)


def parse_envelope(xml_text: str) -> dict:
    """Return {header, body_name, fields, fault, raw_root}."""
    root = ET.fromstring(xml_text)
    header_el = find_local(root, "Header")
    body_el = find_local(root, "Body")
    token = child_text(header_el, "SessTok") if header_el is not None else ""

    fault_el = find_local(body_el, "Fault") if body_el is not None else None
    if fault_el is not None:
        return {
            "session_token": token,
            "body_name": "Fault",
            "fields": {},
            "fault": {
                "faultcode": child_text(fault_el, "faultcode"),
                "faultstring": child_text(fault_el, "faultstring"),
                "err_cd": child_text(fault_el, "ErrCd"),
                "err_msg": child_text(fault_el, "ErrMsg"),
            },
        }

    operation = None
    if body_el is not None:
        for child in list(body_el):
            if local_name(child.tag) != "Fault":
                operation = child
                break

    fields: dict[str, str] = {}
    body_name = ""
    if operation is not None:
        body_name = local_name(operation.tag)
        for child in list(operation):
            # Nested line items are handled by the caller via the element tree.
            if list(child):
                continue
            fields[local_name(child.tag)] = child.text or ""

    return {
        "session_token": token,
        "body_name": body_name,
        "fields": fields,
        "fault": None,
        "operation": operation,
    }


def dms_element(tag: str, text: str | None = None) -> ET.Element:
    el = ET.Element(q(DMS_NS, tag))
    if text is not None:
        el.text = str(text)
    return el


def append_fields(parent: ET.Element, fields: dict[str, str]) -> None:
    for key, value in fields.items():
        if value is None:
            continue
        node = ET.SubElement(parent, q(DMS_NS, key))
        node.text = str(value)


def build_response(response_name: str, fields: dict[str, str], extra_children: list[ET.Element] | None = None) -> str:
    envelope = ET.Element(q(SOAP_NS, "Envelope"))
    ET.SubElement(envelope, q(SOAP_NS, "Header"))
    body = ET.SubElement(envelope, q(SOAP_NS, "Body"))
    op = ET.SubElement(body, q(DMS_NS, response_name))
    append_fields(op, fields)
    for child in extra_children or []:
        op.append(child)
    return ET.tostring(envelope, encoding="unicode", xml_declaration=True)
