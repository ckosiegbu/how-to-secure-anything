"""DKGA -- STS Decoder Key Generation Algorithms + Key Check Values.

Faithful port of modules/sts/dkga-1.0.tm and the KCV helpers in
modules/sts/softalg-1.0.tm (dkKcvBin / vkKcvBin).
"""

from __future__ import annotations
import hmac
import hashlib
import struct

from Crypto.Cipher import DES

EA_KEYLEN_BITS = {7: 64, 9: 64, 11: 128}


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def set_odd_parity(key: bytes) -> bytes:
    """dbnlib set_parity ... odd: parity bit (LSB) forced for odd 1-count per byte."""
    out = bytearray()
    for b in key:
        if bin(b & 0xFE).count("1") % 2 == 0:
            out.append((b & 0xFE) | 1)
        else:
            out.append(b & 0xFE)
    return bytes(out)


def _des_ecb(key8: bytes, data8: bytes) -> bytes:
    return DES.new(key8, DES.MODE_ECB).encrypt(data8)


def _control_block(kt, sgc, ti, krn) -> bytes:
    return bytes.fromhex("%x%06d%02d%dFFFFFF" % (kt, sgc, ti, krn))


def dkga01(vk: bytes, sgc: int, pan18: str, kt=2, ti=1, krn=1) -> bytes:
    panblock = bytes.fromhex(pan18[1:17])
    datablock = _xor(panblock, _control_block(kt, sgc, ti, krn))
    vk_odd = set_odd_parity(vk)
    dstk = _des_ecb(datablock, vk_odd)        # DKGA01: datablock is the DES key
    return _xor(dstk, vk_odd)


def dkga02(vk: bytes, sgc: int, pan18: str, kt=2, ti=1, krn=1) -> bytes:
    panblock = bytes.fromhex(pan18[1:17])
    datablock = _xor(panblock, _control_block(kt, sgc, ti, krn))
    encblock = _des_ecb(vk, datablock)
    return _xor(_xor(encblock, datablock), set_odd_parity(vk))


def _lvconcat(*parts: bytes) -> bytes:
    return b"".join(bytes([len(p)]) + p for p in parts)


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


def derive_dk(dkga: int, vk: bytes, sgc: int, pan18: str,
              kt=2, ti=1, krn=1, ea=7, bdt=93) -> bytes:
    """Pick the DKGA per spec rules and return the decoder key (8 or 16 bytes).

    Note: the full IEC table-31/32 routing that can downgrade DKGA01->02 is in
    the original deriveDk; here dkga is taken as given (1/2/4). KT=3 forces the
    common PAN.
    """
    if kt == 3:
        pan18 = "600727000000000000"
    if dkga == 1:
        return dkga01(vk, sgc, pan18, kt, ti, krn)
    if dkga == 2:
        return dkga02(vk, sgc, pan18, kt, ti, krn)
    if dkga == 4:
        return dkga04(vk, sgc, pan18, kt, ti, krn, ea, bdt)
    raise ValueError(f"unsupported dkga={dkga}")


def vk_kcv(dkga: int, vk: bytes) -> bytes:
    """3-byte Key Check Value of a vending/decoder key (softalg vkKcvBin)."""
    if dkga in (1, 2):
        return _des_ecb(vk, b"\x00" * 8)[:3]
    if dkga == 4:
        return hashlib.sha256(b"\x01" + vk).digest()[:3]
    raise ValueError(f"unsupported dkga={dkga}")


def dk_kcv(ea: int, dk: bytes) -> bytes:
    """3-byte KCV of a decoder key for the given EA (softalg dkKcvBin)."""
    if ea in (7, 107):
        return vk_kcv(2, dk)
    if ea == 11:
        return vk_kcv(4, dk)
    raise ValueError(f"unsupported ea={ea}")
