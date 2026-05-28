"""Provisioning CLI: users, API keys, vending keys, transaction license.

    python3 -m service.adminctl add-user   --realm local --user op --password ... --perm '*'
    python3 -m service.adminctl add-api-key --key-id k1 --secret ... --user op --perm IssueCreditToken
    python3 -m service.adminctl load-vk     --sgc 123456 --krn 1 --vk-hex AB.. --ea 7 --dkga 2
    python3 -m service.adminctl set-license --count 1000000
    python3 -m service.adminctl status

Operates directly on the Store (DB) and the encrypted Keystore -- the same
artefacts the running service uses. Run on the box that holds the keystore.
"""

from __future__ import annotations
import argparse

import sts_sm
from .store import Store
from .config import Config


def _open(cfg: Config):
    store = Store(cfg.db_path)
    ks = sts_sm.Keystore(cfg.keystore_path, sts_sm.make_kek(cfg.kek, **cfg.kek_kwargs()))
    ks.load_or_create()
    return store, ks


def add_user(store, realm, user, password, perms):
    store.add_user(realm, user, password, perms)
    return f"user {realm}/{user} added with perms {perms}"


def add_api_key(store, key_id, secret, realm, user, perms):
    store.add_api_key(key_id, secret, realm, user, perms)
    return f"api key {key_id} added for {realm}/{user}"


def load_vk(ks, sgc, krn, vk: bytes, ea, dkga, bdt=93, ti=1, kt=2, ken=0):
    vhsm = sts_sm.VirtualHsm(ks)
    reg = vhsm.load_vending_key(sgc, krn, vk, ea=ea, dkga=dkga, bdt=bdt, ti=ti, kt=kt, ken=ken)
    return f"loaded VK into register {reg.reg_no} (SGC={sgc} KRN={krn} KCV={reg.kcv})"


def set_license(ks, count):
    ks.set_tx_counter(int(count))
    return f"transaction counter set to {count}"


def status(store, ks):
    regs = ks.registers()
    lines = [f"txCounter={ks.tx_counter}", f"registers={len(regs)}"]
    for r in regs:
        lines.append(f"  reg {r['reg_no']}: SGC={r['sgc']} KRN={r['krn']} "
                     f"EA={r['ea']} DKGA={r['dkga']} KCV={r['kcv']}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(prog="adminctl", description="PrismToken provisioning")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add-user")
    s.add_argument("--realm", default="local"); s.add_argument("--user", required=True)
    s.add_argument("--password", required=True); s.add_argument("--perm", action="append", default=["*"])

    s = sub.add_parser("add-api-key")
    s.add_argument("--key-id", required=True); s.add_argument("--secret", required=True)
    s.add_argument("--realm", default="local"); s.add_argument("--user", required=True)
    s.add_argument("--perm", action="append", default=["*"])

    s = sub.add_parser("load-vk")
    s.add_argument("--sgc", type=int, required=True); s.add_argument("--krn", type=int, required=True)
    s.add_argument("--vk-hex", required=True); s.add_argument("--ea", type=int, required=True)
    s.add_argument("--dkga", type=int, required=True); s.add_argument("--bdt", type=int, default=93)
    s.add_argument("--ti", type=int, default=1); s.add_argument("--kt", type=int, default=2)
    s.add_argument("--ken", type=int, default=0)

    s = sub.add_parser("set-license"); s.add_argument("--count", type=int, required=True)
    sub.add_parser("status")

    args = p.parse_args(argv)
    cfg = Config.from_env()
    store, ks = _open(cfg)

    if args.cmd == "add-user":
        print(add_user(store, args.realm, args.user, args.password, args.perm))
    elif args.cmd == "add-api-key":
        print(add_api_key(store, args.key_id, args.secret, args.realm, args.user, args.perm))
    elif args.cmd == "load-vk":
        print(load_vk(ks, args.sgc, args.krn, bytes.fromhex(args.vk_hex), args.ea,
                      args.dkga, args.bdt, args.ti, args.kt, args.ken))
    elif args.cmd == "set-license":
        print(set_license(ks, args.count))
    elif args.cmd == "status":
        print(status(store, ks))


if __name__ == "__main__":
    main()
