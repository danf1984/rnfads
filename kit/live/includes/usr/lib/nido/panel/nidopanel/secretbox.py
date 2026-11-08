"""Cifratura dei segreti salvati (password delle cartelle di rete, token).

Usa Fernet (AES-128-CBC + HMAC-SHA256, libreria cryptography). La chiave viene
generata sul NAS al primo uso e sta in /etc/nido/secret.key (solo root): non è
mai nel codice né nella ISO.
"""
import os
import threading

from .util import ETC, ApiError

KEY_FILE = os.path.join(ETC, "secret.key")
_lock = threading.Lock()
_f = None


def _fernet():
    global _f
    from cryptography.fernet import Fernet
    with _lock:
        if _f is None:
            try:
                with open(KEY_FILE, "rb") as fh:
                    key = fh.read().strip()
            except FileNotFoundError:
                key = Fernet.generate_key()
                os.makedirs(ETC, exist_ok=True)
                fd = os.open(KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(key + b"\n")
            _f = Fernet(key)
    return _f


def encrypt(text):
    return _fernet().encrypt((text or "").encode()).decode()


def decrypt(token):
    from cryptography.fernet import InvalidToken
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise ApiError("Impossibile leggere una password salvata: la chiave del NAS è cambiata", 500)
