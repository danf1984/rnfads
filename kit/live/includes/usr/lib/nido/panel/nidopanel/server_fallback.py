"""Porta 80 di riserva: se Caddy non parte, l'interfaccia resta raggiungibile in HTTP.

Con Caddy davanti l'interfaccia ascolta solo su 127.0.0.1:8090. Se Caddy è fermo o in errore per
due controlli di fila, l'interfaccia apre anche 0.0.0.0:80 (NIDO_FALLBACK_LISTEN) così si può entrare
e sistemare l'HTTPS. Prima di riavviare Caddy la porta viene liberata (release()).
"""
import os
import threading
import time

_state = {"srv": None, "handler": None, "server": None, "paused": 0}
_lock = threading.Lock()


def configure(server_cls, handler_cls):
    _state["server"], _state["handler"] = server_cls, handler_cls


def running():
    return _state["srv"] is not None


def release(pause=60):
    """Chiude la porta di riserva e non la riapre per "pause" secondi (tempo per far ripartire Caddy)."""
    with _lock:
        _state["paused"] = time.time() + pause
        srv = _state["srv"]
        _state["srv"] = None
    if srv:
        srv.shutdown()
        srv.server_close()


def _open(addr):
    host, _, port = addr.rpartition(":")
    try:
        srv = _state["server"]((host or "0.0.0.0", int(port)), _state["handler"])
    except OSError:
        return False            # la porta è occupata (Caddy sta ripartendo): riprovo dopo
    with _lock:
        _state["srv"] = srv
    threading.Thread(target=srv.serve_forever, daemon=True, name="fallback-80").start()
    print(f"Caddy non risponde: interfaccia anche su {addr} (riserva)", flush=True)
    return True


def watchdog():
    from .https import caddy_active
    from .util import systemd_running
    addr = os.environ.get("NIDO_FALLBACK_LISTEN", "0.0.0.0:80")
    if not addr or addr == "off":
        return
    bad = 0
    while True:
        time.sleep(20)
        if not systemd_running() or time.time() < _state["paused"]:
            continue
        if caddy_active():
            bad = 0
            if running():
                release(pause=0)
            continue
        bad += 1
        if bad >= 2 and not running():
            _open(addr)
