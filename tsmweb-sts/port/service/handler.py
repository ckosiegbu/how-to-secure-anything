"""TokenApiHandler -- transport-agnostic implementation of the PrismToken
TokenApi service (ports libshlsm/modules/prismtoken1/TokenApi-1.0.tm).

Returns plain dicts/lists with the IDL field names; thrift_server adapts these
to thriftpy2 structs. The handler depends only on SmBase + Store + Authenticator.
"""

from __future__ import annotations
import time

import pysts
from .tid import make_token_id
from .auth import AuthError
from . import meter as _meter

API_VERSION = "1.1"


class ApiException(Exception):
    def __init__(self, ecode: str, msg: str):
        super().__init__(f"{ecode}: {msg}")
        self.eCode = ecode
        self.eMsgEn = msg


def _from_auth_error(e: AuthError) -> ApiException:
    return ApiException(e.ecode, e.msg)


class TokenApiHandler:
    def __init__(self, sm, store, auth):
        self.sm = sm
        self.store = store
        self.auth = auth

    # ---- helpers -------------------------------------------------------
    def _authz(self, access_token, permission):
        try:
            return self.auth.authorize(access_token, permission)
        except AuthError as e:
            raise _from_auth_error(e)

    @staticmethod
    def _pan_of(meter_config: dict) -> str:
        drn = meter_config["drn"]
        return _meter.normalize_pan(drn)

    def _token_struct(self, mc: dict, sgc: int, krn: int, issued, new_config=None) -> dict:
        cls, sub = issued.token_class, issued.subclass
        td = pysts.tariff.TOKEN_TYPES.get((cls, sub), {})
        scaled = pysts.scale_units(cls, sub, issued.transfer_amount)
        pan = self._pan_of(mc)
        return {
            "drn": _meter.pan_to_drn(pan), "pan": pan, "ea": mc["ea"], "tct": mc.get("tct", 0),
            "sgc": sgc, "krn": krn, "ti": mc["ti"],
            "tokenClass": cls, "subclass": sub, "tid": issued.tid,
            "transferAmount": float(issued.transfer_amount),
            "isReservedTid": pysts.is_reserved_tid(issued.tid),
            "newConfig": new_config,
            "description": td.get("desc", f"class {cls} subclass {sub}"),
            "stsUnitName": td.get("unit", "units"),
            "scaledAmount": scaled["print"], "scaledUnitName": scaled["scaledUnitName"],
            "tokenDec": issued.token_dec, "tokenHex": issued.token_hex,
            "idSm": self.sm.status().module_id, "vkKcv": issued.vk_kcv,
        }

    def _auto_kct(self, mc: dict, sgc, krn, pan, vkmeta) -> tuple:
        """Returns (kct_token_structs, eff_sgc, eff_krn, eff_ti). Handles explicit
        newConfig; allowKrn/KenUpdate are accepted but require a KRN registry
        (not modelled here) so only newConfig triggers issuance."""
        nc = mc.get("newConfig")
        if not nc:
            return [], sgc, krn, mc["ti"]
        to_sgc, to_krn, to_ti = nc["toSgc"], nc["toKrn"], nc["toTi"]
        to_ken = mc.get("ken", vkmeta.ken)
        kct = self.sm.issue_key_change_tokens(sgc, krn, pan, mc["ti"], mc["ea"],
                                              mc.get("tct", 0), to_sgc, to_krn, to_ti, to_ken,
                                              allow_3kct=mc.get("allow3Kct", False))
        structs = []
        for i, t in enumerate(kct):
            advice = None
            if t.new_config:
                advice = {"toSgc": to_sgc, "toKrn": to_krn, "toTi": to_ti, "toKen": to_ken,
                          "idRecord": _meter.make_id_record(pan, to_sgc, to_krn, to_ti, mc["ea"], mc.get("tct", 2)),
                          "record2": _meter.make_record2(pan, to_sgc, to_krn, to_ti, mc["ea"], mc.get("tct", 2)),
                          "rollover": False, "toVkKcv": t.vk_kcv}
            structs.append(self._token_struct(mc, to_sgc, to_krn, t, new_config=advice))
        return structs, to_sgc, to_krn, to_ti

    # ---- service methods ----------------------------------------------
    def ping(self, sleepMs: int, echo: str) -> str:
        time.sleep(max(0, min(int(sleepMs), 60000)) / 1000.0)
        return echo

    def signInWithPassword(self, messageId, realm, username, password, sessionOpts) -> dict:
        ver = (sessionOpts or {}).get("version", API_VERSION)
        if ver.split(".")[0] != API_VERSION.split(".")[0]:
            raise ApiException("ESignin.Version",
                               f"This service (API version={API_VERSION}) does not support client API version='{ver}'")
        try:
            token = self.auth.sign_in_password(realm, username, password)
        except AuthError as e:
            raise _from_auth_error(e)
        return {"accessToken": token}

    def getStatus(self, messageId, accessToken) -> list:
        self._authz(accessToken, "GetStatus")
        st = self.sm.status()
        info = {"apiType": st.api_type, "moduleId": st.module_id,
                "firmwareId": st.firmware_id, "txCounter": str(st.tx_counter),
                "numRegisters": str(st.num_registers)}
        info.update({k: str(v) for k, v in st.info.items()})
        return [{"info": info, "alerts": []}]

    def parseIdRecord(self, messageId, accessToken, idRecord) -> dict:
        self._authz(accessToken, "ParseIdRecord")
        try:
            r = _meter.parse_id_record(idRecord)
        except ValueError as e:
            raise ApiException("ESts.IdRecord", str(e))
        return {"drn": r["drn"], "ea": r["ea"], "tct": r["tct"], "sgc": r["sgc"],
                "krn": r["krn"], "ti": r["ti"], "ken": 0, "doe": r["doe"],
                "allowKrnUpdate": True, "allowKenUpdate": True, "allow3Kct": False}

    def loadTransactionLicense(self, messageId, accessToken, licenseText) -> bool:
        self._authz(accessToken, "LoadTransactionLicense")
        if not hasattr(self.sm, "load_transaction_license"):
            raise ApiException("ESm", "backend does not support license loading")
        return bool(self.sm.load_transaction_license(licenseText))

    def _issue(self, kind, messageId, accessToken, meterConfig, subclass, transferAmount,
               tokenTime, flags) -> list:
        perm = "IssueCreditToken" if kind == "credit" else "IssueMseToken"
        sess = self._authz(accessToken, perm)
        pan = self._pan_of(meterConfig)
        sgc, krn = meterConfig["sgc"], meterConfig["krn"]
        try:
            vkmeta = self.sm.fetch_vk_meta(sgc, krn)
        except Exception as e:
            raise ApiException("EKeystore.NotFound", str(e))
        kct_structs, eff_sgc, eff_krn, eff_ti = self._auto_kct(meterConfig, sgc, krn, pan, vkmeta)
        if (eff_sgc, eff_krn) != (sgc, krn):
            vkmeta = self.sm.fetch_vk_meta(eff_sgc, eff_krn)
        tid = make_token_id(self.store, pan, int(tokenTime), vkmeta.bdt, int(flags))
        fn = self.sm.issue_credit_token if kind == "credit" else self.sm.issue_mse_token
        try:
            issued = fn(eff_sgc, eff_krn, pan, eff_ti, meterConfig["ea"],
                        meterConfig.get("tct", 0), subclass, tid, float(transferAmount))
        except pysts_sm_error() as e:
            raise ApiException("ESm", str(e))
        result = kct_structs + [self._token_struct(meterConfig, eff_sgc, eff_krn, issued)]
        self.store.store_result(sess["realm"], sess["username"], messageId, result)
        return result

    def issueCreditToken(self, messageId, accessToken, meterConfig, subclass,
                         transferAmount, tokenTime, flags) -> list:
        return self._issue("credit", messageId, accessToken, meterConfig, subclass,
                           transferAmount, tokenTime, flags)

    def issueMseToken(self, messageId, accessToken, meterConfig, subclass,
                      transferAmount, tokenTime, flags) -> list:
        return self._issue("mse", messageId, accessToken, meterConfig, subclass,
                           transferAmount, tokenTime, flags)

    def issueKeyChangeTokens(self, messageId, accessToken, meterConfig, newConfig) -> list:
        sess = self._authz(accessToken, "IssueKeyChangeTokens")
        pan = self._pan_of(meterConfig)
        sgc, krn = meterConfig["sgc"], meterConfig["krn"]
        try:
            vkmeta = self.sm.fetch_vk_meta(sgc, krn)
        except Exception as e:
            raise ApiException("EKeystore.NotFound", str(e))
        mc = dict(meterConfig, newConfig=newConfig)
        structs, *_ = self._auto_kct(mc, sgc, krn, pan, vkmeta)
        self.store.store_result(sess["realm"], sess["username"], messageId, structs)
        return structs

    def verifyToken(self, messageId, accessToken, meterConfig, tokenDec) -> dict:
        self._authz(accessToken, "VerifyToken")
        pan = self._pan_of(meterConfig)
        try:
            res = self.sm.verify_token(meterConfig["sgc"], meterConfig["krn"], pan,
                                       meterConfig["ti"], meterConfig["ea"], tokenDec)
        except Exception as e:
            raise ApiException("ESm", str(e))
        out = {"validationResult": res["validationResult"]}
        if res["validationResult"] == "EVerify.Ok":
            issued = _IssuedShim(tokenDec, res)
            out["token"] = self._token_struct(meterConfig, meterConfig["sgc"],
                                              meterConfig["krn"], issued)
        return out

    def issueDitkChangeTokens(self, messageId, accessToken, meterConfig) -> list:
        self._authz(accessToken, "IssueDitkChangeTokens")
        raise ApiException("EService.Disabled", "issueDitkChangeTokens requires Manufacturing firmware")

    def issueMeterTestToken(self, messageId, accessToken, subclass, control, mfrcode) -> dict:
        self._authz(accessToken, "IssueMeterTestToken")
        raise ApiException("EService.Disabled", "issueMeterTestToken (class-1) not yet ported")

    def fetchTokenResult(self, messageId, accessToken, reqMessageId) -> list:
        sess = self._authz(accessToken, None)
        res = self.store.fetch_result(sess["realm"], sess["username"], reqMessageId)
        if res is None:
            raise ApiException("ECacheMiss", "The requested entry was not found in the cache")
        return res

    def ctsResetTidList(self, messageId, accessToken, panPattern) -> list:
        self._authz(accessToken, "CtsResetTidList")
        return self.store.reset_tid_lists(panPattern)


class _IssuedShim:
    """Adapts an SM verify_token dict to the IssuedToken fields used by _token_struct."""
    def __init__(self, token_dec, res):
        self.token_dec = token_dec
        self.token_hex = ("%017x" % int(token_dec)).upper()
        self.token_class = res.get("class", 0)
        self.subclass = res.get("subclass", 0)
        self.tid = res.get("tid", 0)
        self.transfer_amount = res.get("amount", 0.0)
        self.vk_kcv = res.get("vkKcv", "")


def pysts_sm_error():
    from sts_sm import SmError
    return SmError
