"""Encrypted keystore for the virtual HSM.

Vending-key material is the crown-jewel secret. It is stored AES-256-GCM
encrypted under a random data key (DEK); the DEK is wrapped by a pluggable
KEK provider. The DEK is only ever decrypted into RAM.

KEK providers
-------------
- MacSecureEnclaveKek : wraps the DEK with a non-exportable EC P-256 key held
  in the Mac's Secure Enclave (the right hardware-rooted choice for Mac Minis).
  Requires macOS + pyobjc-framework-Security; the private key never leaves the
  enclave. Marked NEEDS-ON-DEVICE-VALIDATION (cannot run on this Linux CI).
- PassphraseKek : derives the KEK from an operator passphrase via scrypt.
  Cross-platform, the tested default.
- PlaintextKek : no protection -- development/tests only.

File format (JSON): {"kek":<provider-meta>, "nonce":hex, "ct":hex}
where ct = AES-256-GCM(DEK, plaintext=json(registers)).
"""

from __future__ import annotations
import json
import os
import sys
import platform
from abc import ABC, abstractmethod

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt


class KekProvider(ABC):
    """Wraps/unwraps a 32-byte data-encryption key (DEK)."""
    name = "abstract"

    @abstractmethod
    def wrap(self, dek: bytes) -> dict: ...

    @abstractmethod
    def unwrap(self, meta: dict) -> bytes: ...


class PlaintextKek(KekProvider):
    name = "plaintext"

    def wrap(self, dek: bytes) -> dict:
        return {"provider": self.name, "dek": dek.hex()}

    def unwrap(self, meta: dict) -> bytes:
        return bytes.fromhex(meta["dek"])


class PassphraseKek(KekProvider):
    name = "passphrase"

    def __init__(self, passphrase: str, n=2 ** 15, r=8, p=1):
        self._pw = passphrase.encode()
        self._n, self._r, self._p = n, r, p

    def _derive(self, salt: bytes) -> bytes:
        return scrypt(self._pw, salt, 32, N=self._n, r=self._r, p=self._p)

    def wrap(self, dek: bytes) -> dict:
        salt = os.urandom(16)
        kek = self._derive(salt)
        nonce = os.urandom(12)
        ct, tag = AES.new(kek, AES.MODE_GCM, nonce=nonce).encrypt_and_digest(dek)
        return {"provider": self.name, "salt": salt.hex(), "nonce": nonce.hex(),
                "ct": ct.hex(), "tag": tag.hex(),
                "kdf": {"n": self._n, "r": self._r, "p": self._p}}

    def unwrap(self, meta: dict) -> bytes:
        kdf = meta.get("kdf", {})
        self._n = kdf.get("n", self._n); self._r = kdf.get("r", self._r); self._p = kdf.get("p", self._p)
        kek = self._derive(bytes.fromhex(meta["salt"]))
        c = AES.new(kek, AES.MODE_GCM, nonce=bytes.fromhex(meta["nonce"]))
        return c.decrypt_and_verify(bytes.fromhex(meta["ct"]), bytes.fromhex(meta["tag"]))


class MacSecureEnclaveKek(KekProvider):
    """Wrap the DEK with a Secure Enclave EC key via ECIES. macOS only.

    NEEDS-ON-DEVICE-VALIDATION: cannot be exercised on non-Mac CI. The SE
    private key (label `label`) is created on first use and reused thereafter;
    it is non-exportable and gated by `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`.
    """
    name = "mac-secure-enclave"
    ALGO = "eciesEncryptionCofactorVariableIVX963SHA256AESGCM"

    def __init__(self, label: str = "co.prism.pysts.vhsm.kek"):
        if platform.system() != "Darwin":
            raise RuntimeError("MacSecureEnclaveKek requires macOS")
        self.label = label
        from Security import (  # pyobjc-framework-Security
            SecKeyCreateRandomKey, SecKeyCopyPublicKey,
            SecKeyCreateEncryptedData, SecKeyCreateDecryptedData,
            SecItemCopyMatching, SecItemAdd,
        )  # noqa: F401  (import-time availability check)

    def _security(self):
        import Security
        return Security

    def _load_or_create_key(self):
        S = self._security()
        q = {
            S.kSecClass: S.kSecClassKey,
            S.kSecAttrApplicationTag: self.label.encode(),
            S.kSecAttrKeyType: S.kSecAttrKeyTypeECSECPrimeRandom,
            S.kSecReturnRef: True,
        }
        status, ref = S.SecItemCopyMatching(q, None)
        if status == 0 and ref is not None:
            return ref
        access = S.SecAccessControlCreateWithFlags(
            None, S.kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            S.kSecAccessControlPrivateKeyUsage, None)
        attrs = {
            S.kSecAttrKeyType: S.kSecAttrKeyTypeECSECPrimeRandom,
            S.kSecAttrKeySizeInBits: 256,
            S.kSecAttrTokenID: S.kSecAttrTokenIDSecureEnclave,
            S.kSecPrivateKeyAttrs: {
                S.kSecAttrIsPermanent: True,
                S.kSecAttrApplicationTag: self.label.encode(),
                S.kSecAttrAccessControl: access,
            },
        }
        priv, err = S.SecKeyCreateRandomKey(attrs, None)
        if priv is None:
            raise RuntimeError(f"SecKeyCreateRandomKey failed: {err}")
        return priv

    def wrap(self, dek: bytes) -> dict:
        S = self._security()
        priv = self._load_or_create_key()
        pub = S.SecKeyCopyPublicKey(priv)
        ct, err = S.SecKeyCreateEncryptedData(pub, self.ALGO, dek, None)
        if ct is None:
            raise RuntimeError(f"SE encrypt failed: {err}")
        return {"provider": self.name, "label": self.label, "ct": bytes(ct).hex()}

    def unwrap(self, meta: dict) -> bytes:
        S = self._security()
        priv = self._load_or_create_key()
        pt, err = S.SecKeyCreateDecryptedData(priv, self.ALGO,
                                              bytes.fromhex(meta["ct"]), None)
        if pt is None:
            raise RuntimeError(f"SE decrypt failed: {err}")
        return bytes(pt)


_PROVIDERS = {p.name: p for p in (PlaintextKek, PassphraseKek, MacSecureEnclaveKek)}


def make_kek(provider: str, **kwargs) -> KekProvider:
    if provider == "auto":
        provider = "mac-secure-enclave" if sys.platform == "darwin" else "passphrase"
    cls = _PROVIDERS.get(provider)
    if cls is None:
        raise ValueError(f"unknown KEK provider {provider!r}")
    return cls(**kwargs)


class Keystore:
    """Holds {reg_no: {meta..., 'vk': hex}} encrypted at rest with a DEK."""

    def __init__(self, path: str, kek: KekProvider):
        self.path = path
        self.kek = kek
        self._dek = None
        self._data = {"registers": {}, "next_reg": 1, "tx_counter": 0}

    # ---- lifecycle ------------------------------------------------------
    def create(self):
        self._dek = os.urandom(32)
        self._flush()

    def load(self):
        with open(self.path) as f:
            blob = json.load(f)
        self._dek = self.kek.unwrap(blob["kek"])
        c = AES.new(self._dek, AES.MODE_GCM, nonce=bytes.fromhex(blob["nonce"]))
        pt = c.decrypt_and_verify(bytes.fromhex(blob["ct"]), bytes.fromhex(blob["tag"]))
        self._data = json.loads(pt)

    def load_or_create(self):
        if os.path.exists(self.path):
            self.load()
        else:
            self.create()

    def _flush(self):
        nonce = os.urandom(12)
        pt = json.dumps(self._data).encode()
        ct, tag = AES.new(self._dek, AES.MODE_GCM, nonce=nonce).encrypt_and_digest(pt)
        blob = {"kek": self.kek.wrap(self._dek), "nonce": nonce.hex(),
                "ct": ct.hex(), "tag": tag.hex()}
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(blob, f)
        os.replace(tmp, self.path)

    # ---- register operations -------------------------------------------
    def add_register(self, meta: dict, vk: bytes) -> int:
        reg = self._data["next_reg"]
        self._data["next_reg"] = reg + 1
        rec = dict(meta)
        rec["reg_no"] = reg
        rec["vk"] = vk.hex()
        self._data["registers"][str(reg)] = rec
        self._flush()
        return reg

    def find(self, sgc: int, krn: int) -> dict:
        for rec in self._data["registers"].values():
            if rec["sgc"] == sgc and rec["krn"] == krn:
                return rec
        raise KeyError(f"no vending key for SGC={sgc} KRN={krn}")

    def get(self, reg_no: int) -> dict:
        return self._data["registers"][str(reg_no)]

    def delete(self, reg_no: int):
        self._data["registers"].pop(str(reg_no), None)
        self._flush()

    def registers(self) -> list:
        return list(self._data["registers"].values())

    def vk_bytes(self, rec: dict) -> bytes:
        return bytes.fromhex(rec["vk"])

    # ---- transaction counter -------------------------------------------
    @property
    def tx_counter(self) -> int:
        return self._data["tx_counter"]

    def set_tx_counter(self, n: int):
        self._data["tx_counter"] = n
        self._flush()

    def consume_transaction(self):
        if self._data["tx_counter"] <= 0:
            raise PermissionError("vending disabled: transaction counter exhausted")
        self._data["tx_counter"] -= 1
        self._flush()
