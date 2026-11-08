"""Accesso all'interfaccia: account propri, password con scrypt, sessioni con cookie.

- Gli account dell'interfaccia stanno in /etc/nido/ui-users.json (solo root, 0600).
  Al primo avvio non c'è nessun account: l'interfaccia chiede di crearne uno.
- La sessione è un token casuale nel cookie (HttpOnly, SameSite=Strict, Secure se HTTPS).
  Sul disco si salva solo l'impronta SHA-256 del token, mai il token.
- Dopo troppi tentativi sbagliati dallo stesso indirizzo l'accesso si blocca per un po'.
"""
import hashlib
import hmac
import os
import secrets
import threading
import time

from .util import ApiError, ETC, STATE, USER_RE, load_json, save_json

USERS_FILE = os.path.join(ETC, "ui-users.json")
SESSIONS_FILE = os.path.join(STATE, "ui-sessions.json")
COOKIE = "nido_s"
SHORT_TTL = 12 * 3600          # senza "Ricordami"
LONG_TTL = 30 * 24 * 3600      # con "Ricordami"
IDLE_TTL = 7 * 24 * 3600       # sessioni lunghe: scadono anche se non usate per una settimana

_lock = threading.Lock()
_sessions = None               # {sha256(token): {user, exp, created, seen, ip, ua, long}}
_fails = {}                    # {ip: [conteggio, bloccato_fino_a]}


# --- password -------------------------------------------------------------------------------

def _hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 15, r=8, p=1, maxmem=64 * 1024 * 1024, dklen=32)
    return "scrypt$15$8$1$" + salt.hex() + "$" + dk.hex()


def _check(password, stored):
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2 ** int(n), r=int(r),
                              p=int(p), maxmem=64 * 1024 * 1024, dklen=len(dk) // 2)
        return hmac.compare_digest(calc.hex(), dk)
    except (ValueError, TypeError):
        return False


def _users():
    return load_json(USERS_FILE, {}).get("users", {})


def _save_users(users):
    save_json(USERS_FILE, {"users": users}, 0o600)


def setup_needed():
    return not _users()


def _check_password_rules(password):
    if not isinstance(password, str) or len(password) < 8:
        raise ApiError("La password deve avere almeno 8 caratteri")
    if len(password) > 256:
        raise ApiError("Password troppo lunga")


def create_user(name, password, admin=True):
    name = (name or "").strip().lower()
    if not USER_RE.match(name):
        raise ApiError("Nome utente non valido: lettere minuscole, numeri, _ e - (max 32)")
    _check_password_rules(password)
    with _lock:
        users = _users()
        if name in users:
            raise ApiError("Questo utente esiste già")
        users[name] = {"hash": _hash(password), "admin": bool(admin), "created": int(time.time())}
        _save_users(users)
    return {"user": name}


def set_password(name, password):
    _check_password_rules(password)
    with _lock:
        users = _users()
        if name not in users:
            raise ApiError("Utente non trovato", 404)
        users[name]["hash"] = _hash(password)
        _save_users(users)
        # Una password nuova chiude le altre sessioni di quell'utente
        _load()
        for k in [k for k, s in _sessions.items() if s["user"] == name]:
            _sessions.pop(k)
        _persist()


# --- sessioni ---------------------------------------------------------------------------------

def _load():
    global _sessions
    if _sessions is None:
        _sessions = load_json(SESSIONS_FILE, {})


def _persist():
    now = time.time()
    for k in [k for k, s in _sessions.items() if s["exp"] < now]:
        _sessions.pop(k)
    save_json(SESSIONS_FILE, _sessions, 0o600)


def _digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _throttle(ip):
    cnt, until = _fails.get(ip, [0, 0])
    if until > time.time():
        raise ApiError(f"Troppi tentativi: riprova tra {int(until - time.time()) + 1} secondi", 429)


def _failed(ip):
    cnt, _ = _fails.get(ip, [0, 0])
    cnt += 1
    # 5 errori: 30 s, poi raddoppia fino a 15 minuti
    until = time.time() + min(900, 30 * 2 ** (cnt - 5)) if cnt >= 5 else 0
    _fails[ip] = [cnt, until]
    if len(_fails) > 5000:
        _fails.clear()


def login(name, password, remember, ip, ua):
    name = (name or "").strip().lower()
    _throttle(ip)
    users = _users()
    u = users.get(name)
    # Anche se l'utente non esiste si calcola un hash: i tempi di risposta non rivelano niente
    ok = _check(password or "", u["hash"]) if u else (_hash("x") and False)
    if not ok:
        _failed(ip)
        raise ApiError("Utente o password errati", 401)
    _fails.pop(ip, None)
    token = secrets.token_urlsafe(32)
    ttl = LONG_TTL if remember else SHORT_TTL
    now = int(time.time())
    with _lock:
        _load()
        _sessions[_digest(token)] = {"user": name, "exp": now + ttl, "created": now, "seen": now,
                                     "ip": ip, "ua": (ua or "")[:160], "long": bool(remember)}
        _persist()
    return token, ttl


def verify(name, password, ip):
    """Controlla una password senza aprire una sessione (es. per cambiarla)."""
    _throttle(ip)
    u = _users().get((name or "").strip().lower())
    if not u or not _check(password or "", u["hash"]):
        _failed(ip)
        raise ApiError("Password attuale errata", 401)
    _fails.pop(ip, None)


def session_user(token):
    if not token or len(token) > 100:
        return None
    with _lock:
        _load()
        s = _sessions.get(_digest(token))
        if not s:
            return None
        now = time.time()
        if s["exp"] < now or (s.get("long") and now - s.get("seen", now) > IDLE_TTL):
            _sessions.pop(_digest(token), None)
            return None
        if now - s.get("seen", 0) > 300:
            s["seen"] = int(now)
            _persist()
        if s["user"] not in _users():
            return None
        return s["user"]


def logout(token):
    with _lock:
        _load()
        if _sessions.pop(_digest(token or ""), None):
            _persist()


def is_admin(name):
    return bool(_users().get(name, {}).get("admin"))


def list_users():
    _load()
    last = {}
    for s in _sessions.values():
        last[s["user"]] = max(last.get(s["user"], 0), int(s.get("created") or 0))
    return [{"name": n, "admin": u.get("admin", False), "created": u.get("created"), "last_login": last.get(n) or None}
            for n, u in sorted(_users().items())]


# --- gestione degli account (Impostazioni → Account, solo amministratori) ----------------------------

def _close_sessions(name):
    _load()
    for k in [k for k, s in _sessions.items() if s["user"] == name]:
        _sessions.pop(k)
    _persist()


def set_role(name, admin, by):
    """Ruolo: amministratore (tutto) o utente (Home, app e store in sola consultazione)."""
    with _lock:
        users = _users()
        if name not in users:
            raise ApiError("Account non trovato", 404)
        if not admin and sum(1 for u in users.values() if u.get("admin")) <= 1 and users[name].get("admin"):
            raise ApiError("Serve almeno un amministratore")
        if name == by and not admin:
            raise ApiError("Non puoi togliere a te stesso il ruolo di amministratore")
        users[name]["admin"] = bool(admin)
        _save_users(users)
        _close_sessions(name)
    return {"ok": True}


def delete_user(name, by):
    with _lock:
        users = _users()
        if name not in users:
            raise ApiError("Account non trovato", 404)
        if name == by:
            raise ApiError("Non puoi eliminare l'account con cui sei entrato")
        if users[name].get("admin") and sum(1 for u in users.values() if u.get("admin")) <= 1:
            raise ApiError("Serve almeno un amministratore")
        users.pop(name)
        _save_users(users)
        _close_sessions(name)
    return {"ok": True}
