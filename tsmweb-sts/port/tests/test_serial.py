"""Tests for the serial (DCM/STS6) backend: PTVD, framing, and the DcmSerialSm
backend round-tripping against the SoftSm6Emulator over a loopback transport.
Run: python3 tests/test_serial.py"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pysts
import sts_sm
from sts_sm import ptvd, sts6_frame

VK8 = bytes.fromhex("ABABABABABABABAB")
VK16 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
PAN = pysts.is_currency  # placeholder import sanity
SGC = 123456


# ---- PTVD ------------------------------------------------------------------

def test_ptvd_roundtrip():
    pkt = ptvd.build_packet("N", 42, "P", "600727000000000084", "H", b"\x0f\xff\xff", "D", "20210412090000")
    r = ptvd.Reader(pkt)
    assert r.scan_n() == 42
    assert r.scan_p() == "600727000000000084"
    assert r.scan_h() == b"\x0f\xff\xff"
    assert r.scan_d() == "20210412090000"
    r.scan_end()


def test_ptvd_rejects_leading_zero_and_tilde():
    try:
        ptvd.Reader("N007~").scan_n(); assert False
    except ValueError:
        pass
    try:
        ptvd.fmt_p("a~b"); assert False
    except ValueError:
        pass


# ---- CRC-16/ARC + framing --------------------------------------------------

def test_crc16_arc_known_vector():
    assert sts6_frame.crc16_arc(b"123456789") == 0xBB3D


def test_frame_request_response_roundtrip():
    req = sts6_frame.build_request("SM", "VC", ptvd.build_packet("N", 1))
    api, cmd, params = sts6_frame.parse_request(req)
    assert (api, cmd) == ("SM", "VC") and params == "N1~"
    resp = sts6_frame.build_response("SM", "VC", 0, ptvd.build_packet("P", "x"))
    assert sts6_frame.parse_response("SM", "VC", resp) == "Px~"


def test_frame_detects_corruption_and_status():
    resp = sts6_frame.build_response("SM", "VC", 0, "Pabc~")
    bad = resp[:-1] + ("0" if resp[-1] != "0" else "1")
    try:
        sts6_frame.parse_response("SM", "VC", bad); assert False
    except sts6_frame.StsProtocolError:
        pass
    err = sts6_frame.build_response("SM", "VC", 22)
    try:
        sts6_frame.parse_response("SM", "VC", err); assert False
    except sts6_frame.StsApiError as e:
        assert e.status == 22


# ---- DcmSerialSm <-> SoftSm6Emulator over loopback -------------------------

def _serial_sm():
    emu = sts_sm.SoftSm6Emulator(sta_mode=1)
    emu.load(1, SGC, 1, VK8, ea=7, dkga=2)
    emu.load(2, SGC, 2, bytes.fromhex("1122334455667788"), ea=7, dkga=2)
    emu.load(3, 654321, 1, VK16, ea=11, dkga=4)
    sm = sts_sm.DcmSerialSm(sts_sm.LoopbackTransport(emu))
    sm.register(1, SGC, 1, ea=7, dkga=2, kcv=pysts.vk_kcv(2, VK8).hex().upper())
    sm.register(2, SGC, 2, ea=7, dkga=2,
                kcv=pysts.vk_kcv(2, bytes.fromhex("1122334455667788")).hex().upper())
    sm.register(3, 654321, 1, ea=11, dkga=4, kcv=pysts.vk_kcv(4, VK16).hex().upper())
    return sm, emu


def test_serial_status():
    sm, _ = _serial_sm()
    st = sm.status()
    assert st.module_id == "00000001" and st.firmware_id == "EMUL0001"
    assert st.tx_counter > 0 and st.api_type == "vending"


def test_serial_credit_issue_and_verify_ea7():
    sm, _ = _serial_sm()
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 1000 * 60)
    tok = sm.issue_credit_token(SGC, 1, "600727000000000084", ti=1, ea=7, tct=0,
                                subclass=0, tid=tid, transfer_amount=50)
    assert len(tok.token_dec) == 20 and len(tok.token_hex) == 17
    vr = sm.verify_token(SGC, 1, "600727000000000084", ti=1, ea=7, token_dec=tok.token_dec)
    assert vr["validationResult"] == "EVerify.Ok" and vr["tid"] == tid


def test_serial_matches_virtual_hsm_bit_for_bit():
    """A token issued via the serial path must verify under an independent
    VirtualHsm holding the same key -- proves the wire encoding is correct."""
    sm, _ = _serial_sm()
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 1234 * 60)
    tok = sm.issue_credit_token(SGC, 1, "600727000000000084", 1, 7, 0, 0, tid, 40)
    ks = sts_sm.Keystore(":memory:" if False else
                         os.path.join(__import__("tempfile").mkdtemp(), "k.json"),
                         sts_sm.PlaintextKek())
    ks.create()
    v = sts_sm.VirtualHsm(ks, sta_mode=1)
    v.enable_vending(10)
    v.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    res = v.verify_token(SGC, 1, "600727000000000084", 1, 7, tok.token_dec)
    assert res["validationResult"] == "EVerify.Ok" and res["tid"] == tid


def test_serial_currency_and_mse():
    sm, _ = _serial_sm()
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 2000 * 60)
    cur = sm.issue_credit_token(SGC, 1, "600727000000000084", 1, 7, 0, 4, tid, 123.45)
    assert abs(cur.transfer_amount - 123.45) <= 0.01
    mse = sm.issue_mse_token(SGC, 1, "600727000000000084", 1, 7, 0, 1, tid, 7)
    assert mse.token_class == 2


def test_serial_ea11_misty1():
    sm, _ = _serial_sm()
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 4242 * 60)
    tok = sm.issue_credit_token(654321, 1, "600727000000000084", 1, 11, 0, 0, tid, 250)
    vr = sm.verify_token(654321, 1, "600727000000000084", 1, 11, tok.token_dec)
    assert vr["validationResult"] == "EVerify.Ok" and vr["tid"] == tid


def test_serial_key_change_tokens():
    sm, _ = _serial_sm()
    toks = sm.issue_key_change_tokens(SGC, 1, "600727000000000084", ti=1, ea=7, tct=0,
                                      to_sgc=SGC, to_krn=2, to_ti=1, to_ken=0)
    assert len(toks) == 2
    assert all(len(t.token_dec) == 20 for t in toks)
    assert toks[0].new_config is not None


def test_serial_unknown_register_raises():
    sm, _ = _serial_sm()
    try:
        sm.issue_credit_token(SGC, 9, "600727000000000084", 1, 7, 0, 0, 1, 10)
        assert False
    except sts_sm.SmError as e:
        assert e.code == 0x22


def test_serial_verify_wrong_key():
    sm, _ = _serial_sm()
    tid = pysts.token_id_from_time(pysts.EPOCHS[93] + 100 * 60)
    tok = sm.issue_credit_token(SGC, 1, "600727000000000084", 1, 7, 0, 0, tid, 10)
    vr = sm.verify_token(SGC, 2, "600727000000000084", 1, 7, tok.token_dec)
    assert vr["validationResult"] == "EVerify.Crc"


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for f in funcs:
        f()
        print(f"  ok  {f.__name__}")
        passed += 1
    print(f"\n{passed}/{len(funcs)} serial tests passed")
