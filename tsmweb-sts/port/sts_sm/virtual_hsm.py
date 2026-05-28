"""VirtualHsm -- in-process software Security Module (drop-in SmBase backend).

Implements the SM contract using the pysts crypto engine and an encrypted
Keystore. Decoder-key derivation (DKGA) is memoised per (register, pan, ti, ea)
in an LRU cache -- the main throughput lever, since DKGA is the costly step and
a meter is typically vended to repeatedly. EA=11 (MISTY1) is production-faithful;
EA=7 (STA) runs on DEMO tables until production STSA tables are supplied.
"""

from __future__ import annotations
import os

import pysts
from pysts import codec
from .sm_base import SmBase, SmStatus, KeyRegister, IssuedToken, SmError
from .keystore import Keystore
from .cache import LruCache


def _cipher_for(ea: int, sta_mode: int):
    if ea in (7, 107):
        return pysts.Sta(sta_mode)          # sta_mode 1 = demo tables
    if ea == 11:
        return pysts.Misty1()
    raise SmError(0x01, f"unsupported EA={ea}")


class VirtualHsm(SmBase):
    def __init__(self, keystore: Keystore, module_id: str = "VHSM0001",
                 firmware_id: str = "pysts-vhsm-1.0", sta_mode: int = 1,
                 api_type: str = "vending", dk_cache_size: int = 8192):
        self.ks = keystore
        self.module_id = module_id
        self.firmware_id = firmware_id
        self.sta_mode = sta_mode
        self.api_type = api_type
        self.dk_cache = LruCache(dk_cache_size)
        self.metrics = {"tokensIssued": 0, "verifies": 0, "errors": 0}

    # ----- provisioning (software analogue of SM?KL load-vending-key) ----
    def load_vending_key(self, sgc, krn, vk: bytes, ea, dkga, bdt=93, ti=1,
                         kt=2, ken=0) -> KeyRegister:
        kcv = pysts.vk_kcv(dkga, vk).hex().upper()
        meta = dict(sgc=sgc, krn=krn, ea=ea, dkga=dkga, bdt=bdt, ti=ti,
                    kt=kt, ken=ken, kcv=kcv)
        reg = self.ks.add_register(meta, vk)
        self.dk_cache.clear()
        return self._reg(self.ks.get(reg))

    def enable_vending(self, count: int):
        self.ks.set_tx_counter(count)

    def load_transaction_license(self, license_text: str) -> bool:
        """Minimal license: any integer found in the text sets the tx counter."""
        import re
        m = re.search(r"\d+", license_text or "")
        if not m:
            raise SmError(0x01, "no transaction count in license")
        self.ks.set_tx_counter(int(m.group()))
        return True

    # ----- SmBase: status -----------------------------------------------
    def status(self) -> SmStatus:
        info = {"backend": "virtual", "sta_mode": str(self.sta_mode)}
        info.update({f"metric.{k}": str(v) for k, v in self.metrics.items()})
        info.update({f"dkCache.{k}": str(v) for k, v in self.dk_cache.stats().items()})
        return SmStatus(api_type=self.api_type, module_id=self.module_id,
                        firmware_id=self.firmware_id, tx_counter=self.ks.tx_counter,
                        num_registers=len(self.ks.registers()), info=info)

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
            raise SmError(0x22, str(e))

    # ----- helpers ------------------------------------------------------
    def _rec(self, sgc, krn):
        try:
            return self.ks.find(sgc, krn)
        except KeyError as e:
            raise SmError(0x22, str(e))

    def _dk(self, rec: dict, pan18: str, ti: int, ea: int) -> bytes:
        key = (rec["reg_no"], pan18, ti, ea)
        return self.dk_cache.get_or_compute(key, lambda: pysts.derive_dk(
            rec["dkga"], self.ks.vk_bytes(rec), rec["sgc"], pan18, rec["kt"], ti,
            rec["krn"], ea, rec["bdt"]))

    def _issue(self, cls, sgc, krn, pan18, ti, ea, subclass, tid, transfer_amount):
        rec = self._rec(sgc, krn)
        self.ks.consume_transaction()
        dk = self._dk(rec, pan18, ti, ea)
        cipher = _cipher_for(ea, self.sta_mode)
        amt = transfer_amount if pysts.is_currency(cls, subclass) else int(round(transfer_amount))
        content = codec.build_credit_mse_content(cls, subclass,
                                                 int.from_bytes(os.urandom(1), "big") & 0x0F,
                                                 tid, amt, encode_amount=True)
        token20 = codec.encrypt_token_int(cipher, dk, cls, subclass, content)
        parsed = codec.parse_credit_mse_content(cls, subclass, content)
        self.metrics["tokensIssued"] += 1
        return IssuedToken(token_dec=token20, token_hex=("%017X" % int(token20)),
                           token_class=cls, subclass=subclass, tid=tid,
                           transfer_amount=parsed["amount"], vk_kcv=rec["kcv"])

    # ----- SmBase: token issuance ---------------------------------------
    def issue_credit_token(self, sgc, krn, pan18, ti, ea, tct, subclass, tid,
                           transfer_amount) -> IssuedToken:
        return self._issue(0, sgc, krn, pan18, ti, ea, subclass, tid, transfer_amount)

    def issue_mse_token(self, sgc, krn, pan18, ti, ea, tct, subclass, tid,
                        transfer_amount) -> IssuedToken:
        return self._issue(2, sgc, krn, pan18, ti, ea, subclass, tid, transfer_amount)

    def issue_key_change_tokens(self, sgc, krn, pan18, ti, ea, tct, to_sgc,
                                to_krn, to_ti, to_ken, allow_3kct=False) -> list:
        src = self._rec(sgc, krn)
        dst = self._rec(to_sgc, to_krn)
        self.ks.consume_transaction()
        toks = pysts.vk_create_key_change_tokens(
            self.ks.vk_bytes(src), sgc, krn, src["kt"], src["dkga"], src["bdt"], pan18, ti, ea,
            new_vk=self.ks.vk_bytes(dst), new_dkga=dst["dkga"], new_bdt=dst["bdt"],
            new_sgc=to_sgc, new_krn=to_krn, new_ti=to_ti, new_ken=to_ken,
            new_kt=dst["kt"], three_kct=1 if allow_3kct else 0, sta_mode=self.sta_mode)
        self.metrics["tokensIssued"] += len(toks)
        out = []
        for i, t in enumerate(toks):
            out.append(IssuedToken(token_dec=t, token_hex=("%017X" % int(t)),
                                   token_class=2, subclass=(3 if i == 0 else 4 + i - 1),
                                   tid=0, transfer_amount=0.0, vk_kcv=dst["kcv"],
                                   new_config=({"toSgc": to_sgc, "toKrn": to_krn,
                                                "toTi": to_ti, "toKen": to_ken,
                                                "toVkKcv": dst["kcv"]} if i == 0 else None)))
        return out

    # ----- SmBase: verify -----------------------------------------------
    def verify_token(self, sgc, krn, pan18, ti, ea, token_dec) -> dict:
        rec = self._rec(sgc, krn)
        dk = self._dk(rec, pan18, ti, ea)
        cipher = _cipher_for(ea, self.sta_mode)
        self.metrics["verifies"] += 1
        try:
            base = codec.decrypt_token_int(cipher, dk, token_dec)
        except ValueError:
            return {"validationResult": "EVerify.Crc"}
        info = codec.parse_credit_mse_content(base["class"], base["subclass"], base["content"])
        info.update({"class": base["class"], "subclass": base["subclass"],
                     "validationResult": "EVerify.Ok", "vkKcv": rec["kcv"]})
        return info
