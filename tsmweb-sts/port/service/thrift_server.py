"""Thrift transport binding for TokenApiHandler.

Loads the recovered IDL at runtime with thriftpy2 (no codegen step) and adapts
between thriftpy2 structs and the plain dicts the handler uses. thriftpy2 is an
optional dependency: importing this module without it raises a clear error, but
service.handler (and the test-suite) work without it.
"""

from __future__ import annotations
import os

from .handler import TokenApiHandler, ApiException

IDL_PATH = os.environ.get("PRISMTOKEN_IDL", os.path.join(
    os.path.dirname(__file__), "prismtoken1-TokenApi.thrift"))

_TOKEN_FIELDS = ("drn", "pan", "ea", "tct", "sgc", "krn", "ti", "tokenClass",
                 "subclass", "tid", "transferAmount", "isReservedTid", "description",
                 "stsUnitName", "scaledAmount", "scaledUnitName", "tokenDec",
                 "tokenHex", "idSm", "vkKcv")
_MC_IN_FIELDS = ("drn", "ea", "tct", "sgc", "krn", "ti", "ken", "doe",
                 "allowKrnUpdate", "allowKenUpdate", "allow3Kct")


def load_idl(path: str = IDL_PATH):
    import thriftpy2
    return thriftpy2.load(path, module_name="prismtoken1_thrift")


def _mc_in_to_dict(mc) -> dict:
    d = {k: getattr(mc, k, None) for k in _MC_IN_FIELDS}
    nc = getattr(mc, "newConfig", None)
    if nc is not None:
        d["newConfig"] = {"toSgc": nc.toSgc, "toKrn": nc.toKrn, "toTi": nc.toTi}
    return {k: v for k, v in d.items() if v is not None}


def _advice(mod, nc):
    return mod.MeterConfigAdvice(
        toSgc=nc["toSgc"], toKrn=nc["toKrn"], toTi=nc["toTi"], toKen=nc["toKen"],
        idRecord=nc["idRecord"], record2=nc["record2"],
        rollover=nc["rollover"], toVkKcv=nc["toVkKcv"]) if nc else None


def _token(mod, d):
    return mod.Token(newConfig=_advice(mod, d.get("newConfig")),
                     **{k: d[k] for k in _TOKEN_FIELDS})


class ThriftAdapter:
    """Wraps TokenApiHandler with thriftpy2 struct (de)serialisation."""

    def __init__(self, handler: TokenApiHandler, mod):
        self.h = handler
        self.mod = mod

    def _guard(self, fn):
        try:
            return fn()
        except ApiException as e:
            raise self.mod.ApiException(eCode=e.eCode, eMsgEn=e.eMsgEn)

    def ping(self, sleepMs, echo):
        return self._guard(lambda: self.h.ping(sleepMs, echo))

    def signInWithPassword(self, messageId, realm, username, password, sessionOpts):
        opts = {"version": sessionOpts.version, "culture": sessionOpts.culture}
        r = self._guard(lambda: self.h.signInWithPassword(messageId, realm, username, password, opts))
        return self.mod.SignInResult(accessToken=r["accessToken"])

    def getStatus(self, messageId, accessToken):
        r = self._guard(lambda: self.h.getStatus(messageId, accessToken))
        return [self.mod.NodeStatus(info=n["info"], alerts=[]) for n in r]

    def parseIdRecord(self, messageId, accessToken, idRecord):
        r = self._guard(lambda: self.h.parseIdRecord(messageId, accessToken, idRecord))
        return self.mod.MeterConfigIn(**r)

    def loadTransactionLicense(self, messageId, accessToken, licenseText):
        return self._guard(lambda: self.h.loadTransactionLicense(messageId, accessToken, licenseText))

    def _issue_thrift(self, method, messageId, accessToken, meterConfig, subclass,
                      transferAmount, tokenTime, flags):
        mc = _mc_in_to_dict(meterConfig)
        r = self._guard(lambda: method(messageId, accessToken, mc, subclass,
                                       transferAmount, tokenTime, flags))
        return [_token(self.mod, t) for t in r]

    def issueCreditToken(self, messageId, accessToken, meterConfig, subclass,
                         transferAmount, tokenTime, flags):
        return self._issue_thrift(self.h.issueCreditToken, messageId, accessToken,
                                  meterConfig, subclass, transferAmount, tokenTime, flags)

    def issueMseToken(self, messageId, accessToken, meterConfig, subclass,
                      transferAmount, tokenTime, flags):
        return self._issue_thrift(self.h.issueMseToken, messageId, accessToken,
                                  meterConfig, subclass, transferAmount, tokenTime, flags)

    def issueKeyChangeTokens(self, messageId, accessToken, meterConfig, newConfig):
        mc = _mc_in_to_dict(meterConfig)
        nc = {"toSgc": newConfig.toSgc, "toKrn": newConfig.toKrn, "toTi": newConfig.toTi}
        r = self._guard(lambda: self.h.issueKeyChangeTokens(messageId, accessToken, mc, nc))
        return [_token(self.mod, t) for t in r]

    def verifyToken(self, messageId, accessToken, meterConfig, tokenDec):
        mc = _mc_in_to_dict(meterConfig)
        r = self._guard(lambda: self.h.verifyToken(messageId, accessToken, mc, tokenDec))
        tok = _token(self.mod, r["token"]) if "token" in r else None
        return self.mod.VerifyResult(validationResult=r["validationResult"], token=tok)

    def issueDitkChangeTokens(self, messageId, accessToken, meterConfig):
        return self._guard(lambda: self.h.issueDitkChangeTokens(messageId, accessToken,
                                                                _mc_in_to_dict(meterConfig)))

    def issueMeterTestToken(self, messageId, accessToken, subclass, control, mfrcode):
        return self._guard(lambda: self.h.issueMeterTestToken(messageId, accessToken,
                                                              subclass, control, mfrcode))

    def fetchTokenResult(self, messageId, accessToken, reqMessageId):
        r = self._guard(lambda: self.h.fetchTokenResult(messageId, accessToken, reqMessageId))
        return [_token(self.mod, t) for t in r]

    def ctsResetTidList(self, messageId, accessToken, panPattern):
        return self._guard(lambda: self.h.ctsResetTidList(messageId, accessToken, panPattern))


def make_thrift_server(handler: TokenApiHandler, host="0.0.0.0", port=9090,
                       idl_path: str = IDL_PATH):
    """Build a multithreaded Thrift server. Wrap the socket in TLS at deploy time."""
    from thriftpy2.rpc import make_server
    mod = load_idl(idl_path)
    adapter = ThriftAdapter(handler, mod)
    return make_server(mod.TokenApi, adapter, host, port)
