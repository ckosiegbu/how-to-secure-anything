"""PTVD -- Printable Type-Value-Delimiter field encoding (ports net/Ptvd-1.0.tm).

Each field is `<T><value>~` where T is the wire type and `~` (0x7E) delimits.
  N : decimal integer 0..2147483647, no leading zeros
  P : printable ASCII (no `~`)
  H : octets, encoded as UPPERCASE hex pairs
  D : date/time string 'YYYYMMDDhhmmss'
A packet is the concatenation of fields.
"""

from __future__ import annotations

DELIM = "~"


def fmt_n(value: int) -> str:
    v = int(value)
    if not (0 <= v <= 2147483647):
        raise ValueError("PTVD N out of range")
    return f"N{v}~"


def fmt_p(value: str) -> str:
    if DELIM in value:
        raise ValueError("PTVD P may not contain '~'")
    if not value.isascii() or not value.isprintable():
        # allow empty; isprintable('')==True
        raise ValueError("PTVD P must be printable ASCII")
    return f"P{value}~"


def fmt_h(value: bytes) -> str:
    return f"H{value.hex().upper()}~"


def fmt_d(value: str) -> str:
    if len(value) != 14 or not value.isdigit():
        raise ValueError("PTVD D must be 14 digits YYYYMMDDhhmmss")
    return f"D{value}~"


_FMT = {"N": fmt_n, "P": fmt_p, "H": fmt_h, "D": fmt_d}


def build_packet(*pairs) -> str:
    """build_packet('N', 1, 'P', 'foo', 'H', b'\\x01') -> 'N1~Pfoo~H01~'."""
    out = []
    it = iter(pairs)
    for t, v in zip(it, it):
        out.append(_FMT[t](v))
    return "".join(out)


class Reader:
    """Cursor over a PTVD packet; scan_* mirror Ptvd::scanN/scanP/scanH/scanD."""

    def __init__(self, packet: str):
        self.pkt = packet
        self.ofs = 0

    def _field(self, expect: str | None = None) -> tuple:
        if self.ofs >= len(self.pkt):
            raise ValueError("PTVD overflow: read past end of packet")
        wire = self.pkt[self.ofs]
        end = self.pkt.find(DELIM, self.ofs + 1)
        if end < 0:
            raise ValueError("PTVD encoding: missing end-of-field '~'")
        raw = self.pkt[self.ofs + 1:end]
        self.ofs = end + 1
        if expect and expect != wire:
            raise ValueError(f"PTVD type: expected {expect} got {wire}")
        return wire, raw

    def scan_n(self) -> int:
        _, raw = self._field("N")
        if raw != "0" and raw.startswith("0"):
            raise ValueError("PTVD N leading zeros")
        return int(raw)

    def scan_p(self) -> str:
        return self._field("P")[1]

    def scan_h(self) -> bytes:
        raw = self._field("H")[1]
        if len(raw) % 2:
            raise ValueError("PTVD H odd length")
        return bytes.fromhex(raw)

    def scan_d(self) -> str:
        return self._field("D")[1]

    def at_end(self) -> bool:
        return self.ofs == len(self.pkt)

    def scan_end(self):
        if not self.at_end():
            raise ValueError("PTVD trailing data")
