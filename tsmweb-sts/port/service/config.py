"""Service configuration (env-driven, with a typed dataclass)."""

from __future__ import annotations
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 9090
    workers: int = 1                       # prefork worker processes (virtual backend)
    backend: str = "virtual"               # "virtual" | "serial"

    # virtual HSM
    keystore_path: str = "/var/lib/prismtoken/keystore.json"
    kek: str = "auto"                      # auto|mac-secure-enclave|passphrase|plaintext
    kek_passphrase_env: str = "PRISMTOKEN_KEK_PASSPHRASE"
    sta_mode: int = 1                      # 1 = demo STA tables (EA=7)
    dk_cache_size: int = 8192

    # serial HSM
    serial_port: str = ""
    serial_baud: int = 9600

    # persistence
    db_path: str = "/var/lib/prismtoken/prismtoken.db"

    # TLS (recommended; clients then send API key / bearer token)
    tls_certfile: str = ""
    tls_keyfile: str = ""

    idl_path: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(__file__), "prismtoken1-TokenApi.thrift"))

    @classmethod
    def from_env(cls, env=None) -> "Config":
        e = os.environ if env is None else env
        def g(name, default):
            return e.get(name, default)
        return cls(
            host=g("PRISMTOKEN_HOST", cls.host),
            port=int(g("PRISMTOKEN_PORT", cls.port)),
            workers=int(g("PRISMTOKEN_WORKERS", cls.workers)),
            backend=g("PRISMTOKEN_BACKEND", cls.backend),
            keystore_path=g("PRISMTOKEN_KEYSTORE", cls.keystore_path),
            kek=g("PRISMTOKEN_KEK", cls.kek),
            sta_mode=int(g("PRISMTOKEN_STA_MODE", cls.sta_mode)),
            dk_cache_size=int(g("PRISMTOKEN_DK_CACHE", cls.dk_cache_size)),
            serial_port=g("PRISMTOKEN_SERIAL_PORT", cls.serial_port),
            serial_baud=int(g("PRISMTOKEN_SERIAL_BAUD", cls.serial_baud)),
            db_path=g("PRISMTOKEN_DB", cls.db_path),
            tls_certfile=g("PRISMTOKEN_TLS_CERT", cls.tls_certfile),
            tls_keyfile=g("PRISMTOKEN_TLS_KEY", cls.tls_keyfile),
        )

    def kek_kwargs(self, env=None) -> dict:
        e = os.environ if env is None else env
        if self.kek == "passphrase":
            pw = e.get(self.kek_passphrase_env)
            if not pw:
                raise ValueError(f"{self.kek_passphrase_env} must be set for passphrase KEK")
            return {"passphrase": pw}
        return {}
