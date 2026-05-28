"""Application wiring: build the SM backend, store, auth and handler; run server.

Production (Mac Mini), virtual HSM, 4 workers, TLS:
    PRISMTOKEN_BACKEND=virtual PRISMTOKEN_KEK=auto PRISMTOKEN_WORKERS=4 \
    PRISMTOKEN_KEYSTORE=/var/lib/prismtoken/keystore.json \
    PRISMTOKEN_DB=/var/lib/prismtoken/prismtoken.db \
    PRISMTOKEN_TLS_CERT=/etc/prismtoken/tls.crt PRISMTOKEN_TLS_KEY=/etc/prismtoken/tls.key \
    python3 -m service.app

Provision users / API keys / vending keys first with `python3 -m service.adminctl`.
"""

from __future__ import annotations

import sts_sm
from .store import Store
from .auth import Authenticator
from .handler import TokenApiHandler
from .config import Config


def build_sm(cfg: Config, kek_kwargs=None):
    if cfg.backend == "virtual":
        ks = sts_sm.Keystore(cfg.keystore_path, sts_sm.make_kek(cfg.kek, **(kek_kwargs or {})))
        ks.load_or_create()
        return sts_sm.VirtualHsm(ks, sta_mode=cfg.sta_mode, dk_cache_size=cfg.dk_cache_size)
    if cfg.backend == "serial":
        transport = sts_sm.SerialTransport(cfg.serial_port, baudrate=cfg.serial_baud)
        sm = sts_sm.DcmSerialSm(transport)
        _load_serial_registers(sm, cfg)
        return sm
    raise ValueError(f"unknown backend {cfg.backend!r}")


def _load_serial_registers(sm, cfg):
    """Hook: populate the (sgc,krn)->HSM-register map from the vending DB.
    The secret keys live in the module; only the register index is host-side."""
    # Implemented by the deployment's provisioning (adminctl serial-register).
    pass


def build_app(cfg: Config = None, seed_admin=None, kek_kwargs=None):
    cfg = cfg or Config()
    sm = build_sm(cfg, kek_kwargs)
    store = Store(cfg.db_path)
    if seed_admin:
        realm, user, pw = seed_admin
        store.add_user(realm, user, pw, ["*"])
    auth = Authenticator(store)
    handler = TokenApiHandler(sm, store, auth)
    return handler, sm, store, auth


def make_adapter_factory(cfg: Config):
    """Returns build_adapter(mod) used by pool.serve_forked (runs in each worker)."""
    kek_kwargs = cfg.kek_kwargs()

    def build_adapter(mod):
        from .thrift_server import ThriftAdapter
        handler, _, _, _ = build_app(cfg, seed_admin=None, kek_kwargs=kek_kwargs)
        return ThriftAdapter(handler, mod)

    return build_adapter


def main(argv=None):
    cfg = Config.from_env()
    from .pool import serve_forked
    tls = " +TLS" if cfg.tls_certfile else ""
    print(f"PrismToken serving on {cfg.host}:{cfg.port} "
          f"(backend={cfg.backend}, workers={cfg.workers}{tls})")
    serve_forked(make_adapter_factory(cfg), cfg.host, cfg.port, cfg.idl_path,
                 workers=cfg.workers, tls_certfile=cfg.tls_certfile,
                 tls_keyfile=cfg.tls_keyfile)


if __name__ == "__main__":
    main()
