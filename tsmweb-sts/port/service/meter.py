"""Meter identity: DRN / PAN / IDRecord / Record2 (ports common-1.0.tm + MeterRec).

DRN  = Decoder Reference Number: 11 digits (IIN 600727, mfr 0-99) or 13 digits
       (IIN 0000, mfr 100-9999); last digit is a Luhn check.
PAN  = 18-digit Primary Account Number = IIN + DRN + Luhn(whole).
IDRecord (IEC 62055-41) = PAN(18) DOE(4) TCT(2) EA(2) SGC(6) TI(2) KRN(1)  [35 chars]
Record2  (IEC 62055-51) = ;PAN=DOE==TCT EA SGC TI KRN?  (magstripe track 2)
"""

from __future__ import annotations
import re
import time


def luhn_mod_10(number: str) -> int:
    """Tcl ::sts::luhn_mod_10: returns the value that makes the string check out.
    Verify: luhn_mod_10(full) == 0.  Check digit: luhn_mod_10(base + '0')."""
    total = 0
    for pos, ch in enumerate(reversed(number)):
        prod = int(ch) * ((pos % 2) + 1)
        total += prod // 10 + prod % 10      # digit-sum of the product (prod <= 18)
    return (10 - total % 10) % 10


def check_digit(base: str) -> int:
    return luhn_mod_10(base + "0")


def luhn_ok(number: str) -> bool:
    return number.isdigit() and luhn_mod_10(number) == 0


def make_meter_pan(mfrcode: int, dsn: int) -> str:
    """Build an 18-digit PAN from manufacturer code + decoder serial number."""
    if mfrcode < 100:
        iin = "600727"
        drn = "%02d%08d" % (mfrcode, dsn)
    else:
        iin = "0000"
        drn = "%04d%08d" % (mfrcode, dsn)
    drn += str(check_digit(drn))
    assert luhn_mod_10(drn) == 0
    pan = iin + drn
    pan += str(check_digit(pan))
    assert luhn_mod_10(pan) == 0
    return pan


def drn_to_pan(drn: str) -> str:
    """11- or 13-digit DRN (with its own Luhn) -> 18-digit PAN."""
    if not luhn_ok(drn):
        raise ValueError(f"DRN bad check digit: {drn}")
    if len(drn) == 11:
        iin = "600727"
    elif len(drn) == 13:
        iin = "0000"
    else:
        raise ValueError(f"DRN must be 11 or 13 digits: {drn}")
    pan = iin + drn
    return pan + str(check_digit(pan))


def pan_to_drn(pan: str) -> str:
    """18-digit PAN -> DRN (validates both Luhns and the IIN)."""
    if len(pan) != 18 or not luhn_ok(pan):
        raise ValueError(f"PAN bad length/check digit: {pan}")
    if pan.startswith("600727"):
        drn = pan[6:17]                      # 11-digit DRN
    elif pan.startswith("0000"):
        drn = pan[4:17]                      # 13-digit DRN
    else:
        raise ValueError(f"PAN IIN must be 600727 or 0000: {pan}")
    if not luhn_ok(drn):
        raise ValueError(f"PAN embedded DRN bad check digit: {drn}")
    return drn


def normalize_pan(s: str) -> str:
    """Normalise an abbreviated PAN/DRN to a full 18-digit PAN."""
    s = s.strip()
    if not s.isdigit():
        raise ValueError(f"PAN/DRN must be digits: {s!r}")
    if len(s) == 11:
        s = "600727" + s
    elif len(s) == 13:
        s = "0000" + s
    elif len(s) == 16:
        s = "6" + s
    if len(s) == 17:
        s = s + str(check_digit(s))
    if len(s) != 18 or not luhn_ok(s):
        raise ValueError(f"cannot normalise to a valid 18-digit PAN: {s!r}")
    pan_to_drn(s)                            # validates IIN + embedded DRN
    return s


def has_expired(doe: str, unixtime: int | None = None) -> bool:
    """doe = 'YYMM' card expiry; '0000' = never. Expired if current month >= DOE."""
    if not doe or doe == "0000":
        return False
    unixtime = int(time.time()) if unixtime is None else unixtime
    yy, mm = int(doe[:2]), int(doe[2:])
    year = 1900 + yy
    if year < 1993:
        year += 100
    cur = time.strftime("%Y%m", time.gmtime(unixtime))
    return cur >= "%04d%02d" % (year, mm)


_RECORD2_RE = re.compile(r"^;?(\d{18})=(\d{4}|=)=(\d{2})(\d{2})(\d{6})(\d{2})(\d)\??$")


def parse_id_record(rec: str) -> dict:
    """Parse an IEC 62055-41 IDRecord (35 digits) or IEC 62055-51 Record2."""
    rec = rec.strip().lstrip("\x02").rstrip("\x03").strip()
    if rec.isdigit() and len(rec) == 35:
        pan, doe, tct, ea, sgc, ti, krn = (
            rec[0:18], rec[18:22], rec[22:24], rec[24:26], rec[26:32], rec[32:34], rec[34:35])
    else:
        m = _RECORD2_RE.match(rec)
        if not m:
            raise ValueError("not a valid IDRecord (35 digits) or Record2")
        pan, doe, tct, ea, sgc, ti, krn = m.groups()
        if doe == "=":
            doe = "0000"
    pan = normalize_pan(pan)
    return {
        "pan": pan, "drn": pan_to_drn(pan), "doe": doe,
        "tct": int(tct), "ea": int(ea), "sgc": int(sgc),
        "ti": int(ti), "krn": int(krn),
    }


def make_id_record(pan: str, sgc: int, krn: int, ti: int = 1, ea: int = 7,
                   tct: int = 2, doe: str = "0000") -> str:
    return "%18s%04d%02d%02d%06d%02d%1d" % (pan, int(doe), tct, ea, sgc, ti, krn)


def make_record2(pan: str, sgc: int, krn: int, ti: int = 1, ea: int = 7,
                 tct: int = 2, doe: str = "0000") -> str:
    doe_f = doe if (doe and doe != "0000") else "="
    return ";%-18s=%s=%02d%02d%06d%02d%d?" % (pan, doe_f, tct, ea, sgc, ti, krn)
