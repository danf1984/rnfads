"""Contatore del tempo di accensione.

- Tempo dall'ultimo avvio (dal kernel, /proc/uptime).
- Ore totali di accensione dall'installazione: il NAS le conta ogni minuto in
  /var/lib/nido/uptime.json, così restano anche dopo spegnimenti e riavvii.
- Numero di avvii, ultimo spegnimento e se è stato regolare (spegni/riavvia) o improvviso
  (mancanza di corrente, blocco): allo spegnimento regolare il servizio nido-uptime scrive
  un segno con l'identificativo dell'avvio; se all'avvio successivo il segno manca, lo
  spegnimento è stato improvviso.
"""
import os
import threading
import time

from .util import STATE, load_json, save_json

FILE = os.path.join(STATE, "uptime.json")
BOOT_ID = "/proc/sys/kernel/random/boot_id"
_lock = threading.Lock()


def _boot_id():
    try:
        with open(BOOT_ID) as f:
            return f.read().strip()
    except OSError:
        return "?"


def _since_boot():
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except (OSError, ValueError, IndexError):
        return 0.0


def _installed_guess():
    for p in ("/var/log/installer", "/etc/machine-id", "/etc/hostname"):
        try:
            return int(os.stat(p).st_mtime)
        except OSError:
            pass
    return int(time.time())


def tick(final=False):
    """Aggiorna il conteggio (ogni minuto dal servizio dell'interfaccia; final=True allo spegnimento)."""
    now = time.time()
    bid = _boot_id()
    with _lock:
        d = load_json(FILE, {})
        if not d:
            d = {"counting_since": int(now), "installed": _installed_guess(), "total": 0.0, "boots": 0,
                 "boot_id": None, "last_tick": None, "last_shutdown": None, "history": []}
        if d.get("boot_id") != bid:
            # Avvio nuovo: chiudo quello precedente
            if d.get("boot_id"):
                clean = d.get("clean_boot_id") == d["boot_id"]
                d["last_shutdown"] = {"time": int(d.get("clean_time") or d.get("last_tick") or now),
                                      "clean": clean}
                d["history"] = (d.get("history") or [])[-29:] + [
                    {"boot": int(d.get("boot_time") or 0), "end": d["last_shutdown"]["time"], "clean": clean}]
                if not clean:
                    d["unclean"] = int(d.get("unclean") or 0) + 1
            d["boots"] = int(d.get("boots") or 0) + 1
            d["boot_id"] = bid
            up = _since_boot()
            d["boot_time"] = int(now - up)
            d["total"] = float(d.get("total") or 0) + up     # il tempo prima che partisse il conteggio
            d["last_tick"] = now
        else:
            last = d.get("last_tick") or now
            # Se il sistema è stato sospeso o l'orologio è saltato, conto al massimo 3 minuti
            d["total"] = float(d.get("total") or 0) + max(0.0, min(now - last, 180.0))
            d["last_tick"] = now
        if final:
            d["clean_boot_id"] = bid
            d["clean_time"] = int(now)
        save_json(FILE, d, 0o644)
        return d


def summary():
    d = load_json(FILE, {})
    if d.get("boot_id") != _boot_id():
        try:
            d = tick()
        except OSError:
            pass
    up = _since_boot()
    extra = max(0.0, min(time.time() - (d.get("last_tick") or time.time()), 180.0))
    total = float(d.get("total") or 0) + extra
    return {
        "since_boot": int(up), "boot_time": int(time.time() - up),
        "total_seconds": int(total), "total_hours": round(total / 3600, 1),
        "boots": int(d.get("boots") or 1), "unclean": int(d.get("unclean") or 0),
        "counting_since": d.get("counting_since"), "installed": d.get("installed"),
        "last_shutdown": d.get("last_shutdown"),
    }


def start_thread():
    def loop():
        while True:
            try:
                tick()
            except Exception as e:  # noqa: BLE001
                print(f"uptime: {e}", flush=True)
            time.sleep(60)
    threading.Thread(target=loop, daemon=True, name="uptime").start()
