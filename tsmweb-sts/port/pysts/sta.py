"""STA block cipher (EA=07) -- faithful port of modules/sts/sta-1.0.tm.

64-bit block, 64-bit key, 16 rounds (substitute -> permute -> rotate key).

NDA / DEMO boundary: the original ships PRODUCTION S-box/permutation tables
marked "DO NOT DISTRIBUTE; PROD table under NDA from STSA", plus DEMO tables
for testing. ONLY the DEMO tables are embedded here. A licensee with rights to
the STSA production tables can populate PROD_* below; until then mode=0 raises.
"""

from __future__ import annotations
import struct

MASK32 = 0xFFFFFFFF

PROD_ENC_SUBST = PROD_DEC_SUBST = PROD_ENC_PERM = PROD_DEC_PERM = None  # withheld (NDA)

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


class Sta:
    """STA cipher. mode: 0=production (withheld), 1=demo."""

    def __init__(self, mode: int = 1):
        if mode == 0:
            if PROD_ENC_SUBST is None:
                raise ValueError("STA production tables withheld (NDA); use mode=1 (demo)")
            self.es, self.ds, self.ep, self.dp = (
                PROD_ENC_SUBST, PROD_DEC_SUBST, PROD_ENC_PERM, PROD_DEC_PERM)
        else:
            self.es, self.ds, self.ep, self.dp = (
                DEMO_ENC_SUBST, DEMO_DEC_SUBST, DEMO_ENC_PERM, DEMO_DEC_PERM)
        self.mode = mode

    @staticmethod
    def _ror(k1, k2, n):
        mask = MASK32 >> (32 - n)
        return ((((k2 & mask) << (32 - n)) | (k1 >> n)) & MASK32,
                (((k1 & mask) << (32 - n)) | (k2 >> n)) & MASK32)

    @staticmethod
    def _rol(k1, k2, n):
        mask = MASK32 >> n
        return ((((k1 & mask) << n) | (k2 >> (32 - n))) & MASK32,
                (((k2 & mask) << n) | (k1 >> (32 - n))) & MASK32)

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

    @staticmethod
    def block_size() -> int:
        return 8
