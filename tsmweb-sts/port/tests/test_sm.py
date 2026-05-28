"""Tests for the SM layer (keystore + virtual HSM). Run: python3 tests/test_sm.py"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pysts
import sts_sm

VK8 = bytes.fromhex("ABABABABABABABAB")
VK16 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
PAN = "600727000000000084"   # IIN 600727 (valid-ish placeholder PAN)
SGC = 123456


# ---- keystore + KEK providers ----------------------------------------------

def _ks(kek):
    path = os.path.join(tempfile.mkdtemp(), "ks.json")
    ks = sts_sm.Keystore(path, kek)
    ks.create()
    return ks, path


def test_plaintext_keystore_roundtrip():
    ks, path = _ks(sts_sm.PlaintextKek())
    reg = ks.add_register(dict(sgc=SGC, krn=1, ea=7, dkga=2, bdt=93, ti=1, kt=2, ken=0, kcv="ABCDEF"), VK8)
    ks2 = sts_sm.Keystore(path, sts_sm.PlaintextKek())
    ks2.load()
    assert ks2.vk_bytes(ks2.get(reg)) == VK8


def test_passphrase_keystore_roundtrip_and_wrong_pw():
    kek = sts_sm.PassphraseKek("correct horse battery staple", n=2 ** 12)
    ks, path = _ks(kek)
    ks.add_register(dict(sgc=SGC, krn=1, ea=11, dkga=4, bdt=93, ti=1, kt=2, ken=0, kcv="001122"), VK16)
    # correct passphrase reopens
    ok = sts_sm.Keystore(path, sts_sm.PassphraseKek("correct horse battery staple", n=2 ** 12))
    ok.load()
    assert ok.find(SGC, 1)["ea"] == 11
    # wrong passphrase fails GCM auth
    bad = sts_sm.Keystore(path, sts_sm.PassphraseKek("wrong", n=2 ** 12))
    try:
        bad.load()
        assert False, "expected auth failure"
    except (ValueError, KeyError):
        pass


def test_transaction_counter_gate():
    ks, _ = _ks(sts_sm.PlaintextKek())
    ks.set_tx_counter(1)
    ks.consume_transaction()
    try:
        ks.consume_transaction()
        assert False, "expected exhaustion"
    except PermissionError:
        pass


# ---- virtual HSM end-to-end ------------------------------------------------

def _vhsm(sta_mode=1):
    ks, _ = _ks(sts_sm.PlaintextKek())
    vhsm = sts_sm.VirtualHsm(ks, sta_mode=sta_mode)
    vhsm.enable_vending(1000)
    return vhsm


def test_vhsm_status_and_load_key():
    v = _vhsm()
    reg = v.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    assert reg.kcv and len(reg.kcv) == 6
    st = v.status()
    assert st.api_type == "vending" and st.num_registers == 1 and st.tx_counter == 1000
    assert v.fetch_vk_meta(SGC, 1).sgc == SGC


def test_vhsm_credit_issue_and_verify_ea7():
    v = _vhsm()
    v.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 1000 * 60)
    tok = v.issue_credit_token(SGC, 1, PAN, ti=1, ea=7, tct=0, subclass=0, tid=tid,
                               transfer_amount=50)
    assert len(tok.token_dec) == 20 and len(tok.token_hex) == 17
    assert abs(tok.transfer_amount - 50) <= 1   # rounding in customer favour
    res = v.verify_token(SGC, 1, PAN, ti=1, ea=7, token_dec=tok.token_dec)
    assert res["validationResult"] == "EVerify.Ok"
    assert res["tid"] == tid


def test_vhsm_credit_issue_and_verify_ea11_misty1():
    v = _vhsm()
    v.load_vending_key(SGC, 1, VK16, ea=11, dkga=4)
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 4242 * 60)
    tok = v.issue_credit_token(SGC, 1, PAN, ti=1, ea=11, tct=0, subclass=0, tid=tid,
                               transfer_amount=250)
    res = v.verify_token(SGC, 1, PAN, ti=1, ea=11, token_dec=tok.token_dec)
    assert res["validationResult"] == "EVerify.Ok" and res["tid"] == tid


def test_vhsm_currency_token():
    v = _vhsm()
    v.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 2000 * 60)
    tok = v.issue_credit_token(SGC, 1, PAN, ti=1, ea=7, tct=0, subclass=4, tid=tid,
                               transfer_amount=123.45)
    assert abs(tok.transfer_amount - 123.45) <= 0.01
    res = v.verify_token(SGC, 1, PAN, ti=1, ea=7, token_dec=tok.token_dec)
    assert res["validationResult"] == "EVerify.Ok"


def test_vhsm_mse_token():
    v = _vhsm()
    v.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 3000 * 60)
    tok = v.issue_mse_token(SGC, 1, PAN, ti=1, ea=7, tct=0, subclass=1, tid=tid,
                            transfer_amount=7)
    assert tok.token_class == 2
    res = v.verify_token(SGC, 1, PAN, ti=1, ea=7, token_dec=tok.token_dec)
    assert res["validationResult"] == "EVerify.Ok" and res["subclass"] == 1


def test_vhsm_key_change_tokens():
    v = _vhsm()
    v.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    v.load_vending_key(SGC, 2, bytes.fromhex("1122334455667788"), ea=7, dkga=2)
    toks = v.issue_key_change_tokens(SGC, 1, PAN, ti=1, ea=7, tct=0,
                                     to_sgc=SGC, to_krn=2, to_ti=1, to_ken=0)
    assert len(toks) == 2
    assert toks[0].new_config is not None and toks[1].new_config is None


def test_vhsm_verify_wrong_key_fails():
    v = _vhsm()
    v.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    v.load_vending_key(999999, 1, bytes.fromhex("CDCDCDCDCDCDCDCD"), ea=7, dkga=2)
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 100 * 60)
    tok = v.issue_credit_token(SGC, 1, PAN, ti=1, ea=7, tct=0, subclass=0, tid=tid,
                               transfer_amount=10)
    res = v.verify_token(999999, 1, PAN, ti=1, ea=7, token_dec=tok.token_dec)
    assert res["validationResult"] == "EVerify.Crc"


def test_vhsm_unknown_key_raises():
    v = _vhsm()
    try:
        v.issue_credit_token(SGC, 9, PAN, ti=1, ea=7, tct=0, subclass=0, tid=1,
                             transfer_amount=10)
        assert False, "expected SmError"
    except sts_sm.SmError as e:
        assert e.code == 0x22


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for f in funcs:
        f()
        print(f"  ok  {f.__name__}")
        passed += 1
    print(f"\n{passed}/{len(funcs)} SM tests passed")
