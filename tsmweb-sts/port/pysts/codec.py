"""STS token codec -- ports modules/sts/{common,softalg}-1.0.tm.

Clear-token build, CRC-16, transfer-amount encodings (16-bit + 20-bit
currency), TID helpers, class-bit transpose, encrypt/decrypt of class 0/1/2
tokens, and Key Change Token (KCT) build/parse.
"""

from __future__ import annotations
import math
from datetime import datetime, timezone

from .sta import Sta
from .misty1 import Misty1

# --------------------------------------------------------------------------
# Cipher dispatch (softalg getCipherCmdForEa)
#   ea 7   -> STA production tables (withheld; raises unless dropped in)
#   ea 107 -> STA demo tables, behaves as ea 7
#   ea 11  -> MISTY1 (public, fully functional)
# --------------------------------------------------------------------------

def get_cipher(ea: int):
    if ea == 7:
        return Sta(0), 7          # production (will raise: tables withheld)
    if ea == 107:
        return Sta(1), 7          # demo STA
    if ea == 11:
        return Misty1(), 11
    raise ValueError(f"unsupported EA={ea}")


# --------------------------------------------------------------------------
# CRC-16/CCITT-FALSE (poly 0x1021, seed 0xFFFF) -- the STS token CRC
# --------------------------------------------------------------------------

def crc16(data: bytes, seed: int = 0xFFFF) -> int:
    crc = seed
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


def _swap16(v: int) -> int:
    return ((v & 0xFF) << 8) | ((v >> 8) & 0xFF)


# --------------------------------------------------------------------------
# Token IDs / epochs (common-1.0.tm)
# --------------------------------------------------------------------------

EPOCHS = {
    93: int(datetime(1993, 1, 1, tzinfo=timezone.utc).timestamp()),
    14: int(datetime(2014, 1, 1, tzinfo=timezone.utc).timestamp()),
    35: int(datetime(2035, 1, 1, tzinfo=timezone.utc).timestamp()),
}
MAX_TID = 16777215


def token_id_from_time(unixtime: int, bdt=93) -> int:
    return (unixtime - EPOCHS[bdt]) // 60


def date_from_token_id(tid: int, bdt=93) -> int:
    return tid * 60 + EPOCHS[bdt]


def is_reserved_tid(tid: int) -> bool:
    return (tid % (24 * 60)) == 1


def is_currency(cls: int, subclass: int) -> bool:
    return cls == 0 and 4 <= subclass <= 7


# --------------------------------------------------------------------------
# Transfer amount encodings (common-1.0.tm)
# --------------------------------------------------------------------------

def encode_transfer_amount(amt: int) -> int:
    """16-bit mantissa/exponent encoding (IEC 62055-41 s6.3.6), rounds up."""
    if not 0 <= amt <= 18201624:
        raise ValueError("amt out of range")
    if amt >= 1818624:
        ta = 0xC000 | ((amt - 1818624) // 1000)
    elif amt >= 180224:
        ta = 0x8000 | ((amt - 180224) // 100)
    elif amt >= 16384:
        ta = 0x4000 | ((amt - 16384) // 10)
    else:
        ta = amt
    if decode_transfer_amount(ta) < amt:
        ta += 1
    return ta


def decode_transfer_amount(ta: int) -> int:
    exp = (ta >> 14) & 0x03
    m = ta & 0x3FFF
    t = (10 ** exp) * m
    for n in range(1, exp + 1):
        t += 0x4000 * 10 ** (n - 1)
    return t


def encode_currency_transfer_amount(amt: float) -> int:
    """20-bit signed currency encoding (STS202-1 Ed 2 s5.6.1)."""
    units = 100000.0 * float(amt)
    abs_units = abs(units)
    sbit = 1 if units < 0 else 0
    e = 0
    while e < 31 and (math.floor(abs_units) if sbit else math.ceil(abs_units)) > 16383:
        abs_units = (abs_units - 16384) / 10
        e += 1
    m = int(math.floor(abs_units) if sbit else math.ceil(abs_units))
    if m > 16383:
        raise ValueError("transferAmount out of range")
    return (sbit << 19) | (e << 14) | m


def decode_currency_transfer_amount(ta: int) -> float:
    sign = -1 if ((ta >> 19) & 1) else 1
    exp = (ta >> 14) & 0x1F
    m = float(ta & 0x3FFF)
    for _ in range(exp):
        m = m * 10.0 + 16384
    return m * sign / 100000.0


# --------------------------------------------------------------------------
# Clear-token assembly & class-bit transpose
# --------------------------------------------------------------------------

def _transpose_class_bits(tv: int) -> int:
    lobits = (tv >> 27) & 3
    hibits = (tv >> 64) & 3
    return (lobits << 64) | ((tv & 0xFFFFFFFFE7FFFFFF) | ((hibits & 3) << 27))


def make_clear_token_int(cls: int, subclass: int, content44: int) -> int:
    """66-bit clear token int incl. byte-swapped CRC (common makeClearTokenInt)."""
    cleartok = ((cls & 3) << 48) | ((subclass & 0xF) << 44) | (content44 & ((1 << 44) - 1))
    tokstr = cleartok.to_bytes(8, "big")[1:]
    if is_currency(cls, subclass):
        tokstr += b"\x01"
    return (cleartok << 16) | _swap16(crc16(tokstr))


def make_clear_token_fields(cls: int, subclass: int, *fields) -> int:
    """common makeClearToken: pack (value, bitlen) pairs MSB-first into 44 bits."""
    content = 0
    total = 0
    it = iter(fields)
    for val, bits in zip(it, it):
        content = (content << bits) | (val & ((1 << bits) - 1))
        total += bits
    if total != 44:
        raise ValueError("token content fields must total 44 bits")
    return make_clear_token_int(cls, subclass, content)


# --------------------------------------------------------------------------
# Encrypt / decrypt a 66-bit token  (softalg encryptToken / decryptToken)
# --------------------------------------------------------------------------

def encrypt_token_int(cipher, dk: bytes, cls: int, subclass: int, content44: int) -> str:
    cleartok = ((cls & 3) << 48) | ((subclass & 0xF) << 44) | (content44 & ((1 << 44) - 1))
    tokstr = cleartok.to_bytes(8, "big")[1:]
    if is_currency(cls, subclass):
        tokstr += b"\x01"
    crc = crc16(tokstr)
    datablock = ((cleartok & ((1 << 48) - 1)) << 16) | _swap16(crc)   # 64-bit
    enc = cipher.encrypt(dk, datablock.to_bytes(8, "big"))
    enc66 = (cls << 64) | int.from_bytes(enc, "big")
    return "%020d" % _transpose_class_bits(enc66)


def decrypt_token_int(cipher, dk: bytes, token20d: str) -> dict:
    det = _transpose_class_bits(int(token20d))
    cls = (det >> 64) & 3
    enc_db = (det & ((1 << 64) - 1)).to_bytes(8, "big")
    db = int.from_bytes(cipher.decrypt(dk, enc_db), "big")
    subclass = (db >> 60) & 0xF
    content = (db >> 16) & ((1 << 44) - 1)
    crc_stored = _swap16(db & 0xFFFF)
    cleartok = (cls << 48) | (subclass << 44) | content
    tokstr = cleartok.to_bytes(8, "big")[1:]
    if is_currency(cls, subclass):
        tokstr += b"\x01"
    if crc16(tokstr) != crc_stored:
        raise ValueError("CRC check failed (STSAPI 30)")
    return {"class": cls, "subclass": subclass, "content": content}


# --------------------------------------------------------------------------
# Credit / MSE token build & parse (softalg buildClearCreditMseToken / parse)
# --------------------------------------------------------------------------

def build_credit_mse_content(cls: int, subclass: int, rnd: int, tid: int,
                             transferamount, encode_amount=False) -> int:
    """Return the 44-bit content for class 0 / most class 2 tokens."""
    if is_currency(cls, subclass):
        amount = encode_currency_transfer_amount(transferamount) if encode_amount else transferamount
        if not 0 <= amount <= 0xFFFFF:
            raise ValueError("currency amount out of 20-bit range")
        rnd = (amount >> 16) & 0x0F
        transferamount = amount & 0xFFFF
    elif cls == 0:
        transferamount = encode_transfer_amount(transferamount) if encode_amount else transferamount
    elif cls == 2:
        if encode_amount and subclass in (0, 6):
            transferamount = encode_transfer_amount(transferamount)
        elif encode_amount and subclass == 5:
            transferamount = 0
    else:
        raise ValueError(f"unsupported class={cls}")
    if not 0 <= transferamount <= 0xFFFF:
        raise ValueError("transferamount out of 16-bit range")
    return ((rnd & 0xF) << 40) | ((tid & 0xFFFFFF) << 16) | (transferamount & 0xFFFF)


def parse_credit_mse_content(cls: int, subclass: int, content: int) -> dict:
    transferamount = content & 0xFFFF
    tid = (content >> 16) & 0xFFFFFF
    rnd = (content >> 40) & 0xF
    out = {"rnd": rnd, "tid": tid, "transferamount": transferamount}
    if is_currency(cls, subclass):
        amount20 = (rnd << 16) | transferamount
        out["rnd"] = 0
        out["transferamount"] = amount20
        out["amount"] = decode_currency_transfer_amount(amount20)
    else:
        out["amount"] = decode_transfer_amount(transferamount)
    out["unixtime"] = date_from_token_id(tid)
    return out


# --------------------------------------------------------------------------
# Key Change Tokens (softalg buildKeyChangeTokens)
# --------------------------------------------------------------------------

def build_key_change_tokens(ea: int, new_dk: bytes, new_sgc: int, new_krn: int,
                            new_ti: int, new_ken: int, new_kt: int,
                            ro: int = 0, three_kct: int = 0) -> list:
    """Return list of clear KCT token ints. EA=7 -> 2 (or 3) tokens; EA=11 -> 4."""
    kct = []
    if ea in (7, 107):
        if len(new_dk) != 8:
            raise ValueError("EA=7 new_dk must be 8 octets")
        nkho = int.from_bytes(new_dk[:4], "big")
        nklo = int.from_bytes(new_dk[4:], "big")
        kct.append(make_clear_token_fields(2, 3, new_ken >> 4, 4, new_krn, 4,
                                           ro, 1, three_kct, 1, new_kt, 2, nkho, 32))
        kct.append(make_clear_token_fields(2, 4, new_ken & 0x0F, 4, new_ti, 8, nklo, 32))
        if three_kct:
            kct.append(make_clear_token_fields(2, 8, new_sgc, 24, 0, 20))
    elif ea == 11:
        if len(new_dk) != 16:
            raise ValueError("EA=11 new_dk must be 16 octets")
        nkho = int.from_bytes(new_dk[0:4], "big")
        nkmo1 = int.from_bytes(new_dk[4:8], "big")
        nkmo2 = int.from_bytes(new_dk[8:12], "big")
        nklo = int.from_bytes(new_dk[12:16], "big")
        kct.append(make_clear_token_fields(2, 3, new_ken >> 4, 4, new_krn, 4,
                                           ro, 1, 0, 1, new_kt, 2, nkho, 32))
        kct.append(make_clear_token_fields(2, 4, new_ken & 0x0F, 4, new_ti, 8, nklo, 32))
        kct.append(make_clear_token_fields(2, 8, new_sgc & 0x0FFF, 12, nkmo1, 32))
        kct.append(make_clear_token_fields(2, 9, new_sgc >> 12, 12, nkmo2, 32))
    else:
        raise ValueError(f"buildKeyChangeTokens does not support EA={ea}")
    return kct
