"""Aggiornamento online del sistema: canale firmato su GitHub Pages (o un altro sito statico).

Sul sito, per ogni canale (stable, beta) ci sono:
  <canale>.json        manifesto: versione, nome del pacchetto, sha256, dimensione, note
  <canale>.json.sig    firma Ed25519 del manifesto (stessa chiave dei pacchetti)
  pool/<pacchetto>.deb e pool/<pacchetto>.deb.sig
Il NAS scarica il manifesto, controlla la firma con le chiavi pubbliche della ISO, e se c'è una
versione più nuova avvisa (notifica e sensore di Home Assistant). "Aggiorna ora" scarica il
pacchetto e lo installa con lo stesso procedimento del caricamento manuale (firma, snapshot,
controllo che l'interfaccia riparta, ritorno automatico alla versione di prima).
Il manifesto firmato impedisce di "spingere" un pacchetto vecchio ma firmato (downgrade).
I manifesti e i pacchetti li prepara kit/strumenti/pubblica-aggiornamento.{sh,ps1}.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import urllib.request

from . import selfupdate
from .util import ApiError, ETC, job_state, load_json, product, read_file, save_json, start_job

CONF = os.path.join(ETC, "selfupdate.json")       # stesso file della modalità sviluppatore
CHANNELS = ("stable", "beta")
MODES = ("off", "notify", "nightly")               # off = mai, notify = solo avviso, nightly = installa di notte
UA = "RNFADS-update/1"
MAX_MANIFEST = 256 * 1024


def _default_url():
    m = re.search(r'^NIDO_UPDATE_URL="?([^"\n]*)"?', read_file(os.path.join(ETC, "nido.conf")) or "", re.M)
    return (m.group(1).strip() if m else "")


def settings():
    c = load_json(CONF, {})
    url = (c.get("url") or _default_url()).strip()
    return {"url": url, "default_url": _default_url(),
            "channel": c.get("channel") if c.get("channel") in CHANNELS else "stable",
            "mode": c.get("mode") if c.get("mode") in MODES else "notify"}


def set_settings(d):
    c = load_json(CONF, {})
    if "channel" in d:
        if d["channel"] not in CHANNELS:
            raise ApiError("Canale non valido")
        c["channel"] = d["channel"]
    if "mode" in d:
        if d["mode"] not in MODES:
            raise ApiError("Scelta non valida")
        c["mode"] = d["mode"]
    if "url" in d:
        u = (d.get("url") or "").strip()
        # Anche http:// (es. una cartella sul PC o sul NAS di casa): la sicurezza la danno le firme, non il sito
        if u and not re.match(r"^https?://[A-Za-z0-9.-]+(:\d+)?(/[^\s]*)?$", u):
            raise ApiError("Indirizzo non valido: deve iniziare con http:// o https://")
        if u and u == _default_url():
            u = ""
        c["url"] = u
    save_json(CONF, c, 0o600)
    return status()


def _get(url, limit, dest=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            if dest is None:
                data = r.read(limit + 1)
                if len(data) > limit:
                    raise ApiError("Risposta troppo grande")
                return data
            n = 0
            with open(dest, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    n += len(b)
                    if n > limit:
                        raise ApiError("File troppo grande")
                    f.write(b)
            return n
    except ApiError:
        raise
    except Exception as e:  # noqa: BLE001
        code = getattr(e, "code", None)
        raise ApiError(f"Sito degli aggiornamenti non raggiungibile ({code or str(e)[:80]})") from None


def _verify_bytes(data, sig):
    """Firma Ed25519 di un manifesto: stesso controllo dei pacchetti."""
    with tempfile.TemporaryDirectory() as d:
        p, s = os.path.join(d, "m"), os.path.join(d, "m.sig")
        with open(p, "wb") as f:
            f.write(data)
        with open(s, "wb") as f:
            f.write(sig)
        return selfupdate.verify(p, s)


def _base(st):
    if not st["url"]:
        raise ApiError("Indirizzo degli aggiornamenti online non impostato")
    return st["url"].rstrip("/") + "/"


def check(save=True):
    """Scarica il manifesto del canale scelto e dice se c'è una versione più nuova."""
    st = settings()
    res = {"checked": int(time.time()), "channel": st["channel"]}
    try:
        base = _base(st)
        raw = _get(base + st["channel"] + ".json", MAX_MANIFEST)
        sig = _get(base + st["channel"] + ".json.sig", 4096)
        ok, who = _verify_bytes(raw, sig)
        if not ok and not selfupdate.devmode():
            raise ApiError(f"Manifesto degli aggiornamenti non valido: {who}")
        m = json.loads(raw.decode("utf-8"))
        if m.get("package") not in (None, selfupdate.PACKAGE):
            raise ApiError("Il manifesto non è per questo sistema")
        deb = os.path.basename(m.get("deb") or "")
        if not re.match(r"^[A-Za-z0-9._+~-]{1,120}\.deb$", deb) or not re.match(r"^[0-9a-f]{64}$", m.get("sha256", "")):
            raise ApiError("Manifesto degli aggiornamenti incompleto")
        cur = selfupdate.installed_version()
        pv = m.get("package_version") or ""
        newer = bool(pv) and (not cur or selfupdate._cmp(pv, cur, "gt"))
        res.update({"ok": True, "signed": ok, "signature": who, "version": m.get("version"), "package_version": pv,
                    "deb": deb, "sha256": m["sha256"], "size": int(m.get("size") or 0),
                    "notes": (m.get("notes") or "")[:4000], "date": m.get("date"), "current": cur,
                    "available": newer})
    except ApiError as e:
        res.update({"ok": False, "error": e.message, "available": False})
    except (ValueError, KeyError, TypeError):
        res.update({"ok": False, "error": "Manifesto degli aggiornamenti non leggibile", "available": False})
    if save:
        data = load_json(selfupdate.FILE, {})
        data["online"] = res
        save_json(selfupdate.FILE, data, 0o644)
    return res


def status():
    data = load_json(selfupdate.FILE, {})
    return {**settings(), "last": data.get("online"),
            "running": job_state("selfupdate") in ("active", "activating")}


def _busy():
    for j in ("selfupdate", "selfupdate-rollback", "updates-install", "release-upgrade"):
        if job_state(j) in ("active", "activating"):
            return True
    return False


def start_install():
    if _busy():
        raise ApiError("È già in corso un aggiornamento", 409)
    res = check()
    if not res.get("ok"):
        raise ApiError(res.get("error") or "Controllo non riuscito")
    if not res.get("available"):
        raise ApiError("Il sistema è già aggiornato")
    start_job("selfupdate", ["selfupdate-online"], log=selfupdate.LOG)
    return {"ok": True}


def download(res):
    """Scarica pacchetto e firma in INCOMING e controlla sha256 (la firma la controlla run_install)."""
    base = _base(settings())
    shutil.rmtree(selfupdate.INCOMING, ignore_errors=True)
    os.makedirs(selfupdate.INCOMING, exist_ok=True)
    deb = os.path.join(selfupdate.INCOMING, res["deb"])
    selfupdate._say(f"Scarico {res['deb']} ({res['size'] // 1024 // 1024 or 1} MB circa)")
    _get(base + "pool/" + res["deb"], selfupdate.MAX_SIZE, dest=deb + ".part")
    h = hashlib.sha256()
    with open(deb + ".part", "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    if h.hexdigest() != res["sha256"]:
        os.unlink(deb + ".part")
        raise ApiError("Il file scaricato non corrisponde al manifesto (sha256 diverso)")
    os.replace(deb + ".part", deb)
    _get(base + "pool/" + res["deb"] + ".sig", 4096, dest=deb + ".sig")
    return deb


def run_install():
    """Job: scarica l'aggiornamento del canale e lo installa."""
    selfupdate._say(f"=== Aggiornamento online di {product()[0]}")
    res = check()
    if not res.get("ok"):
        selfupdate._say(f"ERRORE: {res.get('error')}")
        return False
    if not res.get("available"):
        selfupdate._say("Il sistema è già aggiornato.")
        return True
    try:
        download(res)
        selfupdate.inspect()
    except ApiError as e:
        selfupdate._say(f"ERRORE: {e.message}")
        selfupdate._finish(ok=False, error=e.message, to=res.get("package_version"))
        return False
    return selfupdate.run_install()


def run_check():
    """Timer di ogni notte: controlla, avvisa una volta per versione, e se scelto installa."""
    from . import notify
    st = settings()
    if st["mode"] == "off" or not st["url"]:
        print("Aggiornamento online spento o senza indirizzo.", flush=True)
        return True
    res = check()
    print(json.dumps(res, ensure_ascii=False), flush=True)
    if not res.get("available"):
        return True
    if st["mode"] == "nightly" and not _busy():
        notify.event("updates", f"Installo {product()[0]} {res.get('version')}",
                     "Aggiornamento automatico di notte.", level="info", key=f"online-auto-{res['package_version']}")
        start_job("selfupdate", ["selfupdate-online"], log=selfupdate.LOG)
        return True
    data = load_json(selfupdate.FILE, {})
    if data.get("online_notified") == res["package_version"]:
        return True   # già avvisato per questa versione
    data["online_notified"] = res["package_version"]
    save_json(selfupdate.FILE, data, 0o644)
    notify.event("updates", f"{product()[0]} {res.get('version')} disponibile",
                 "Installalo da Impostazioni > Aggiornamenti di sistema.", level="info",
                 key=f"online-{res['package_version']}")
    return True
