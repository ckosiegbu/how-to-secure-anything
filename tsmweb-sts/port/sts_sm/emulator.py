"""SoftSm6Emulator -- an in-process STS6 module that speaks the wire protocol.

It parses framed SM?xx requests and produces framed responses using the pysts
engine, so DcmSerialSm can be integration-tested (over LoopbackTransport)
without a physical module. Keys live in numbered registers, exactly like real
hardware. EA=11/MISTY1 is production-faithful; EA=7/STA uses demo tables.
"""

from __future__ import annotations
import os
import time

import pysts
from . import ptvd
from .sts6_frame import parse_request, build_response, StsApiError, StsProtocolError


class SoftSm6Emulator:
    def __init__(self, module_id: str = "00000001", firmware_id: str = "EMUL0001",
                 sta_mode: int = 1, tx_counter: int = 1_000_000):
        self.module_id = module_id
        self.firmware_id = firmware_id
        self.sta_mode = sta_mode
        self.tx_counter = tx_counter
        self.regs = {}            # reg_no -> dict(vk, ea, dkga, bdt, ti, kt, sgc, krn, ken)

    def load(self, reg_no, sgc, krn, vk: bytes, ea, dkga, bdt=93, ti=1, kt=2, ken=0):
        self.regs[reg_no] = dict(vk=vk, ea=ea, dkga=dkga, bdt=bdt, ti=ti, kt=kt,
                                 sgc=sgc, krn=krn, ken=ken)

    # ---- request dispatch ----------------------------------------------
    def handle(self, request: str) -> str:
        try:
            api, cmd, params = parse_request(request)
        except StsProtocolError:
            return build_response("GL", "ER", 20)        # CHECKSUM_ERROR
        try:
            fn = getattr(self, f"_cmd_{api}{cmd}", None)
            if fn is None:
                return build_response(api, cmd if len(cmd) == 2 else "ER", 21)  # INVALID_REQUEST_HEADER
            payload = fn(ptvd.Reader(params))
            return build_response(api, cmd, 0, payload)
        except StsApiError as e:
            return build_response(api, cmd, e.status)
        except Exception:
            return build_response(api, cmd, 1)           # DEVICE_FAILURE

    def _reg(self, reg_no):
        r = self.regs.get(reg_no)
        if r is None:
            raise StsApiError(22)                        # CSP_RECORD_EMPTY
        return r

    def _spend(self):
        if self.tx_counter <= 0:
            raise StsApiError(1)
        self.tx_counter -= 1

    # ---- status --------------------------------------------------------
    def _cmd_SMDI(self, r):
        return ptvd.build_packet("P", self.module_id, "P", self.firmware_id)

    def _cmd_SMCQ(self, r):
        return ptvd.build_packet("N", self.tx_counter, "P", self.module_id,
                                 "H", os.urandom(8),
                                 "D", time.strftime("%Y%m%d%H%M%S", time.gmtime()))

    def _cmd_SMGA(self, reader):
        reg = self._reg(reader.scan_n())
        attrs = f"SGC={reg['sgc']};KRN={reg['krn']};EA={reg['ea']};DKGA={reg['dkga']};BDT={reg['bdt']};KEN={reg['ken']}"
        return ptvd.build_packet("P", attrs)

    # ---- vend ----------------------------------------------------------
    def _vend(self, cls, reader):
        reg_no = reader.scan_n(); pan = reader.scan_p()
        ti = reader.scan_n(); ea = reader.scan_n(); tct = reader.scan_n()
        subclass = reader.scan_n()
        amt = int.from_bytes(reader.scan_h(), "big")     # already-encoded amount
        tid = int.from_bytes(reader.scan_h(), "big")
        reader.scan_end()
        reg = self._reg(reg_no)
        self._spend()
        rnd = int.from_bytes(os.urandom(1), "big") & 0x0F
        res = pysts.vk_create_token(reg["vk"], reg["sgc"], pan, reg["krn"], reg["kt"],
                                    reg["dkga"], reg["bdt"], ti, ea, cls, subclass, rnd,
                                    tid, amt, encode_amount=False, sta_mode=self.sta_mode)
        thex = ("%017X" % int(res["token20d"]))
        return ptvd.build_packet("P", thex, "P", res["token20d"])

    def _cmd_SMVC(self, reader):
        return self._vend(0, reader)

    def _cmd_SMVM(self, reader):
        return self._vend(2, reader)

    def _cmd_SMVT(self, reader):
        reg_no = reader.scan_n(); pan = reader.scan_p()
        ti = reader.scan_n(); ea = reader.scan_n(); token_dec = reader.scan_p()
        reader.scan_end()
        reg = self._reg(reg_no)
        try:
            info = pysts.vk_verify_token(reg["vk"], reg["sgc"], pan, reg["krn"], reg["kt"],
                                         reg["dkga"], reg["bdt"], ti, ea, token_dec,
                                         sta_mode=self.sta_mode)
        except ValueError:
            return ptvd.build_packet("N", 3, "N", 0, "N", 0, "H", b"", "H", b"")
        amt_hex = bytes.fromhex("%04X" % (info["transferamount"] & 0xFFFF))
        tid_hex = bytes.fromhex("%06X" % (info["tid"] & 0xFFFFFF))
        return ptvd.build_packet("N", 0, "N", info["class"], "N", info["subclass"],
                                 "H", amt_hex, "H", tid_hex)

    def _cmd_SMVK(self, reader):
        old = reader.scan_n(); new = reader.scan_n(); pan = reader.scan_p()
        ti_old = reader.scan_n(); ea = reader.scan_n(); tct = reader.scan_n()
        ti_new = reader.scan_n(); num = reader.scan_n()
        reader.scan_end()
        ro = self._reg(old); rn = self._reg(new)
        self._spend()
        three_kct = 1 if (ea in (7, 107) and num == 3) else 0
        toks = pysts.vk_create_key_change_tokens(
            ro["vk"], ro["sgc"], ro["krn"], ro["kt"], ro["dkga"], ro["bdt"], pan, ti_old, ea,
            new_vk=rn["vk"], new_dkga=rn["dkga"], new_bdt=rn["bdt"], new_sgc=rn["sgc"],
            new_krn=rn["krn"], new_ti=ti_new, new_ken=rn["ken"], new_kt=rn["kt"],
            three_kct=three_kct, sta_mode=self.sta_mode)
        rollover = 1 if (pysts.EPOCHS[rn["bdt"]] - pysts.EPOCHS[ro["bdt"]]) > 0 else 0
        hexcat = "".join("%017X" % int(t) for t in toks)
        deccat = "".join(t for t in toks)
        return ptvd.build_packet("N", rollover, "N", len(toks), "P", hexcat, "P", deccat)
