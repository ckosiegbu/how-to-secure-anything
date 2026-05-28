"""STS6 'hook-bang' framing (ports dbn-crypto/hsm-sts.tcl _raw_rpc/_rpc).

Request : ``{api}?{cmd}{ptvd-params}{CRC4}`` (+ CR added by the transport)
Response: ``{api}!{cmd}{RR}{ptvd-payload}{CRC4}`` (RR = 2-digit status; 00 = ok)

CRC is CRC-16/ARC (poly 0x8005, reflected, init 0) over the ASCII bytes
preceding the 4 hex CRC digits -- this is NOT the token's CCITT CRC.
"""

from __future__ import annotations

# STS6 status codes (subset of sts6v _errmsg / the SmError table).
STATUS = {
    0: "SUCCESSFUL", 1: "DEVICE_FAILURE", 3: "TOKEN_CRC", 20: "CHECKSUM_ERROR",
    21: "INVALID_REQUEST_HEADER", 22: "CSP_RECORD_EMPTY", 27: "KEK_SLOT_NOT_FOUND",
    41: "KEY_EXPIRED", 50: "LV_FORMAT_ERROR", 57: "TAMPERED_STATE", 80: "DDTK_CREDIT",
}

# Map an SM?VT validationResult code to a PrismToken EVerify.* code.
VERIFY_CODE = {0: "EVerify.Ok", 3: "EVerify.Crc", 80: "EVerify.DdtkCredit",
               41: "EVerify.KeyExpired"}


def crc16_arc(data: bytes) -> int:
    """CRC-16/ARC: poly 0x8005, init 0x0000, reflected in/out, xorout 0."""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF


def _crc_hex(body: str) -> str:
    return "%04X" % crc16_arc(body.encode("ascii"))


class StsProtocolError(Exception):
    pass


class StsApiError(Exception):
    def __init__(self, status: int, raw: str = ""):
        super().__init__(f"STS API error {STATUS.get(status, 'UNKNOWN')} (code {status})")
        self.status = status
        self.raw = raw


def build_request(api: str, cmd: str, params: str = "") -> str:
    body = f"{api}?{cmd}{params}"
    return body + _crc_hex(body)


def parse_request(line: str) -> tuple:
    """Returns (api, cmd, params). Verifies CRC. (For the emulator.)"""
    line = line.rstrip("\r")
    if len(line) < 7 or line[2] != "?":
        raise StsProtocolError("bad request header")
    if _crc_hex(line[:-4]) != line[-4:]:
        raise StsProtocolError("request CRC error")
    return line[0:2], line[3:5], line[5:-4]


def build_response(api: str, cmd: str, status: int, payload: str = "") -> str:
    body = f"{api}!{cmd}{status:02d}{payload}"
    return body + _crc_hex(body)


def parse_response(api: str, cmd: str, line: str) -> str:
    """Returns the PTVD payload on success; raises StsApiError/StsProtocolError."""
    line = line.rstrip("\r")
    # GL!ER short responses may carry no CRC
    if len(line) < 11:
        if line.startswith("GL!ER"):
            raise StsApiError(int(line[5:7] or 99), line)
        raise StsProtocolError(f"response too short: {line!r}")
    if _crc_hex(line[:-4]) != line[-4:]:
        raise StsProtocolError("response CRC error")
    body = line[:-4]
    status = int(body[5:7])
    if status != 0:
        raise StsApiError(status, line)
    if body[0:5] != f"{api}!{cmd}":
        raise StsProtocolError(f"header mismatch: expected {api}!{cmd} got {body[0:5]}")
    return body[7:]
