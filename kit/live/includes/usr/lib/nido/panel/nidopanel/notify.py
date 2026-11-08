"""Notifiche: Telegram, ntfy (push sul telefono), email, webhook (Home Assistant)."""
import datetime
import json
import os
import smtplib
import ssl
import time
import urllib.parse
import urllib.request
from email.message import EmailMessage

from .util import ApiError, ETC, STATE, load_json, save_json

CONF = os.path.join(ETC, "notify.json")
SENT = os.path.join(STATE, "notify-sent.json")
REPEAT_AFTER = 24 * 3600

EVENTS = {
    "disk_health": "Disco con problemi (SMART)",
    "disk_space": "Spazio in esaurimento",
    "disk_temp": "Disco troppo caldo",
    "backup_fail": "Backup non riuscito",
    "backup_ok": "Backup completato",
    "updates": "Aggiornamenti disponibili o installati",
    "power": "Spegnimento programmato",
    "apps": "App aggiornate, tornate indietro o spostate",
}

DEFAULT = {
    "channels": {
        "telegram": {"enabled": False, "token": "", "chat_id": ""},
        "ntfy": {"enabled": False, "server": "https://ntfy.sh", "topic": "", "token": ""},
        "email": {"enabled": False, "host": "", "port": 587, "security": "starttls",
                  "user": "", "password": "", "from": "", "to": ""},
        "webhook": {"enabled": False, "url": ""},
    },
    "events": {k: True for k in EVENTS},
    "space_threshold": 90,
    "temp_threshold": 55,
}
SECRET_FIELDS = {("telegram", "token"), ("ntfy", "token"), ("email", "password")}
MASK = "••••••••"


def load():
    data = load_json(CONF, {})
    out = json.loads(json.dumps(DEFAULT))
    for ch, vals in (data.get("channels") or {}).items():
        if ch in out["channels"]:
            out["channels"][ch].update(vals)
    out["events"].update(data.get("events") or {})
    for k in ("space_threshold", "temp_threshold"):
        if k in data:
            out[k] = data[k]
    return out


def get():
    data = load()
    for ch, field in SECRET_FIELDS:
        if data["channels"][ch].get(field):
            data["channels"][ch][field] = MASK
    data["event_names"] = EVENTS
    return data


def save(body):
    cur = load()
    for ch, vals in (body.get("channels") or {}).items():
        if ch not in cur["channels"]:
            continue
        for k, v in vals.items():
            if k not in cur["channels"][ch]:
                continue
            if (ch, k) in SECRET_FIELDS and v == MASK:
                continue  # campo segreto non modificato
            if k == "enabled":
                v = bool(v)
            elif k == "port":
                v = int(v or 0)
            else:
                v = str(v).strip()[:500]
            cur["channels"][ch][k] = v
    for k, v in (body.get("events") or {}).items():
        if k in EVENTS:
            cur["events"][k] = bool(v)
    for k, lo, hi in (("space_threshold", 50, 99), ("temp_threshold", 35, 80)):
        if k in body:
            cur[k] = max(lo, min(hi, int(body[k])))
    save_json(CONF, cur, 0o600)
    return get()


# --- invio ------------------------------------------------------------------------------------

def _hostname():
    return os.uname().nodename


def _http(url, data, headers=None, timeout=15):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status


def _send_telegram(c, title, message):
    if not c["token"] or not c["chat_id"]:
        raise ApiError("Telegram: servono token del bot e chat ID")
    body = json.dumps({"chat_id": c["chat_id"], "text": f"{title}\n{message}".strip()}).encode()
    _http(f"https://api.telegram.org/bot{c['token']}/sendMessage", body,
          {"Content-Type": "application/json"})


def _send_ntfy(c, title, message, level):
    if not c["topic"]:
        raise ApiError("ntfy: manca l'argomento (topic)")
    headers = {"Title": title.encode("utf-8").decode("latin-1", "ignore"),
               "Priority": {"error": "high", "warning": "default"}.get(level, "low"),
               "Tags": {"error": "warning", "warning": "warning"}.get(level, "white_check_mark")}
    if c.get("token"):
        headers["Authorization"] = f"Bearer {c['token']}"
    url = c["server"].rstrip("/") + "/" + urllib.parse.quote(c["topic"])
    _http(url, (message or title).encode("utf-8"), headers)


def _send_email(c, title, message):
    if not c["host"] or not c["to"]:
        raise ApiError("Email: servono server SMTP e destinatario")
    msg = EmailMessage()
    msg["Subject"] = f"[{_hostname()}] {title}"
    msg["From"] = c["from"] or c["user"] or f"nas@{_hostname()}"
    msg["To"] = c["to"]
    msg.set_content(message or title)
    ctx = ssl.create_default_context()
    if c["security"] == "ssl":
        s = smtplib.SMTP_SSL(c["host"], c["port"] or 465, context=ctx, timeout=20)
    else:
        s = smtplib.SMTP(c["host"], c["port"] or 587, timeout=20)
        if c["security"] == "starttls":
            s.starttls(context=ctx)
    try:
        if c["user"]:
            s.login(c["user"], c["password"])
        s.send_message(msg)
    finally:
        s.quit()


def _send_webhook(c, title, message, level, event):
    if not c["url"]:
        raise ApiError("Webhook: manca l'indirizzo")
    body = json.dumps({"title": title, "message": message, "level": level, "event": event,
                       "host": _hostname(),
                       "time": datetime.datetime.now().isoformat(timespec="seconds")}).encode()
    _http(c["url"], body, {"Content-Type": "application/json"})


def send(title, message="", level="info", event="test", only=None):
    """Invia a tutti i canali attivi. Restituisce {canale: "ok" | errore}."""
    data = load()
    results = {}
    try:   # nella lingua scelta per il NAS (il testo di base è italiano)
        from . import i18n
        title, message = i18n.tr(title), i18n.tr(message)
    except Exception:  # noqa: BLE001 — una traduzione mancante non deve fermare la notifica
        pass
    for name, c in data["channels"].items():
        if only and name != only:
            continue
        if not c.get("enabled") and not only:
            continue
        try:
            if name == "telegram":
                _send_telegram(c, title, message)
            elif name == "ntfy":
                _send_ntfy(c, title, message, level)
            elif name == "email":
                _send_email(c, title, message)
            elif name == "webhook":
                _send_webhook(c, title, message, level, event)
            results[name] = "ok"
        except ApiError as e:
            results[name] = e.message
        except Exception as e:  # noqa: BLE001
            results[name] = str(e)
    return results


def event(kind, title, message="", level="warning", key=None):
    """Notifica un evento, se abilitato, senza ripetere lo stesso avviso entro 24 ore."""
    data = load()
    if not data["events"].get(kind, True):
        return {}
    key = key or f"{kind}:{title}"
    sent = load_json(SENT, {})
    now = time.time()
    if now - sent.get(key, 0) < REPEAT_AFTER:
        return {}
    res = send(title, message, level, kind)
    if any(v == "ok" for v in res.values()):
        sent[key] = now
        sent = {k: v for k, v in sent.items() if now - v < 7 * 24 * 3600}
        save_json(SENT, sent, 0o644)
    return res


def test(channel=None):
    res = send("Prova di notifica", f"Se leggi questo messaggio, le notifiche di {_hostname()} funzionano.",
               "info", "test", only=channel)
    if not res:
        raise ApiError("Nessun canale attivo: attivane almeno uno e salva")
    return res
