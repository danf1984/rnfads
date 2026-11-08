"""Schermo del NAS: l'interfaccia web sul monitor collegato al NAS (tastiera e mouse del NAS).

Componenti facoltativi, installati dall'interfaccia (circa 100 MB): cage (compositore Wayland "kiosk", MIT) e
WebKitGTK (LGPL) con un piccolo programma (/usr/lib/nido/kiosk.py) che apre solo http://127.0.0.1:8090.
Serve una scheda video con driver (/dev/dri/card*): con nomodeset (es. scheda VMSVGA di VirtualBox) lo schermo
resta la console di testo. Accesso con un account dell'interfaccia, come dal browser.
L'avvio passa da nido-kiosk-boot (all'accensione): se è attivo e c'è la scheda video avvia nido-kiosk, che prende
il posto del login di testo su tty1. Ctrl+Alt+F2 apre sempre una console di testo.
"""
import glob
import os

from .util import ApiError, ETC, LOGS, have, job_state, load_json, run_rc, save_json, start_job

CONF = os.path.join(ETC, "screen.json")
LOG = os.path.join(LOGS, "screen-install.log")
PACKAGES = ["cage", "python3-gi", "gir1.2-gtk-4.0", "gir1.2-webkit-6.0", "fonts-dejavu-core", "libgl1-mesa-dri"]
USER = "nido-kiosk"


def _installed():
    if not have("cage"):
        return False
    rc, _, _ = run_rc(["python3", "-c", "import gi; gi.require_version('Gtk','4.0'); gi.require_version('WebKit','6.0'); "
                       "from gi.repository import Gtk, WebKit"], timeout=30)
    return rc == 0


def _drm():
    return bool(glob.glob("/dev/dri/card*"))


def status():
    c = load_json(CONF, {})
    installing = job_state("screen-install") in ("active", "activating")
    log = ""
    if installing or c.get("install_failed"):
        try:
            with open(LOG, encoding="utf-8", errors="replace") as f:
                log = f.read()[-4000:]
        except OSError:
            pass
    rc, out, _ = run_rc(["systemctl", "is-active", "nido-kiosk.service"], timeout=10)
    return {"installed": _installed(), "installing": installing, "enabled": bool(c.get("enabled")),
            "graphics": _drm(), "running": out.strip() == "active", "log": log,
            "install_failed": bool(c.get("install_failed")) and not installing}


def install():
    if job_state("screen-install") in ("active", "activating"):
        raise ApiError("Installazione già in corso", 409)
    start_job("screen-install", ["screen-install"], log=LOG)
    return status()


def run_install():
    """Job: installa i componenti dagli archivi di Ubuntu e crea l'utente senza privilegi dello schermo."""
    from .updates import APT_ENV
    env = dict(APT_ENV, LC_ALL="C.UTF-8")
    print("=== Installo i componenti dello schermo del NAS: " + " ".join(PACKAGES), flush=True)
    rc, out, err = run_rc(["apt-get", "update"], env=env, timeout=600)
    print(out[-2000:], err[-2000:], flush=True)
    rc, out, err = run_rc(["apt-get", "install", "-y", "--no-install-recommends"] + PACKAGES, env=env, timeout=3600)
    print(out[-6000:], err[-3000:], flush=True)
    c = load_json(CONF, {})
    if rc != 0:
        c["install_failed"] = True
        save_json(CONF, c, 0o644)
        print("ERRORE: installazione non riuscita", flush=True)
        return False
    run_rc(["useradd", "--system", "--create-home", "--home-dir", "/var/lib/nido-kiosk", "--shell", "/usr/sbin/nologin",
            USER], timeout=30)
    run_rc(["usermod", "-aG", "video,render,input", USER], timeout=30)
    c.pop("install_failed", None)
    save_json(CONF, c, 0o644)
    print("Fatto.", flush=True)
    return True


def set_enabled(on):
    c = load_json(CONF, {})
    if on and not _installed():
        raise ApiError("Prima installa i componenti dello schermo")
    c["enabled"] = bool(on)
    save_json(CONF, c, 0o644)
    if on:
        run_rc(["systemctl", "enable", "nido-kiosk-boot.service"], timeout=30)
        if not _drm():
            raise ApiError("Attivato, ma questo NAS non ha una scheda video con driver: lo schermo resta la console di "
                           "testo (nelle VM VirtualBox scegli la scheda video VBoxSVGA)")
        run_rc(["systemctl", "reset-failed", "nido-kiosk.service"], timeout=15)
        run_rc(["systemctl", "start", "--no-block", "nido-kiosk.service"], timeout=30)
    else:
        run_rc(["systemctl", "disable", "nido-kiosk-boot.service"], timeout=30)
        run_rc(["systemctl", "stop", "nido-kiosk.service"], timeout=60)
        run_rc(["systemctl", "start", "--no-block", "getty@tty1.service"], timeout=30)
    return status()


def boot():
    """All'accensione (nido-kiosk-boot): avvia lo schermo se è attivo e c'è una scheda video con driver."""
    if load_json(CONF, {}).get("enabled") and _installed() and _drm():
        run_rc(["systemctl", "start", "--no-block", "nido-kiosk.service"], timeout=30)
    return True
