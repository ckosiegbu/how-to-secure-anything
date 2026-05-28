"""Unit tests for pysts. Run: python3 -m pytest -q   (or python3 tests/test_pysts.py)"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pysts


# ---- MISTY1 (production-faithful) against the RFC 2994 test vector ----------

def test_misty1_rfc2994_vector():
    key = bytes.fromhex("00112233445566778899aabbccddeeff")
    pt = bytes.fromhex("0123456789abcdef")
    ct = bytes.fromhex("8b1da5f56ab3d07c")
    m = pysts.Misty1()
    assert m.encrypt(key, pt) == ct
    assert m.decrypt(key, ct) == pt


def test_misty1_roundtrip_random():
    m = pysts.Misty1()
    for _ in range(50):
        k, d = os.urandom(16), os.urandom(8)
        assert m.decrypt(k, m.encrypt(k, d)) == d


# ---- STA cipher (demo) is an invertible 64-bit block cipher ----------------

def test_sta_demo_roundtrip():
    c = pysts.Sta(1)
    for _ in range(50):
        k, d = os.urandom(8), os.urandom(8)
        assert c.decrypt(k, c.encrypt(k, d)) == d


def test_sta_production_withheld():
    try:
        pysts.Sta(0)
        assert False, "expected NDA guard"
    except ValueError:
        pass


# ---- transfer-amount codecs -------------------------------------------------

def test_transfer_amount_bands_round_up():
    for a in (0, 1, 16383, 16384, 180223, 180224, 1818623, 1818624, 18201624):
        ta = pysts.encode_transfer_amount(a)
        assert pysts.decode_transfer_amount(ta) >= a
        assert 0 <= ta <= 0xFFFF


def test_currency_amount_roundtrip():
    for v in (0.0, 1.0, 12.5, 50.0, 999.99, 12345.6789):
        ta = pysts.encode_currency_transfer_amount(v)
        assert 0 <= ta <= 0xFFFFF
        back = pysts.decode_currency_transfer_amount(ta)
        assert abs(back - v) <= max(0.01, abs(v) * 0.001)


# ---- DKGA key derivation ----------------------------------------------------

VK8 = bytes.fromhex("ABABABABABABABAB")
VK16 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
PAN = "000000000000000000"


def test_dkga02_deterministic_and_kcv():
    dk = pysts.dkga02(VK8, 123456, PAN, kt=2, ti=1, krn=1)
    assert len(dk) == 8
    assert pysts.dkga02(VK8, 123456, PAN, 2, 1, 1) == dk     # deterministic
    assert pysts.dkga02(VK8, 123457, PAN, 2, 1, 1) != dk     # sgc-sensitive
    assert len(pysts.vk_kcv(2, VK8)) == 3


def test_dkga04_length():
    dk7 = pysts.dkga04(VK16, 123456, PAN, ea=7)
    dk11 = pysts.dkga04(VK16, 123456, PAN, ea=11)
    assert len(dk7) == 8 and len(dk11) == 16


# ---- full token round-trips -------------------------------------------------

def test_credit_token_ea7_demo_roundtrip():
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 1000 * 60)
    res = pysts.vk_create_token(VK8, 123456, PAN, krn=1, kt=2, dkga_no=2, bdt=93,
                                ti=1, ea=7, cls=0, subclass=0, rnd=3, tid=tid,
                                amount=50, encode_amount=True, sta_mode=1)
    assert len(res["token20d"]) == 20
    info = pysts.vk_verify_token(VK8, 123456, PAN, 1, 2, 2, 93, 1, 7,
                                 res["token20d"], sta_mode=1)
    assert info["class"] == 0 and info["subclass"] == 0
    assert info["tid"] == tid and info["rnd"] == 3
    assert pysts.decode_transfer_amount(info["transferamount"]) == 50


def test_credit_token_ea11_misty1_roundtrip():
    # EA=11 uses MISTY1 (real) + DKGA04 (16-byte key) -- production-faithful path
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 5000 * 60)
    res = pysts.vk_create_token(VK16, 123456, PAN, krn=1, kt=2, dkga_no=4, bdt=93,
                                ti=1, ea=11, cls=0, subclass=0, rnd=9, tid=tid,
                                amount=250, encode_amount=True)
    info = pysts.vk_verify_token(VK16, 123456, PAN, 1, 2, 4, 93, 1, 11, res["token20d"])
    assert info["tid"] == tid and info["rnd"] == 9
    assert pysts.decode_transfer_amount(info["transferamount"]) == 250


def test_currency_token_roundtrip():
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 2000 * 60)
    res = pysts.vk_create_token(VK8, 123456, PAN, 1, 2, 2, 93, 1, 7,
                                cls=0, subclass=4, rnd=0, tid=tid,
                                amount=123.45, encode_amount=True, sta_mode=1)
    info = pysts.vk_verify_token(VK8, 123456, PAN, 1, 2, 2, 93, 1, 7,
                                 res["token20d"], sta_mode=1)
    assert info["class"] == 0 and info["subclass"] == 4
    assert abs(info["amount"] - 123.45) <= 0.01


def test_management_token_roundtrip():
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 3000 * 60)
    res = pysts.vk_create_token(VK8, 123456, PAN, 1, 2, 2, 93, 1, 7,
                                cls=2, subclass=1, rnd=0, tid=tid, amount=7,
                                encode_amount=False, sta_mode=1)
    info = pysts.vk_verify_token(VK8, 123456, PAN, 1, 2, 2, 93, 1, 7,
                                 res["token20d"], sta_mode=1)
    assert info["class"] == 2 and info["subclass"] == 1
    assert info["transferamount"] == 7


def test_wrong_key_fails_crc():
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 100 * 60)
    res = pysts.vk_create_token(VK8, 123456, PAN, 1, 2, 2, 93, 1, 7,
                                cls=0, subclass=0, rnd=0, tid=tid, amount=10,
                                encode_amount=True, sta_mode=1)
    try:
        pysts.vk_verify_token(bytes.fromhex("CDCDCDCDCDCDCDCD"), 123456, PAN,
                              1, 2, 2, 93, 1, 7, res["token20d"], sta_mode=1)
        assert False, "expected CRC failure with wrong key"
    except ValueError:
        pass


# ---- key change tokens ------------------------------------------------------

def test_kct_ea7_two_tokens():
    toks = pysts.vk_create_key_change_tokens(
        VK8, 123456, 1, 2, 2, 93, PAN, 1, 7,
        new_vk=bytes.fromhex("1122334455667788"), new_dkga=2, new_bdt=93,
        new_sgc=123457, new_krn=2, new_ti=1, new_ken=0, new_kt=2, sta_mode=1)
    assert len(toks) == 2
    assert all(len(t) == 20 for t in toks)


def test_kct_ea11_four_tokens():
    toks = pysts.vk_create_key_change_tokens(
        VK16, 123456, 1, 2, 4, 93, PAN, 1, 11,
        new_vk=os.urandom(16), new_dkga=4, new_bdt=93,
        new_sgc=123457, new_krn=2, new_ti=1, new_ken=0, new_kt=2)
    assert len(toks) == 4


# ---- tariff -----------------------------------------------------------------

def test_convert_units_with_tariff():
    # ZAR 50 at 0.115 ZAR/100Wh -> ~434.78 units (100Wh), encoded
    r = pysts.convert_units(50.0, tariff=0.115, cls=0, subclass=0)
    assert r["valueReq"] == 50.0
    assert r["transferAmt"] > 0
    assert r["unitsReq"] >= 434


def test_scale_units_electricity():
    s = pysts.scale_units(0, 0, 500)   # 500 hWh -> 50.0 kWh
    assert s["scaledUnitName"] == "kWh"
    assert abs(s["scaledUnits"] - 50.0) < 1e-9


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for f in funcs:
        f()
        print(f"  ok  {f.__name__}")
        passed += 1
    print(f"\n{passed}/{len(funcs)} tests passed")
