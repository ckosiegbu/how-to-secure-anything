"""Application wiring: build the SM backend, store, auth and handler; run server.

Usage (Mac Mini deployment):
    PRISMTOKEN_BACKEND=virtual PRISMTOKEN_KEK=auto \
    PRISMTOKEN_KEYSTORE=/var/lib/prismtoken/keystore.json \
    python3 -m service.app --host 0.0.0.0 --port 9090

The default (no env) builds an in-memory virtual HSM with a dev plaintext
keystore and a seeded admin -- for local testing only.
"""

from __future__ import annotations
import argparse
import os
import tempfile

import sts_sm
from .store import Store
from .auth import Authenticator
from .handler import TokenApiHandler


def build_sm(backend="virtual", keystore_path=None, kek="plaintext", **kek_kwargs):
    if backend == "virtual":
        path = keystore_path or os.path.join(tempfile.mkdtemp(), "keystore.json")
        ks = sts_sm.Keystore(path, sts_sm.make_kek(kek, **kek_kwargs))
        ks.load_or_create()
        sm = sts_sm.VirtualHsm(ks)
        return sm
    if backend == "serial":
        # Drive a real Prism module over a macOS serial device. The (sgc,krn)->
        # register map is loaded from config/DB after construction via sm.register().
        transport = sts_sm.SerialTransport(
            os.environ["PRISMTOKEN_SERIAL_PORT"],
            baudrate=int(os.environ.get("PRISMTOKEN_SERIAL_BAUD", "9600")))
        return sts_sm.DcmSerialSm(transport)
    raise ValueError(f"unknown backend {backend!r}")


def build_app(backend="virtual", keystore_path=None, kek="plaintext",
              db_path=":memory:", seed_admin=("local", "admin", "admin"),
              **kek_kwargs):
    sm = build_sm(backend, keystore_path, kek, **kek_kwargs)
    store = Store(db_path)
    if seed_admin:
        realm, user, pw = seed_admin
        store.add_user(realm, user, pw, ["*"])
    auth = Authenticator(store)
    handler = TokenApiHandler(sm, store, auth)
    return handler, sm, store, auth


def main(argv=None):
    p = argparse.ArgumentParser(description="PrismToken Thrift service")
    p.add_argument("--host", default=os.environ.get("PRISMTOKEN_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("PRISMTOKEN_PORT", "9090")))
    args = p.parse_args(argv)

    backend = os.environ.get("PRISMTOKEN_BACKEND", "virtual")
    handler, sm, store, auth = build_app(
        backend=backend,
        keystore_path=os.environ.get("PRISMTOKEN_KEYSTORE"),
        kek=os.environ.get("PRISMTOKEN_KEK", "plaintext"),
        db_path=os.environ.get("PRISMTOKEN_DB", ":memory:"))

    from .thrift_server import make_thrift_server
    print(f"PrismToken serving Thrift on {args.host}:{args.port} (backend={backend})")
    make_thrift_server(handler, args.host, args.port).serve()


if __name__ == "__main__":
    main()
