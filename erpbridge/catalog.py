"""Fictional Lakeside Auto Group DMS records used by the mock SOAP service.

Every value here is made up for the demo. The VIN matches the other
portfolio projects (Maya Elena Alvarez's 2023 Honda CR-V EX).
"""

from __future__ import annotations

# StoreNum is the odd, padded identifier a real DMS would use.
# Agents and the MCP tools speak store names; the bridge maps them.
STORES: dict[str, dict] = {
    "01": {"name": "Lakeside Honda", "city": "Portland"},
    "02": {"name": "Westbrook Chevrolet", "city": "Westbrook"},
    "03": {"name": "Northlake Toyota", "city": "Northlake"},
    "04": {"name": "Parkside Ford", "city": "Parkside"},
}

STORE_ALIASES: dict[str, str] = {}
for _num, _meta in STORES.items():
    STORE_ALIASES[_num] = _num
    STORE_ALIASES[_meta["name"].lower()] = _num
    STORE_ALIASES[_meta["name"].lower().replace(" ", "")] = _num


def resolve_store(value: str) -> str | None:
    """Map a store name or number to a StoreNum, or None if unknown."""
    if value is None:
        return None
    key = str(value).strip()
    if not key:
        return None
    if key in STORES:
        return key
    return STORE_ALIASES.get(key.lower()) or STORE_ALIASES.get(key.lower().replace(" ", ""))


# Inventory keyed by (StoreNum, PartNo). Quantities and prices are stored
# as the DMS would: strings with four decimal places.
PARTS: dict[tuple[str, str], dict] = {
    ("01", "12345"): {
        "PartNo": "12345",
        "PartDesc": "Honda oil filter (demo SKU)",
        "MfrCode": "HON",
        "QtyOnHand": "14.0000",
        "QtyOnOrder": "6.0000",
        "QtyAlloc": "1.0000",
        "ListPrice": "12.8500",
        "CostAmt": "6.4000",
        "BinLoc": "A-14-C",
        "SupersedeTo": "",
        "AvailStat": "A",
        "LeadTimeDays": "1",
    },
    ("02", "12345"): {
        "PartNo": "12345",
        "PartDesc": "Honda oil filter (demo SKU)",
        "MfrCode": "HON",
        "QtyOnHand": "0.0000",
        "QtyOnOrder": "4.0000",
        "QtyAlloc": "0.0000",
        "ListPrice": "13.2500",
        "CostAmt": "6.4000",
        "BinLoc": "",
        "SupersedeTo": "",
        "AvailStat": "N",
        "LeadTimeDays": "3",
    },
    ("01", "15400RTA"): {
        "PartNo": "15400RTA",
        "PartDesc": "Honda oil filter, superseded SKU",
        "MfrCode": "HON",
        "QtyOnHand": "0.0000",
        "QtyOnOrder": "0.0000",
        "QtyAlloc": "0.0000",
        "ListPrice": "11.9900",
        "CostAmt": "5.8000",
        "BinLoc": "",
        "SupersedeTo": "12345",
        "AvailStat": "S",
        "LeadTimeDays": "1",
    },
    ("01", "SLOW99"): {
        "PartNo": "SLOW99",
        "PartDesc": "Cabin filter (intentionally slow DMS lookup)",
        "MfrCode": "HON",
        "QtyOnHand": "8.0000",
        "QtyOnOrder": "0.0000",
        "QtyAlloc": "0.0000",
        "ListPrice": "24.5000",
        "CostAmt": "11.2000",
        "BinLoc": "B-02-A",
        "SupersedeTo": "",
        "AvailStat": "A",
        "LeadTimeDays": "2",
    },
    ("01", "FLAKY99"): {
        "PartNo": "FLAKY99",
        "PartDesc": "Wiper blade (intentionally flaky first call)",
        "MfrCode": "HON",
        "QtyOnHand": "22.0000",
        "QtyOnOrder": "0.0000",
        "QtyAlloc": "0.0000",
        "ListPrice": "18.0000",
        "CostAmt": "7.2500",
        "BinLoc": "C-11-D",
        "SupersedeTo": "",
        "AvailStat": "A",
        "LeadTimeDays": "1",
    },
}

REPAIR_ORDERS: dict[tuple[str, str], dict] = {
    ("01", "7781"): {
        "RONum": "7781",
        "StoreNum": "01",
        "StatCd": "O",
        "OpenDt": "20261120",
        "PromisedDt": "20261124",
        "CustNo": "C-44108",
        "CustName": "Maya Elena Alvarez",
        "VIN": "1LKSDM26XMCB00001",
        "VehYr": "2023",
        "VehMake": "HONDA",
        "VehMod": "CR-V EX",
        "Mileage": "28410",
        "TagNo": "7781",
        "AdvisorNm": "Casey Ward",
        "OpCodes": "10;50",
        "LaborAmt": "89.9500",
        "PartsAmt": "12.8500",
        "lines": [
            {
                "LineNo": "1",
                "OpCode": "10",
                "OpDesc": "Oil and filter service",
                "LaborAmt": "89.9500",
                "PartsAmt": "12.8500",
                "TechInit": "CWARD",
            },
            {
                "LineNo": "2",
                "PartNo": "12345",
                "PartDesc": "Honda oil filter (demo SKU)",
                "Qty": "1.0000",
                "PartsAmt": "12.8500",
            },
            {
                "LineNo": "3",
                "OpCode": "50",
                "OpDesc": "Multi-point inspection",
                "LaborAmt": "0.0000",
                "PartsAmt": "0.0000",
                "TechInit": "CWARD",
            },
        ],
    }
}

VEHICLES: dict[str, dict] = {
    "1LKSDM26XMCB00001": {
        "VIN": "1LKSDM26XMCB00001",
        "CustNo": "C-44108",
        "CustName": "Maya Elena Alvarez",
        "VehYr": "2023",
        "VehMake": "HONDA",
        "VehMod": "CR-V EX",
        "Mileage": "28410",
        "LastSvcDt": "20261120",
        "StockNo": "0007781",
        "StoreNum": "01",
    }
}

VEHICLE_BY_CUSTOMER = {v["CustNo"]: v for v in VEHICLES.values()}

AVAIL_LABELS = {
    "A": "in_stock",
    "N": "not_in_stock",
    "S": "superseded",
}

RO_STATUS_LABELS = {
    "O": "open",
    "C": "closed",
    "I": "invoiced",
    "V": "void",
}
