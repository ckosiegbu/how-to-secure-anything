"""Smoke-test client: ping -> signin -> issueCreditToken -> verifyToken -> fetch.

Two modes, one flow:
  --inproc            drive the handler directly (no socket); self-provisions a
                      demo key + user. Runnable anywhere; used by the test-suite.
  --host/--port ...   connect to a running server with thriftpy2 (TLS + API key
                      or password). This is the first end-to-end hardware test.

Examples:
  python3 -m service.smoke --inproc --ea 11
  python3 -m service.smoke --host meter-vend.local --port 9090 \
      --tls-ca /etc/prismtoken/ca.crt --api-key 'vend1:s3cret' \
      --drn 60072700000000000 --ea 11 --sgc 123456 --krn 1 --ti 1 --amount 50
"""

from __future__ import annotations
import argparse
import os
import tempfile
import time

from .tid import EXTERNAL_CLOCK
from . import meter

DEMO_VK8 = bytes.fromhex("ABABABABABABABAB")
DEMO_VK16 = bytes.fromhex("000102030405060708090a0b0c0d0e0f")


def _d(obj, field):
    """Read a field from a dict or a thriftpy2 struct."""
    return obj[field] if isinstance(obj, dict) else getattr(obj, field)


class InProcClient:
    """Drives a TokenApiHandler directly. Returns plain dicts."""

    def __init__(self, handler, realm="local", user="smoke", password="smoke"):
        self.h = handler
        self.realm, self.user, self.password = realm, user, password

    def ping(self, echo="ping"):
        return self.h.ping(0, echo)

    def signin(self):
        return self.h.signInWithPassword("smoke", self.realm, self.user,
                                         self.password, {"version": "1.1"})["accessToken"]

    def issue_credit(self, token, mc, subclass, amount, token_time, flags):
        return self.h.issueCreditToken("smoke-issue", token, mc, subclass,
                                       amount, token_time, flags)

    def verify(self, token, mc, token_dec):
        return self.h.verifyToken("smoke-verify", token, mc, token_dec)

    def fetch(self, token, req_mid):
        return self.h.fetchTokenResult("smoke-fetch", token, req_mid)

    def status(self, token):
        return self.h.getStatus("smoke-status", token)


class ThriftClient:
    """Connects to a running PrismToken server via thriftpy2 (TLS optional)."""

    def __init__(self, host, port, idl_path=None, tls_ca=None, api_key=None,
                 realm="local", user=None, password=None, timeout=10.0):
        import thriftpy2
        from thriftpy2.transport import TSocket, TBufferedTransportFactory
        from thriftpy2.protocol import TBinaryProtocolFactory
        from thriftpy2.thrift import TClient
        idl_path = idl_path or os.path.join(os.path.dirname(__file__),
                                            "prismtoken1-TokenApi.thrift")
        self.mod = thriftpy2.load(idl_path, module_name="prismtoken_thrift")
        if tls_ca:
            from thriftpy2.transport.sslsocket import TSSLSocket
            sock = TSSLSocket(host, port, socket_timeout=timeout * 1000,
                              cafile=tls_ca, validate=True)
        else:
            sock = TSocket(host, port, socket_timeout=timeout * 1000)
        trans = TBufferedTransportFactory().get_transport(sock)
        proto = TBinaryProtocolFactory().get_protocol(trans)
        trans.open()
        self._trans = trans
        self.client = TClient(self.mod.TokenApi, proto)
        self.api_key, self.realm, self.user, self.password = api_key, realm, user, password

    def ping(self, echo="ping"):
        return self.client.ping(0, echo)

    def signin(self):
        if self.api_key:
            return self.api_key                         # API key acts as the accessToken
        opts = self.mod.SessionOptions(version="1.1", culture="en")
        return self.client.signInWithPassword("smoke", self.realm, self.user,
                                              self.password, opts).accessToken

    def _mc(self, mc):
        return self.mod.MeterConfigIn(
            drn=mc["drn"], ea=mc["ea"], tct=mc.get("tct", 0), sgc=mc["sgc"],
            krn=mc["krn"], ti=mc["ti"], ken=mc.get("ken", 0))

    def issue_credit(self, token, mc, subclass, amount, token_time, flags):
        return self.client.issueCreditToken("smoke-issue", token, self._mc(mc),
                                            subclass, amount, token_time, flags)

    def verify(self, token, mc, token_dec):
        return self.client.verifyToken("smoke-verify", token, self._mc(mc), token_dec)

    def fetch(self, token, req_mid):
        return self.client.fetchTokenResult("smoke-fetch", token, req_mid)

    def status(self, token):
        return self.client.getStatus("smoke-status", token)

    def close(self):
        self._trans.close()


def run_smoke(client, mc, amount=50.0, subclass=0, token_time=None,
              flags=EXTERNAL_CLOCK, log=print) -> dict:
    """signin -> issueCreditToken -> verifyToken -> fetchTokenResult. Raises on failure."""
    token_time = int(time.time()) if token_time is None else token_time
    log(f"[1] ping            -> {client.ping('hello')!r}")
    access = client.signin()
    log(f"[2] signin          -> accessToken {access[:12]}...")
    st = client.status(access)
    log(f"[3] getStatus       -> {_d(st[0], 'info').get('moduleId', '?')}")
    issued = client.issue_credit(access, mc, subclass, amount, token_time, flags)
    credit = issued[-1]
    token_dec = _d(credit, "tokenDec")
    log(f"[4] issueCreditToken-> {len(issued)} token(s); credit tokenDec={token_dec} "
        f"(tid={_d(credit, 'tid')}, units={_d(credit, 'transferAmount')})")
    vr = client.verify(access, mc, token_dec)
    result = _d(vr, "validationResult")
    log(f"[5] verifyToken     -> {result}")
    if result != "EVerify.Ok":
        raise SystemExit(f"SMOKE FAIL: verification returned {result}")
    fetched = client.fetch(access, "smoke-issue")
    if _d(fetched[-1], "tokenDec") != token_dec:
        raise SystemExit("SMOKE FAIL: fetchTokenResult did not return the issued token")
    log("[6] fetchTokenResult-> idempotent result matches")
    log("SMOKE PASS")
    return {"accessToken": access, "tokenDec": token_dec, "validationResult": result,
            "numTokens": len(issued)}


def _build_inproc(ea):
    """Self-contained in-process server with a demo key + user provisioned."""
    from .config import Config
    from .app import build_app
    cfg = Config(keystore_path=os.path.join(tempfile.mkdtemp(), "ks.json"),
                 kek="plaintext", db_path=":memory:")
    handler, sm, store, auth = build_app(cfg, seed_admin=None)
    store.add_user("local", "smoke", "smoke", ["*"])
    sm.enable_vending(1000)
    if ea == 11:
        sm.load_vending_key(123456, 1, DEMO_VK16, ea=11, dkga=4, bdt=14)
    else:
        sm.load_vending_key(123456, 1, DEMO_VK8, ea=7, dkga=2, bdt=14)
    return InProcClient(handler)


def main(argv=None):
    p = argparse.ArgumentParser(prog="prismtoken-smoke", description="PrismToken smoke test")
    p.add_argument("--inproc", action="store_true", help="drive the handler directly (no server)")
    p.add_argument("--host"); p.add_argument("--port", type=int, default=9090)
    p.add_argument("--tls-ca", help="CA cert to validate the server's TLS cert")
    p.add_argument("--api-key", help="accessToken as 'key_id:secret'")
    p.add_argument("--realm", default="local"); p.add_argument("--user"); p.add_argument("--password")
    p.add_argument("--drn", default=meter.pan_to_drn(meter.make_meter_pan(7, 1)))
    p.add_argument("--ea", type=int, default=7)
    p.add_argument("--sgc", type=int, default=123456); p.add_argument("--krn", type=int, default=1)
    p.add_argument("--ti", type=int, default=1); p.add_argument("--amount", type=float, default=50.0)
    p.add_argument("--subclass", type=int, default=0)
    args = p.parse_args(argv)

    if args.inproc:
        client = _build_inproc(args.ea)
    elif args.host:
        client = ThriftClient(args.host, args.port, tls_ca=args.tls_ca, api_key=args.api_key,
                              realm=args.realm, user=args.user, password=args.password)
    else:
        p.error("specify --inproc or --host")

    mc = {"drn": args.drn, "ea": args.ea, "tct": 0, "sgc": args.sgc,
          "krn": args.krn, "ti": args.ti, "ken": 0}
    run_smoke(client, mc, amount=args.amount, subclass=args.subclass)


if __name__ == "__main__":
    main()
