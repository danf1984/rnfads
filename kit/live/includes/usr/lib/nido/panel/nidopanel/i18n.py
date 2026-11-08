"""Traduzione dei testi generati dal server (notifiche) nella lingua scelta per il NAS.

Usa gli stessi dizionari dell'interfaccia (ui/lang/<lingua>.json) e le stesse regole di
ui/i18n.js: testo esatto, poi modelli con {0}, {1}… (i pezzi variabili si traducono a loro
volta, se sono testi noti). Il testo di base resta l'italiano.
"""
import json
import os
import re

LANG_FILE = "/etc/nido/ui-language.json"
LANGS = ("it", "en", "es", "de")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_cache = {}


def current():
    try:
        with open(LANG_FILE, encoding="utf-8") as f:
            v = json.load(f).get("lang")
        return v if v in LANGS else "it"
    except (OSError, ValueError, AttributeError):
        return "it"


def _load(lang):
    ui = os.environ.get("NIDO_UI_DIR", os.path.join(_ROOT, "ui"))
    path = os.path.join(ui, "lang", f"{lang}.json")
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    c = _cache.get(lang)
    if c and c[0] == mtime:
        return c[1]
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    exact = dict(data.get("exact") or {})
    pats = []
    for p in data.get("pats") or []:
        it, t = p[0], p[1]
        rx = re.escape(it)
        rx = re.sub(r"\\\{(\d+)\\\}", "(.+?)", rx)
        if len(p) > 2 and p[2]:
            rx += "[a-zà-ù]{0,3}"
        pats.append((re.compile("^" + rx + "$", re.I | re.S), t, len(it)))
    pats.sort(key=lambda x: -x[2])
    d = (exact, pats)
    _cache[lang] = (mtime, d)
    return d


def _core(d, s, depth=0):
    exact, pats = d
    if s in exact:
        return exact[s]
    if depth > 2:
        return None
    for rx, t, _ in pats:
        m = rx.match(s)
        if m:
            def sub(x):
                g = m.group(int(x.group(1)) + 1)
                if g is None:
                    return ""
                y = _core(d, g.strip(), depth + 1)
                return y if y is not None else g
            return re.sub(r"\{(\d+)\}", sub, t)
    return None


def _one(d, s):
    core = re.sub(r"[ \t]+", " ", s).strip()
    if not core or not re.search(r"[a-zà-ù]{2}", core, re.I):
        return s
    out = _core(d, core)
    if out is None:
        m = re.match(r"^(.*?)(\s*[.:;…])$", core)
        if m and m.group(1):
            t = _core(d, m.group(1))
            if t is not None:
                out = t + m.group(2)
    if out is None:
        return s
    return s[:len(s) - len(s.lstrip())] + out


def tr(s, lang=None):
    """Traduce un testo (anche su più righe) nella lingua del NAS; se non lo conosce lo lascia com'è."""
    if not s or not isinstance(s, str):
        return s
    lang = lang or current()
    if lang == "it":
        return s
    d = _load(lang)
    if not d:
        return s
    return "\n".join(_one(d, line) for line in s.split("\n"))
