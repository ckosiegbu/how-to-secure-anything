"""VirtualHsm -- in-process software Security Module (drop-in SmBase backend).

Implements the SM contract using the pysts crypto engine and an encrypted
Keystore. EA=11 (MISTY1) is production-faithful; EA=7 (STA) runs on DEMO
tables until production STSA tables are supplied (sta_mode=1).
"""

from __future__ import annotations
import os

import pysts
from .sm_base import (SmBase, SmStatus, KeyRegister, IssuedToken, SmError)
from .keystore import Keystore


class VirtualHsm(SmBase):
    def __init__(self, keystore: Keystore, module_id: str = "VHSM0001",
                 firmware_id: str = "pysts-vhsm-1.0", sta_mode: int = 1,
                 api_type: str = "vending"):
        self.ks = keystore
        self.module_id = module_id
        self.firmware_id = firmware_id
        self.sta_mode = sta_mode          # 1 = demo STA tables (EA=7)
        self.api_type = api_type

    # ----- provisioning (software analogue of SM?KL load-vending-key) ----
    def load_vending_key(self, sgc, krn, vk: bytes, ea, dkga, bdt=93, ti=1,
                         kt=2, ken=0) -> KeyRegister:
        kcv = pysts.vk_kcv(dkga, vk).hex().upper()
        meta = dict(sgc=sgc, krn=krn, ea=ea, dkga=dkga, bdt=bdt, ti=ti,
                    kt=kt, ken=ken, kcv=kcv)
        reg = self.ks.add_register(meta, vk)
        return self._reg(self.ks.get(reg))

    def enable_vending(self, count: int):
        """Software analogue of loadTransactionLicense / SM?CI."""
        self.ks.set_tx_counter(count)

    # ----- SmBase: status -----------------------------------------------
    def status(self) -> SmStatus:
        return SmStatus(api_type=self.api_type, module_id=self.module_id,
                        firmware_id=self.firmware_id, tx_counter=self.ks.tx_counter,
                        num_registers=len(self.ks.registers()),
                        info={"backend": "virtual", "sta_mode": str(self.sta_mode)})

    # ----- SmBase: registers --------------------------------------------
    @staticmethod
    def _reg(rec: dict) -> KeyRegister:
        return KeyRegister(reg_no=rec["reg_no"], sgc=rec["sgc"], krn=rec["krn"],
                           ea=rec["ea"], dkga=rec["dkga"], bdt=rec["bdt"],
                           ti=rec["ti"], kt=rec["kt"], ken=rec["ken"], kcv=rec["kcv"])

    def list_key_registers(self) -> list:
        return [self._reg(r) for r in self.ks.registers()]

    def fetch_vk_meta(self, sgc, krn) -> KeyRegister:
        try:
            return self._reg(self.ks.find(sgc, krn))
        except KeyError as e:
            raise SmError(0x22, str(e))   # CSP_RECORD_EMPTY

    # ----- helpers ------------------------------------------------------
    def _rec_vk(self, sgc, krn):
        try:
            rec = self.ks.find(sgc, krn)
        except KeyError as e:
            raise SmError(0x22, str(e))
        return rec, self.ks.vk_bytes(rec)

    def _issue(self, cls, sgc, krn, pan18, ti, ea, subclass, tid, transfer_amount):
        rec, vk = self._rec_vk(sgc, krn)
        self.ks.consume_transaction()
        rnd = int.from_bytes(os.urandom(1), "big") & 0x0F
        amt = transfer_amount
        if not pysts.is_currency(cls, subclass) and cls == 0:
            amt = int(round(transfer_amount))
        res = pysts.vk_create_token(vk, sgc, pan18, krn, rec["kt"], rec["dkga"],
                                    rec["bdt"], ti, ea, cls, subclass, rnd, tid,
                                    amt, encode_amount=True, sta_mode=self.sta_mode)
        info = pysts.vk_verify_token(vk, sgc, pan18, krn, rec["kt"], rec["dkga"],
                                     rec["bdt"], ti, ea, res["token20d"],
                                     sta_mode=self.sta_mode)
        token_hex = "%017x" % int(res["token20d"])  # 17 hex digits (66-bit)
        return IssuedToken(token_dec=res["token20d"], token_hex=token_hex.upper(),
                           token_class=cls, subclass=subclass, tid=tid,
                           transfer_amount=info["amount"], vk_kcv=rec["kcv"])

    # ----- SmBase: token issuance ---------------------------------------
    def issue_credit_token(self, sgc, krn, pan18, ti, ea, tct, subclass, tid,
                           transfer_amount) -> IssuedToken:
        return self._issue(0, sgc, krn, pan18, ti, ea, subclass, tid, transfer_amount)

    def issue_mse_token(self, sgc, krn, pan18, ti, ea, tct, subclass, tid,
                        transfer_amount) -> IssuedToken:
        return self._issue(2, sgc, krn, pan18, ti, ea, subclass, tid, transfer_amount)

    def issue_key_change_tokens(self, sgc, krn, pan18, ti, ea, tct, to_sgc,
                                to_krn, to_ti, to_ken, allow_3kct=False) -> list:
        src, src_vk = self._rec_vk(sgc, krn)
        dst, dst_vk = self._rec_vk(to_sgc, to_krn)
        self.ks.consume_transaction()
        toks = pysts.vk_create_key_change_tokens(
            src_vk, sgc, krn, src["kt"], src["dkga"], src["bdt"], pan18, ti, ea,
            new_vk=dst_vk, new_dkga=dst["dkga"], new_bdt=dst["bdt"],
            new_sgc=to_sgc, new_krn=to_krn, new_ti=to_ti, new_ken=to_ken,
            new_kt=dst["kt"], three_kct=1 if allow_3kct else 0, sta_mode=self.sta_mode)
        out = []
        for i, t in enumerate(toks):
            out.append(IssuedToken(token_dec=t, token_hex=("%017x" % int(t)).upper(),
                                   token_class=2, subclass=(3 if i == 0 else 4 + i - 1),
                                   tid=0, transfer_amount=0.0, vk_kcv=dst["kcv"],
                                   new_config=({"toSgc": to_sgc, "toKrn": to_krn,
                                                "toTi": to_ti, "toKen": to_ken,
                                                "toVkKcv": dst["kcv"]} if i == 0 else None)))
        return out

    # ----- SmBase: verify -----------------------------------------------
    def verify_token(self, sgc, krn, pan18, ti, ea, token_dec) -> dict:
        rec, vk = self._rec_vk(sgc, krn)
        try:
            info = pysts.vk_verify_token(vk, sgc, pan18, krn, rec["kt"], rec["dkga"],
                                         rec["bdt"], ti, ea, token_dec,
                                         sta_mode=self.sta_mode)
        except ValueError:
            return {"validationResult": "EVerify.Crc"}
        info["validationResult"] = "EVerify.Ok"
        info["vkKcv"] = rec["kcv"]
        return info
