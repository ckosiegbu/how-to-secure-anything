"""
sts_engine.py -- Clean-room Python port of the STS prepaid-token engine.

Ported from the decompiled Tcl of "Prism TsmWeb-STS 4.70.2"
(modules/sts/{dkga,sta,softalg,common}). Implements:

  * DKGA01 / DKGA02 (DES-based) and DKGA04 (KDF108-Feedback-HMAC-SHA256)
    decoder-key derivation  (IEC 62055-41 / STS202-3)
  * The STA block cipher (EA=07)  (IEC 62055-41 s6.5.4)
  * The class-0/1/2 token codec: clear-token build, CRC-16, datablock
    assembly, class-bit transpose, 20-digit encoding, and the inverse.

IMPORTANT -- NDA / DEMO boundary
--------------------------------
The STA substitution & permutation S-boxes ship in two flavours in the
original source: a PRODUCTION set explicitly marked "DO NOT DISTRIBUTE;
PROD table under NDA from STSA", and a DEMO/sample set for testing.

This port embeds ONLY the DEMO tables. It therefore produces internally
consistent (encrypt<->decrypt round-trip) tokens for development/testing,
but NOT tokens a real production meter will accept. A licensee with rights
to the STSA production tables can drop them into PROD_* below.

Dependencies: pycryptodome (DES) + stdlib hmac/hashlib.
"""

from __future__ import annotations
import hmac
import hashlib
import struct
from datetime import datetime, timezone

from Crypto.Cipher import DES


# --------------------------------------------------------------------------
# STA constant tables  (mode 0 = production [NOT INCLUDED], 1 = demo)
# --------------------------------------------------------------------------

# Production tables are withheld (NDA). Drop them in here if licensed.
PROD_ENC_SUBST = PROD_DEC_SUBST = PROD_ENC_PERM = PROD_DEC_PERM = None

DEMO_ENC_SUBST = (
    (12, 10, 8, 4, 3, 15, 0, 2, 14, 1, 5, 13, 6, 9, 7, 11),
    (6, 9, 7, 4, 3, 10, 12, 14, 2, 13, 1, 15, 0, 11, 8, 5),
)
DEMO_DEC_SUBST = (
    (12, 10, 8, 4, 3, 15, 0, 2, 14, 1, 5, 13, 6, 9, 7, 11),
    (6, 9, 7, 4, 3, 10, 12, 14, 2, 13, 1, 15, 0, 11, 8, 5),
)
DEMO_ENC_PERM = (
    29, 27, 34, 9, 16, 62, 55, 2, 40, 49, 38, 25, 33, 61, 30, 23,
    1, 41, 21, 57, 42, 15, 5, 58, 19, 53, 22, 17, 48, 28, 24, 39,
    3, 60, 36, 14, 11, 52, 54, 12, 31, 51, 10, 26, 0, 45, 37, 43,
    44, 6, 59, 4, 7, 35, 56, 50, 13, 18, 32, 47, 46, 63, 20, 8,
)
DEMO_DEC_PERM = (
    44, 16, 7, 32, 51, 22, 49, 52, 63, 3, 42, 36, 39, 56, 35, 21,
    4, 27, 57, 24, 62, 18, 26, 15, 30, 11, 43, 1, 29, 0, 14, 40,
    58, 12, 2, 53, 34, 46, 10, 31, 8, 17, 20, 47, 48, 45, 60, 59,
    28, 9, 55, 41, 37, 25, 38, 6, 54, 19, 23, 50, 33, 13, 5, 61,
)

MASK32 = 0xFFFFFFFF


class Sta:
    """STA block cipher (EA=07), 64-bit block, 64-bit key. Pure Python."""

    def __init__(self, mode: int = 1):
        if mode == 0:
            if PROD_ENC_SUBST is None:
                raise ValueError("production STA tables withheld (NDA); use mode=1 (demo)")
            self.es, self.ds = PROD_ENC_SUBST, PROD_DEC_SUBST
            self.ep, self.dp = PROD_ENC_PERM, PROD_DEC_PERM
        else:
            self.es, self.ds = DEMO_ENC_SUBST, DEMO_DEC_SUBST
            self.ep, self.dp = DEMO_ENC_PERM, DEMO_DEC_PERM

    @staticmethod
    def _ror(k1, k2, n):
        mask = MASK32 >> (32 - n)
        return (((k2 & mask) << (32 - n)) | (k1 >> n)) & MASK32, \
               (((k1 & mask) << (32 - n)) | (k2 >> n)) & MASK32

    @staticmethod
    def _rol(k1, k2, n):
        mask = MASK32 >> n
        return (((k1 & mask) << n) | (k2 >> (32 - n))) & MASK32, \
               (((k2 & mask) << n) | (k1 >> (32 - n))) & MASK32

    @staticmethod
    def _substitute(table, kpart, dpart):
        dout = 0
        for i in range(7, -1, -1):
            tablenum = ((kpart >> (i * 4)) & 8) >> 3
            index = (dpart >> (i * 4)) & 0x0F
            dout = (dout << 4) | table[tablenum][index]
        return dout & MASK32

    @staticmethod
    def _permute(table, d1, d2):
        d1o = d2o = 0
        for i, opos in enumerate(table):
            bit = ((d2 >> i) if i < 32 else (d1 >> (i - 32))) & 1
            if bit:
                if opos < 32:
                    d2o |= (1 << opos)
                else:
                    d1o |= (1 << (opos - 32))
        return d1o, d2o

    def encrypt(self, key8: bytes, data8: bytes) -> bytes:
        k1, k2 = struct.unpack(">II", key8)
        d1, d2 = struct.unpack(">II", data8)
        k1 ^= MASK32
        k2 ^= MASK32
        k1, k2 = self._ror(k1, k2, 12)
        for _ in range(16):
            d1 = self._substitute(self.es, k1, d1)
            d2 = self._substitute(self.es, k2, d2)
            d1, d2 = self._permute(self.ep, d1, d2)
            k1, k2 = self._rol(k1, k2, 1)
        return struct.pack(">II", d1, d2)

    def decrypt(self, key8: bytes, data8: bytes) -> bytes:
        k1, k2 = struct.unpack(">II", key8)
        d1, d2 = struct.unpack(">II", data8)
        k1, k2 = self._rol(k1, k2, 3)
        for _ in range(16):
            d1, d2 = self._permute(self.dp, d1, d2)
            d1 = self._substitute(self.ds, k1, d1)
            d2 = self._substitute(self.ds, k2, d2)
            k1, k2 = self._ror(k1, k2, 1)
        return struct.pack(">II", d1, d2)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def set_odd_parity(key: bytes) -> bytes:
    """Force odd parity on each byte (parity bit = LSB), as dbnlib set_parity."""
    out = bytearray()
    for b in key:
        if bin(b & 0xFE).count("1") % 2 == 0:
            out.append((b & 0xFE) | 1)
        else:
            out.append(b & 0xFE)
    return bytes(out)


def _des_ecb(key8: bytes, data8: bytes) -> bytes:
    return DES.new(key8, DES.MODE_ECB).encrypt(data8)


def crc16_ccitt(data: bytes, seed: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, no reflection, no final xor) -- the STS CRC."""
    crc = seed
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if (crc & 0x8000) else (crc << 1)
            crc &= 0xFFFF
    return crc


# --------------------------------------------------------------------------
# DKGA -- decoder-key derivation
# --------------------------------------------------------------------------

EA_KEYLEN_BITS = {7: 64, 9: 64, 11: 128}


def dkga01(vk: bytes, sgc: int, pan18: str, kt=2, ti=1, krn=1) -> bytes:
    panblock = bytes.fromhex(pan18[1:17])
    controlblock = bytes.fromhex("%x%06d%02d%dFFFFFF" % (kt, sgc, ti, krn))
    datablock = _xor(panblock, controlblock)
    vk_odd = set_odd_parity(vk)
    dstk = _des_ecb(datablock, vk_odd)        # NB: DKGA01 uses datablock as the DES key
    return _xor(dstk, vk_odd)


def dkga02(vk: bytes, sgc: int, pan18: str, kt=2, ti=1, krn=1) -> bytes:
    panblock = bytes.fromhex(pan18[1:17])
    controlblock = bytes.fromhex("%x%06d%02d%dFFFFFF" % (kt, sgc, ti, krn))
    datablock = _xor(panblock, controlblock)
    encblock = _des_ecb(vk, datablock)
    return _xor(_xor(encblock, datablock), set_odd_parity(vk))


def dkga04(vk: bytes, sgc: int, pan18: str, kt=2, ti=1, krn=1, ea=7, bdt=93,
           keylen_bits=None) -> bytes:
    if keylen_bits is None:
        keylen_bits = EA_KEYLEN_BITS[ea]
    label = _lvconcat(b"04", b"%02d" % bdt, b"%02d" % ea, b"%02d" % ti)
    context = _lvconcat(b"%06d" % sgc, b"%01d" % kt, b"%01d" % krn, pan18.encode())
    other = label + b"\x00" + context
    L = struct.pack(">I", keylen_bits)
    k1 = hmac.new(vk, other + L, hashlib.sha256).digest()
    return k1[: keylen_bits // 8]


def _lvconcat(*parts: bytes) -> bytes:
    """util::encode::lvconcat -- each item prefixed by a 1-byte length."""
    return b"".join(bytes([len(p)]) + p for p in parts)


def derive_dk(dkga: int, vk: bytes, sgc: int, pan18: str,
              kt=2, ti=1, krn=1, ea=7, bdt=93) -> bytes:
    if kt == 3:
        pan18 = "600727000000000000"[:18]
    if dkga in (1, 2):
        return dkga01(vk, sgc, pan18, kt, ti, krn) if dkga == 1 \
            else dkga02(vk, sgc, pan18, kt, ti, krn)
    if dkga == 4:
        return dkga04(vk, sgc, pan18, kt, ti, krn, ea, bdt)
    raise ValueError(f"unsupported dkga={dkga}")


# --------------------------------------------------------------------------
# Token codec  (class 0/1/2; STA EA=07)
# --------------------------------------------------------------------------

EPOCHS = {
    93: int(datetime(1993, 1, 1, tzinfo=timezone.utc).timestamp()),
    14: int(datetime(2014, 1, 1, tzinfo=timezone.utc).timestamp()),
    35: int(datetime(2035, 1, 1, tzinfo=timezone.utc).timestamp()),
}


def token_id_from_time(unixtime: int, bdt=93) -> int:
    return (unixtime - EPOCHS[bdt]) // 60


def is_currency(cls: int, subclass: int) -> bool:
    return cls == 0 and 4 <= subclass <= 7


def _swap16(v: int) -> int:
    return ((v & 0xFF) << 8) | ((v >> 8) & 0xFF)


def _transpose_class_bits(tv: int) -> int:
    lobits = (tv >> 27) & 3
    hibits = (tv >> 64) & 3
    return (lobits << 64) | ((tv & 0xFFFFFFFFE7FFFFFF) | ((hibits & 3) << 27))


def encode_transfer_amount(amt: int) -> int:
    """16-bit STS TransferAmount mantissa/exponent encoding (IEC 62055-41 s6.3.6)."""
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
    exp = (ta >> 14) & 3
    m = ta & 0x3FFF
    t = (10 ** exp) * m
    for n in range(1, exp + 1):
        t += 0x4000 * 10 ** (n - 1)
    return t


def build_clear_token(cls: int, subclass: int, content44: int) -> int:
    """Return the 66-bit clear token int (incl. byte-swapped CRC), as makeClearTokenInt."""
    cleartok = ((cls & 3) << 48) | ((subclass & 0xF) << 44) | (content44 & ((1 << 44) - 1))
    tokstr = cleartok.to_bytes(8, "big")[1:]          # 56-bit field
    if is_currency(cls, subclass):
        tokstr += b"\x01"
    crc = crc16_ccitt(tokstr)
    return (cleartok << 16) | _swap16(crc)


def encrypt_token(cipher: Sta, dk: bytes, cls: int, subclass: int, content44: int) -> str:
    cleartok = ((cls & 3) << 48) | ((subclass & 0xF) << 44) | (content44 & ((1 << 44) - 1))
    tokstr = cleartok.to_bytes(8, "big")[1:]
    if is_currency(cls, subclass):
        tokstr += b"\x01"
    crc = crc16_ccitt(tokstr)
    lower48 = cleartok & ((1 << 48) - 1)               # subclass|content
    datablock = (lower48 << 16) | _swap16(crc)         # 64-bit
    enc = cipher.encrypt(dk, datablock.to_bytes(8, "big"))
    enc66 = (cls << 64) | int.from_bytes(enc, "big")
    return "%020d" % _transpose_class_bits(enc66)


def decrypt_token(cipher: Sta, dk: bytes, token20d: str) -> dict:
    tv = int(token20d)
    det = _transpose_class_bits(tv)                    # involution
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
    if crc16_ccitt(tokstr) != crc_stored:
        raise ValueError("CRC check failed (wrong key, tables, or corrupt token)")
    return {
        "class": cls, "subclass": subclass, "content": content,
        "rnd": (content >> 40) & 0xF,
        "tid": (content >> 16) & 0xFFFFFF,
        "amount": content & 0xFFFF,
    }


# --------------------------------------------------------------------------
# High-level: vending-key -> token   (mirrors sts::vkCreateToken / vkVerifyToken)
# --------------------------------------------------------------------------

def vk_create_credit_token(vk, sgc, pan18, krn, kt, dkga, bdt, ti, ea,
                           subclass, amount, tid, rnd=0, encode_amount=True,
                           mode=1) -> str:
    dk = derive_dk(dkga, vk, sgc, pan18, kt, ti, krn, ea, bdt)
    amt = encode_transfer_amount(amount) if encode_amount else amount
    content = ((rnd & 0xF) << 40) | ((tid & 0xFFFFFF) << 16) | (amt & 0xFFFF)
    return encrypt_token(Sta(mode), dk, 0, subclass, content)


def vk_verify_token(vk, sgc, pan18, krn, kt, dkga, bdt, ti, ea, token20d, mode=1) -> dict:
    dk = derive_dk(dkga, vk, sgc, pan18, kt, ti, krn, ea, bdt)
    return decrypt_token(Sta(mode), dk, token20d)


# --------------------------------------------------------------------------
# Self-test (round-trip; DEMO tables)
# --------------------------------------------------------------------------

if __name__ == "__main__":
    VK = bytes.fromhex("ABABABABABABABAB")
    SGC, PAN, KRN, KT, DKGA, BDT, TI, EA = 123456, "000000000000000000", 1, 2, 2, 93, 1, 7

    print("=== STS engine self-test (DEMO tables) ===")
    dk = derive_dk(DKGA, VK, SGC, PAN, KT, TI, KRN, EA, BDT)
    print("DKGA02 decoder key:", dk.hex())

    units = 50              # 50 kWh-ish (encoded)
    tid = token_id_from_time(int(datetime(2021, 4, 12, 9, 0, tzinfo=timezone.utc).timestamp()), BDT)
    print("TID:", tid)

    tok = vk_create_credit_token(VK, SGC, PAN, KRN, KT, DKGA, BDT, TI, EA,
                                 subclass=0, amount=units, tid=tid, rnd=7)
    print("Encrypted 20-digit token:", tok)

    info = vk_verify_token(VK, SGC, PAN, KRN, KT, DKGA, BDT, TI, EA, tok)
    print("Decrypted:", info)

    assert info["class"] == 0 and info["subclass"] == 0
    assert info["tid"] == tid
    assert info["rnd"] == 7
    assert decode_transfer_amount(info["amount"]) == 50
    print("decoded units:", decode_transfer_amount(info["amount"]), "kWh")

    # STA cipher is invertible for arbitrary blocks
    c = Sta(1)
    import os
    k, d = os.urandom(8), os.urandom(8)
    assert c.decrypt(k, c.encrypt(k, d)) == d

    # TransferAmount codec round-trips across all 3 exponent bands
    for a in (0, 1, 16383, 16384, 180223, 180224, 1818623, 1818624, 18201624):
        assert decode_transfer_amount(encode_transfer_amount(a)) >= a

    print("ALL ROUND-TRIP TESTS PASSED")
