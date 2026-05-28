"""Authentication / authorisation.

signInWithPassword issues an opaque bearer accessToken bound to a subject and a
permission set; pre-provisioned API keys ("key_id:secret") act as accessTokens
directly. Every API call validates the accessToken and the required permission.
"""

from __future__ import annotations
import secrets
import time
import threading

DEFAULT_TTL = 12 * 3600
ALL = "*"


class AuthError(Exception):
    def __init__(self, ecode: str, msg: str):
        super().__init__(msg)
        self.ecode = ecode
        self.msg = msg


class Authenticator:
    def __init__(self, store, ttl: int = DEFAULT_TTL):
        self.store = store
        self.ttl = ttl
        self._sessions = {}          # accessToken -> dict(realm, username, perms, exp)
        self._lock = threading.Lock()

    def sign_in_password(self, realm: str, username: str, password: str) -> str:
        perms = self.store.check_password(realm, username, password)
        if perms is None:
            raise AuthError("ESignin.Authentication",
                            f"Sign-in failed: authentication failed for realm='{realm}' username='{username}'")
        token = "st_" + secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {"realm": realm, "username": username,
                                     "perms": perms, "exp": time.time() + self.ttl}
        return token

    def _resolve(self, access_token: str):
        with self._lock:
            sess = self._sessions.get(access_token)
            if sess is not None:
                if sess["exp"] < time.time():
                    self._sessions.pop(access_token, None)
                    return None
                return sess
        if ":" in access_token:                       # API key form "key_id:secret"
            key_id, _, secret = access_token.partition(":")
            ident = self.store.check_api_key(key_id, secret)
            if ident:
                return {"realm": ident["realm"], "username": ident["username"],
                        "perms": ident["perms"], "exp": float("inf")}
        return None

    def authorize(self, access_token: str, permission: str | None = None) -> dict:
        sess = self._resolve(access_token)
        if sess is None:
            raise AuthError("EAuthentication.Token",
                            f"Authentication failed (bad accessToken: {access_token[:8]}...)")
        if permission and ALL not in sess["perms"] and permission not in sess["perms"]:
            raise AuthError("EAuthentication.Permission",
                            f"Access denied: accessToken does not have permission '{permission}'")
        return sess
