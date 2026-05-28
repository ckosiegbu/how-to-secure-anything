"""DcmSerialSm -- hardware Security Module backend (SmBase) over STS6 serial.

Issues SM?VC / SM?VM / SM?VK / SM?VT / SM?DI / SM?CQ commands to a Prism module
via a Transport. Transfer-amount encoding happens host-side (as in the original
ApiService), so the module receives the already-compressed amount.

The host-side register map ((sgc,krn) -> register metadata) mirrors how the
vending DB tracks which numbered HSM register holds each VK; the secret key
material itself never leaves the module.
"""

from __future__ import annotations

import pysts
from . import ptvd
from .sm_base import SmBase, SmStatus, KeyRegister, IssuedToken, SmError
from .sts6_frame import build_request, parse_response, StsApiError, VERIFY_CODE


class DcmSerialSm(SmBase):
    def __init__(self, transport, api_type: str = "vending", sta_demo: bool = True):
        self.t = transport
        self.api_type = api_type
        self.regs = {}            # (sgc, krn) -> KeyRegister (+ _reg_no)
        self._by_no = {}          # reg_no -> KeyRegister

    # ---- host-side register map ----------------------------------------
    def register(self, reg_no, sgc, krn, ea, dkga, bdt=93, ti=1, kt=2, ken=0, kcv=""):
        kr = KeyRegister(reg_no=reg_no, sgc=sgc, krn=krn, ea=ea, dkga=dkga,
                         bdt=bdt, ti=ti, kt=kt, ken=ken, kcv=kcv)
        self.regs[(sgc, krn)] = kr
        self._by_no[reg_no] = kr
        return kr

    # ---- low-level rpc -------------------------------------------------
    def _rpc(self, api, cmd, params=""):
        resp = self.t.exchange(build_request(api, cmd, params))
        try:
            return parse_response(api, cmd, resp)
        except StsApiError as e:
            raise SmError(e.status, str(e))

    # ---- SmBase: status ------------------------------------------------
    def status(self) -> SmStatus:
        di = ptvd.Reader(self._rpc("SM", "DI"))
        module_id = di.scan_p(); firmware_id = di.scan_p()
        cq = ptvd.Reader(self._rpc("SM", "CQ"))
        tx = cq.scan_n()
        return SmStatus(api_type=self.api_type, module_id=module_id,
                        firmware_id=firmware_id, tx_counter=tx,
                        num_registers=len(self.regs), info={"backend": "dcm-serial"})

    # ---- SmBase: registers ---------------------------------------------
    def list_key_registers(self) -> list:
        return list(self.regs.values())

    def fetch_vk_meta(self, sgc, krn) -> KeyRegister:
        kr = self.regs.get((sgc, krn))
        if kr is None:
            raise SmError(0x22, f"no register for SGC={sgc} KRN={krn}")
        return kr

    # ---- encoding helpers ----------------------------------------------
    @staticmethod
    def _encode_amount_hex(cls, subclass, transfer_amount):
        if pysts.is_currency(cls, subclass):
            enc = pysts.encode_currency_transfer_amount(transfer_amount)
            return ("%06X" % enc), enc, True
        enc = pysts.encode_transfer_amount(int(round(transfer_amount)))
        return ("%04X" % enc), enc, False

    def _decode_amount(self, cls, subclass, enc, is_currency):
        return (pysts.decode_currency_transfer_amount(enc) if is_currency
                else pysts.decode_transfer_amount(enc))

    def _vend(self, cmd, cls, sgc, krn, pan18, ti, ea, tct, subclass, tid, transfer_amount):
        kr = self.fetch_vk_meta(sgc, krn)
        amt_hex, enc, is_cur = self._encode_amount_hex(cls, subclass, transfer_amount)
        params = ptvd.build_packet(
            "N", kr.reg_no, "P", pan18, "N", ti, "N", ea, "N", tct, "N", subclass,
            "H", bytes.fromhex(amt_hex), "H", bytes.fromhex("%06X" % (tid & 0xFFFFFF)))
        rd = ptvd.Reader(self._rpc("SM", cmd, params))
        token_hex = rd.scan_p(); token_dec = rd.scan_p()
        return IssuedToken(token_dec=token_dec, token_hex=token_hex, token_class=cls,
                           subclass=subclass, tid=tid,
                           transfer_amount=self._decode_amount(cls, subclass, enc, is_cur),
                           vk_kcv=kr.kcv)

    # ---- SmBase: token issuance ----------------------------------------
    def issue_credit_token(self, sgc, krn, pan18, ti, ea, tct, subclass, tid, transfer_amount):
        return self._vend("VC", 0, sgc, krn, pan18, ti, ea, tct, subclass, tid, transfer_amount)

    def issue_mse_token(self, sgc, krn, pan18, ti, ea, tct, subclass, tid, transfer_amount):
        return self._vend("VM", 2, sgc, krn, pan18, ti, ea, tct, subclass, tid, transfer_amount)

    def issue_key_change_tokens(self, sgc, krn, pan18, ti, ea, tct, to_sgc, to_krn,
                                to_ti, to_ken, allow_3kct=False) -> list:
        src = self.fetch_vk_meta(sgc, krn)
        dst = self.fetch_vk_meta(to_sgc, to_krn)
        num = (4 if ea == 11 else (3 if allow_3kct else 2))
        params = ptvd.build_packet("N", src.reg_no, "N", dst.reg_no, "P", pan18,
                                   "N", ti, "N", ea, "N", tct, "N", to_ti, "N", num)
        rd = ptvd.Reader(self._rpc("SM", "VK", params))
        rollover = rd.scan_n(); ntok = rd.scan_n()
        hexcat = rd.scan_p(); deccat = rd.scan_p()
        decs = [deccat[i:i + 20] for i in range(0, len(deccat), 20)]
        hexs = [hexcat[i:i + 17] for i in range(0, len(hexcat), 17)]
        out = []
        for i, (d, h) in enumerate(zip(decs, hexs)):
            advice = ({"toSgc": to_sgc, "toKrn": to_krn, "toTi": to_ti, "toKen": to_ken,
                       "toVkKcv": dst.kcv, "rollover": bool(rollover)} if i == 0 else None)
            out.append(IssuedToken(token_dec=d, token_hex=h, token_class=2,
                                   subclass=(3 if i == 0 else 4 + i - 1), tid=0,
                                   transfer_amount=0.0, vk_kcv=dst.kcv, new_config=advice))
        return out

    # ---- SmBase: verify ------------------------------------------------
    def verify_token(self, sgc, krn, pan18, ti, ea, token_dec) -> dict:
        kr = self.fetch_vk_meta(sgc, krn)
        params = ptvd.build_packet("N", kr.reg_no, "P", pan18, "N", ti, "N", ea,
                                   "P", token_dec)
        rd = ptvd.Reader(self._rpc("SM", "VT", params))
        vr = rd.scan_n(); cls = rd.scan_n(); subclass = rd.scan_n()
        amt = int.from_bytes(rd.scan_h(), "big"); tid = int.from_bytes(rd.scan_h(), "big")
        result = VERIFY_CODE.get(vr, "EVerify.Crc" if vr else "EVerify.Ok")
        out = {"validationResult": result}
        if vr == 0:
            out.update({"class": cls, "subclass": subclass, "tid": tid,
                        "transferamount": amt, "vkKcv": kr.kcv,
                        "amount": self._decode_amount(cls, subclass, amt,
                                                      pysts.is_currency(cls, subclass))})
        return out
