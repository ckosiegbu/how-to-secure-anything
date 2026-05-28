"""Tariff / unit conversion -- ports the convertUnits/scaleUnits logic and the
TOKEN_TYPES metadata from modules/sts/common-1.0.tm.
"""

from __future__ import annotations
import math

from .codec import (encode_transfer_amount, encode_currency_transfer_amount,
                    is_currency)

# Subset of common-1.0.tm TOKEN_TYPES needed for amount handling/scaling.
# (class, subclass) -> metadata
TOKEN_TYPES = {
    (0, 0): {"desc": "Credit:Electricity", "encode": 1, "scale": 10, "prec": 1, "su": "kWh", "unit": "hWh"},
    (0, 1): {"desc": "Credit:Water", "encode": 1, "scale": 10, "prec": 1, "su": "kL", "unit": "hL"},
    (0, 2): {"desc": "Credit:Gas", "encode": 1, "scale": 10, "prec": 1, "su": "m^3", "unit": "0.1 m^3"},
    (0, 3): {"desc": "Credit:Time", "encode": 1, "scale": 10, "prec": 1, "su": "min", "unit": "0.1 min"},
    (0, 4): {"desc": "Credit:CurrencyElec", "encode": 1, "scale": 1, "prec": 5, "su": "$", "unit": "currency"},
    (0, 5): {"desc": "Credit:CurrencyWater", "encode": 1, "scale": 1, "prec": 5, "su": "$", "unit": "currency"},
    (0, 6): {"desc": "Credit:CurrencyGas", "encode": 1, "scale": 1, "prec": 5, "su": "$", "unit": "currency"},
    (0, 7): {"desc": "Credit:CurrencyTime", "encode": 1, "scale": 1, "prec": 5, "su": "$", "unit": "currency"},
    (2, 0): {"desc": "SetMaximumPowerLimit", "encode": 1, "unit": "Watt"},
    (2, 6): {"desc": "SetMaxPhaseUnbalanceLmt", "encode": 1, "unit": "Watt"},
}


def must_encode_transfer_amount(cls: int, subclass: int) -> bool:
    return bool(TOKEN_TYPES.get((cls, subclass), {}).get("encode", 0))


def convert_units(units_req, tariff=None, cls=0, subclass=0,
                  only_encode_if_required=False) -> dict:
    """Mirror common convertUnits. With a tariff, units_req is a currency value
    (base units) and is divided by the per-unit tariff; rounding is in the
    customer's favour per STS rules.
    """
    units_req = float(units_req)
    result = {}
    if tariff is not None:
        tariff = round(float(tariff), 5)
        result["tariff"] = tariff
        result["valueReq"] = round(units_req, 2)
        units_req = round(units_req / tariff, 5)
    else:
        units_req = round(units_req, 5)

    if only_encode_if_required and not must_encode_transfer_amount(cls, subclass):
        result["transferAmt"] = units_req if is_currency(cls, subclass) else int(math.ceil(units_req))
    elif is_currency(cls, subclass):
        result["transferAmt"] = encode_currency_transfer_amount(units_req)
    else:
        units_req = int(math.ceil(units_req))
        result["transferAmt"] = encode_transfer_amount(units_req)

    result["unitsReq"] = units_req
    return result


def scale_units(cls: int, subclass: int, units_actual: float) -> dict:
    """Mirror common scaleUnits: human-friendly scaled value + unit name."""
    md = TOKEN_TYPES.get((cls, subclass))
    out = {"class": cls, "subclass": subclass, "units": units_actual,
           "scaledUnits": units_actual, "scaledUnitName": "units"}
    if md and "scale" in md:
        out["scaledUnits"] = round(units_actual / md["scale"], md["prec"])
        out["scaledUnitName"] = md["su"]
    elif md and "unit" in md:
        out["scaledUnitName"] = md["unit"]
    out["print"] = f"{out['scaledUnits']} {out['scaledUnitName']}"
    return out
