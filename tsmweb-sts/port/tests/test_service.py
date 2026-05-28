"""Tests for the Thrift service handler (driven directly, no socket).
Run: python3 tests/test_service.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pysts
import sts_sm
from service import meter
from service.tid import (make_token_id, bdt_adjust_tid, EXTERNAL_CLOCK,
                         TID_ADJUST_BDT, SPECIAL_RESERVED)
from service.app import build_app
from service.handler import ApiException

VK8 = bytes.fromhex("ABABABABABABABAB")
VK16 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
SGC = 123456


# ---- meter identity --------------------------------------------------------

def test_luhn_and_pan_roundtrip():
    pan = meter.make_meter_pan(7, 12345678)            # mfr 7 -> IIN 600727
    assert len(pan) == 18 and meter.luhn_ok(pan)
    drn = meter.pan_to_drn(pan)
    assert len(drn) == 11 and meter.drn_to_pan(drn) == pan


def test_pan_13_digit_drn():
    pan = meter.make_meter_pan(500, 12345678)          # mfr>=100 -> IIN 0000
    assert pan.startswith("0000") and meter.luhn_ok(pan)
    assert len(meter.pan_to_drn(pan)) == 13


def test_id_record_roundtrip():
    pan = meter.make_meter_pan(7, 1)
    rec = meter.make_id_record(pan, SGC, krn=1, ti=2, ea=11, tct=2)
    assert len(rec) == 35
    p = meter.parse_id_record(rec)
    assert p["sgc"] == SGC and p["krn"] == 1 and p["ti"] == 2 and p["ea"] == 11
    assert p["pan"] == pan


def test_record2_parse():
    pan = meter.make_meter_pan(7, 2)
    r2 = meter.make_record2(pan, SGC, krn=3, ti=1, ea=7, tct=2)
    p = meter.parse_id_record(r2)
    assert p["sgc"] == SGC and p["krn"] == 3 and p["ea"] == 7


# ---- TID computation -------------------------------------------------------

def test_tid_external_clock_monotonic_and_skip_reserved():
    s = sts_sm.Keystore  # noqa (unused) - use a real store
    from service.store import Store
    st = Store(":memory:")
    pan = meter.make_meter_pan(7, 3)
    base = pysts.EPOCHS[93] + 10 * 24 * 3600
    t1 = make_token_id(st, pan, base, 93, EXTERNAL_CLOCK)
    t2 = make_token_id(st, pan, base, 93, EXTERNAL_CLOCK)   # same clock -> must advance
    assert t2 > t1
    assert (t1 % 1440) != 1 and (t2 % 1440) != 1            # never the reserved minute


def test_tid_adjust_bdt():
    pan = meter.make_meter_pan(7, 4)
    # tokenTime is minutes-from-1993; bdt=93 means identity
    assert make_token_id(None, pan, 1000, 93, TID_ADJUST_BDT) == 1000


def test_tid_special_reserved():
    pan = meter.make_meter_pan(7, 5)
    tid = make_token_id(None, pan, pysts.EPOCHS[93] + 5 * 24 * 3600 + 3600, 93,
                        SPECIAL_RESERVED | EXTERNAL_CLOCK)
    assert tid % 1440 == 1                                   # 00:01 of that day


# ---- handler end-to-end ----------------------------------------------------

def _app():
    handler, sm, store, auth = build_app(seed_admin=("local", "admin", "secret"))
    sm.enable_vending(10000)
    sm.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    return handler, sm, store


def _signin(h):
    return h.signInWithPassword("m0", "local", "admin", "secret", {"version": "1.1"})["accessToken"]


def _mc(pan, ea=7, **kw):
    drn = meter.pan_to_drn(pan)
    d = {"drn": drn, "ea": ea, "tct": 0, "sgc": SGC, "krn": 1, "ti": 1, "ken": 0}
    d.update(kw)
    return d


def test_signin_and_bad_password():
    h, _, _ = _app()
    assert _signin(h).startswith("st_")
    try:
        h.signInWithPassword("m", "local", "admin", "wrong", {"version": "1.1"})
        assert False
    except ApiException as e:
        assert e.eCode == "ESignin.Authentication"


def test_auth_required():
    h, _, _ = _app()
    try:
        h.getStatus("m", "bogus-token")
        assert False
    except ApiException as e:
        assert e.eCode == "EAuthentication.Token"


def test_issue_credit_and_verify():
    h, sm, _ = _app()
    tok = _signin(h)
    pan = meter.make_meter_pan(7, 100)
    sm.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    res = h.issueCreditToken("req1", tok, _mc(pan), subclass=0, transferAmount=50.0,
                             tokenTime=pysts.EPOCHS[93] + 1000 * 60, flags=EXTERNAL_CLOCK)
    assert len(res) == 1
    t = res[0]
    assert len(t["tokenDec"]) == 20 and t["tokenClass"] == 0
    vr = h.verifyToken("v1", tok, _mc(pan), t["tokenDec"])
    assert vr["validationResult"] == "EVerify.Ok"
    assert vr["token"]["tid"] == t["tid"]


def test_fetch_token_result_idempotency():
    h, _, _ = _app()
    tok = _signin(h)
    pan = meter.make_meter_pan(7, 101)
    res = h.issueCreditToken("reqX", tok, _mc(pan), 0, 25.0,
                             pysts.EPOCHS[93] + 2000 * 60, EXTERNAL_CLOCK)
    again = h.fetchTokenResult("m", tok, "reqX")
    assert again[0]["tokenDec"] == res[0]["tokenDec"]


def test_fetch_unknown_result_raises():
    h, _, _ = _app()
    tok = _signin(h)
    try:
        h.fetchTokenResult("m", tok, "never")
        assert False
    except ApiException as e:
        assert e.eCode == "ECacheMiss"


def test_issue_credit_with_auto_kct():
    h, sm, _ = _app()
    tok = _signin(h)
    pan = meter.make_meter_pan(7, 102)
    sm.load_vending_key(SGC, 2, bytes.fromhex("1122334455667788"), ea=7, dkga=2)
    res = h.issueCreditToken("req2", tok, _mc(pan, newConfig={"toSgc": SGC, "toKrn": 2, "toTi": 1}),
                             subclass=0, transferAmount=30.0,
                             tokenTime=pysts.EPOCHS[93] + 1500 * 60, flags=EXTERNAL_CLOCK)
    # 2 KCT tokens (EA=7) + 1 credit token issued under the new KRN
    assert len(res) == 3
    assert res[0]["newConfig"] is not None and res[0]["newConfig"]["toKrn"] == 2
    assert res[-1]["krn"] == 2 and res[-1]["tokenClass"] == 0


def test_get_status_and_parse_id_record():
    h, _, _ = _app()
    tok = _signin(h)
    st = h.getStatus("m", tok)
    assert st[0]["info"]["apiType"] == "vending"
    pan = meter.make_meter_pan(7, 103)
    rec = meter.make_id_record(pan, SGC, 1, 1, 7, 2)
    mc = h.parseIdRecord("m", tok, rec)
    assert mc["sgc"] == SGC and mc["krn"] == 1


def test_ea11_issue_verify_via_handler():
    h, sm, _ = _app()
    tok = _signin(h)
    pan = meter.make_meter_pan(11, 104)
    sm.load_vending_key(654321, 1, VK16, ea=11, dkga=4)
    mc = {"drn": meter.pan_to_drn(pan), "ea": 11, "tct": 0, "sgc": 654321, "krn": 1, "ti": 1, "ken": 0}
    res = h.issueCreditToken("req11", tok, mc, 0, 250.0,
                             pysts.EPOCHS[93] + 4242 * 60, EXTERNAL_CLOCK)
    vr = h.verifyToken("v", tok, mc, res[0]["tokenDec"])
    assert vr["validationResult"] == "EVerify.Ok"


def test_mse_token_and_disabled_methods():
    h, sm, _ = _app()
    tok = _signin(h)
    pan = meter.make_meter_pan(7, 105)
    res = h.issueMseToken("reqm", tok, _mc(pan), subclass=1, transferAmount=7.0,
                          tokenTime=pysts.EPOCHS[93] + 3000 * 60, flags=EXTERNAL_CLOCK)
    assert res[0]["tokenClass"] == 2
    for fn in (lambda: h.issueMeterTestToken("m", tok, 0, 0, 0),
               lambda: h.issueDitkChangeTokens("m", tok, _mc(pan))):
        try:
            fn(); assert False
        except ApiException as e:
            assert e.eCode == "EService.Disabled"


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for f in funcs:
        f()
        print(f"  ok  {f.__name__}")
        passed += 1
    print(f"\n{passed}/{len(funcs)} service tests passed")
