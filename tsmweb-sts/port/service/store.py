"""Persistence (stdlib sqlite3). Postgres is a drop-in via the same SQL DAL.

Holds: local users + API keys, per-meter TID cancellation lists, and the
token-issue result cache for fetchTokenResult idempotency.
"""

from __future__ import annotations
import json
import os
import sqlite3
import threading
import time
import hashlib
import hmac

from Crypto.Protocol.KDF import scrypt

RESULT_CACHE_LIMIT = 1000


def _pwhash(password: str, salt: bytes) -> bytes:
    return scrypt(password.encode(), salt, 32, N=2 ** 14, r=8, p=1)


class Store:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        self._local = threading.local()
        self._init()

    @property
    def _db(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def _init(self):
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            realm TEXT, username TEXT, salt BLOB, pwhash BLOB, perms TEXT,
            PRIMARY KEY(realm, username));
        CREATE TABLE IF NOT EXISTS api_keys(
            key_id TEXT PRIMARY KEY, keyhash BLOB, realm TEXT, username TEXT, perms TEXT);
        CREATE TABLE IF NOT EXISTS tid_lists(pan TEXT PRIMARY KEY, tids TEXT);
        CREATE TABLE IF NOT EXISTS results(
            realm TEXT, username TEXT, message_id TEXT, payload TEXT, ts REAL,
            PRIMARY KEY(realm, username, message_id));
        """)
        self._db.commit()

    # ---- users / api keys ---------------------------------------------
    def add_user(self, realm: str, username: str, password: str, perms: list):
        salt = os.urandom(16)
        self._db.execute(
            "INSERT OR REPLACE INTO users VALUES(?,?,?,?,?)",
            (realm, username, salt, _pwhash(password, salt), json.dumps(perms)))
        self._db.commit()

    def check_password(self, realm: str, username: str, password: str):
        row = self._db.execute(
            "SELECT salt,pwhash,perms FROM users WHERE realm=? AND username=?",
            (realm, username)).fetchone()
        if row is None:
            return None
        if not hmac.compare_digest(bytes(row["pwhash"]), _pwhash(password, bytes(row["salt"]))):
            return None
        return json.loads(row["perms"])

    def add_api_key(self, key_id: str, secret: str, realm: str, username: str, perms: list):
        kh = hashlib.sha256(secret.encode()).digest()
        self._db.execute("INSERT OR REPLACE INTO api_keys VALUES(?,?,?,?,?)",
                         (key_id, kh, realm, username, json.dumps(perms)))
        self._db.commit()

    def check_api_key(self, key_id: str, secret: str):
        row = self._db.execute(
            "SELECT keyhash,realm,username,perms FROM api_keys WHERE key_id=?",
            (key_id,)).fetchone()
        if row is None:
            return None
        if not hmac.compare_digest(bytes(row["keyhash"]), hashlib.sha256(secret.encode()).digest()):
            return None
        return {"realm": row["realm"], "username": row["username"],
                "perms": json.loads(row["perms"])}

    # ---- TID cancellation lists ---------------------------------------
    def get_tid_list(self, pan: str) -> list:
        row = self._db.execute("SELECT tids FROM tid_lists WHERE pan=?", (pan,)).fetchone()
        return json.loads(row["tids"]) if row else []

    def set_tid_list(self, pan: str, tids: list):
        self._db.execute("INSERT OR REPLACE INTO tid_lists VALUES(?,?)",
                         (pan, json.dumps(tids)))
        self._db.commit()

    def reset_tid_lists(self, pan_like: str) -> list:
        like = pan_like.replace("*", "%").replace("?", "_")
        rows = self._db.execute("SELECT pan FROM tid_lists WHERE pan LIKE ?", (like,)).fetchall()
        self._db.execute("DELETE FROM tid_lists WHERE pan LIKE ?", (like,))
        self._db.commit()
        return [r["pan"] for r in rows]

    # ---- result cache (fetchTokenResult idempotency) ------------------
    def store_result(self, realm: str, username: str, message_id: str, payload):
        self._db.execute("INSERT OR REPLACE INTO results VALUES(?,?,?,?,?)",
                         (realm, username, message_id, json.dumps(payload), time.time()))
        self._db.execute(
            "DELETE FROM results WHERE rowid NOT IN "
            "(SELECT rowid FROM results ORDER BY ts DESC LIMIT ?)", (RESULT_CACHE_LIMIT,))
        self._db.commit()

    def fetch_result(self, realm: str, username: str, message_id: str):
        row = self._db.execute(
            "SELECT payload FROM results WHERE realm=? AND username=? AND message_id=?",
            (realm, username, message_id)).fetchone()
        return json.loads(row["payload"]) if row else None
