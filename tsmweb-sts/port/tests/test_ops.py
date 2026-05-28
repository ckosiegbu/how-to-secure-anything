"""Phase 4 (scale & ops) tests: LRU cache, config, DK-cache wiring, provisioning
CLI, and the SO_REUSEPORT listener. Run: python3 tests/test_ops.py"""

import os
import socket
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pysts
import sts_sm
from sts_sm.cache import LruCache
from service.config import Config
from service import adminctl
from service.app import build_app
from service.pool import make_listener
from service.handler import ApiException
from service.tid import EXTERNAL_CLOCK
from service import meter

VK8 = bytes.fromhex("ABABABABABABABAB")
SGC = 123456


# ---- LRU cache -------------------------------------------------------------

def test_lru_cache_hit_miss_and_eviction():
    c = LruCache(capacity=2)
    calls = []
    def mk(v): return lambda: (calls.append(v) or v)
    assert c.get_or_compute("a", mk("A")) == "A"
    assert c.get_or_compute("a", mk("A")) == "A"      # hit, no recompute
    assert calls == ["A"]
    c.get_or_compute("b", mk("B"))
    c.get_or_compute("c", mk("C"))                    # evicts "a" (LRU)
    c.get_or_compute("a", mk("A"))                    # recompute
    assert calls == ["A", "B", "C", "A"]
    st = c.stats()
    assert st["size"] == 2 and st["hits"] == 1


# ---- config ----------------------------------------------------------------

def test_config_from_env():
    env = {"PRISMTOKEN_PORT": "9443", "PRISMTOKEN_WORKERS": "4",
           "PRISMTOKEN_BACKEND": "virtual", "PRISMTOKEN_KEK": "plaintext"}
    cfg = Config.from_env(env)
    assert cfg.port == 9443 and cfg.workers == 4 and cfg.kek == "plaintext"


def test_config_passphrase_kek_requires_env():
    cfg = Config(kek="passphrase")
    try:
        cfg.kek_kwargs({})
        assert False
    except ValueError:
        pass
    assert cfg.kek_kwargs({"PRISMTOKEN_KEK_PASSPHRASE": "x"})["passphrase"] == "x"


# ---- DK cache actually used by the virtual HSM -----------------------------

def test_dk_cache_used_on_repeat_vend():
    cfg = Config(keystore_path=os.path.join(tempfile.mkdtemp(), "ks.json"),
                 kek="plaintext", db_path=":memory:")
    handler, sm, store, auth = build_app(cfg, seed_admin=("local", "admin", "pw"))
    sm.enable_vending(100)
    sm.load_vending_key(SGC, 1, VK8, ea=7, dkga=2)
    pan = meter.make_meter_pan(7, 1)
    for i in range(5):
        sm._issue(0, SGC, 1, pan, 1, 7, 0, 1000 + i, 10)   # same meter -> DK cache hits
    st = sm.dk_cache.stats()
    assert st["hits"] >= 4 and st["misses"] == 1
    assert sm.metrics["tokensIssued"] == 5


# ---- provisioning CLI ------------------------------------------------------

def _cfg_tmp():
    d = tempfile.mkdtemp()
    return Config(keystore_path=os.path.join(d, "ks.json"),
                  kek="plaintext", db_path=os.path.join(d, "db.sqlite"))


def test_adminctl_provision_then_use():
    cfg = _cfg_tmp()
    store, ks = adminctl._open(cfg)
    adminctl.add_user(store, "local", "op", "s3cret", ["IssueCreditToken", "VerifyToken"])
    adminctl.load_vk(ks, SGC, 1, VK8, ea=7, dkga=2)
    adminctl.set_license(ks, 1000)
    assert "reg 1:" in adminctl.status(store, ks)

    # Now the service, using the SAME db + keystore, should vend with that user.
    handler, sm, store2, auth = build_app(cfg, seed_admin=None)
    tok = handler.signInWithPassword("m", "local", "op", "s3cret", {"version": "1.1"})["accessToken"]
    pan = meter.make_meter_pan(7, 1)
    drn = meter.pan_to_drn(pan)
    mc = {"drn": drn, "ea": 7, "tct": 0, "sgc": SGC, "krn": 1, "ti": 1, "ken": 0}
    res = handler.issueCreditToken("r1", tok, mc, 0, 50.0,
                                   pysts.EPOCHS[93] + 1000 * 60, EXTERNAL_CLOCK)
    assert res[0]["tokenClass"] == 0
    vr = handler.verifyToken("v", tok, mc, res[0]["tokenDec"])
    assert vr["validationResult"] == "EVerify.Ok"


def test_adminctl_permission_enforced():
    cfg = _cfg_tmp()
    store, ks = adminctl._open(cfg)
    adminctl.add_user(store, "local", "viewer", "pw", ["VerifyToken"])  # no issue perm
    adminctl.load_vk(ks, SGC, 1, VK8, ea=7, dkga=2)
    adminctl.set_license(ks, 10)
    handler, sm, store2, auth = build_app(cfg, seed_admin=None)
    tok = handler.signInWithPassword("m", "local", "viewer", "pw", {"version": "1.1"})["accessToken"]
    mc = {"drn": meter.pan_to_drn(meter.make_meter_pan(7, 1)), "ea": 7, "tct": 0,
          "sgc": SGC, "krn": 1, "ti": 1, "ken": 0}
    try:
        handler.issueCreditToken("r", tok, mc, 0, 10.0, pysts.EPOCHS[93] + 60, EXTERNAL_CLOCK)
        assert False
    except ApiException as e:
        assert e.eCode == "EAuthentication.Permission"


# ---- listener --------------------------------------------------------------

def test_make_listener_binds_and_reuseport():
    s = make_listener("127.0.0.1", 0)
    try:
        assert s.getsockname()[0] == "127.0.0.1"
        if hasattr(socket, "SO_REUSEPORT"):
            assert s.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT) == 1
    finally:
        s.close()


if __name__ == "__main__":
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for f in funcs:
        f()
        print(f"  ok  {f.__name__}")
        passed += 1
    print(f"\n{passed}/{len(funcs)} ops tests passed")
