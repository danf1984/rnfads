"""Scaricamento dei cataloghi delle app (funzioni comuni usate da catalog.py).

Fino al 31/10/2026 qui c'erano anche i convertitori degli store ZimaOS (v2) e Unraid CA e la
configurazione di CasaOS: tolti su scelta dell'utente, per evitare problemi con i marchi.
"""
import urllib.error
import urllib.request

from .util import user_agent

UA = {"User-Agent": user_agent("catalog")}


def _fetch(url, timeout=60, tries=1):
    """Scarica un indirizzo chiedendo la compressione gzip (i cataloghi grandi si riducono di molto).
    Con tries > 1 riprova sugli errori di rete temporanei."""
    import gzip
    import time
    last = None
    for k in range(max(1, tries)):
        try:
            req = urllib.request.Request(url, headers={**UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
                if (r.headers.get("Content-Encoding") or "").lower() == "gzip" or data[:2] == b"\x1f\x8b":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as e:
            last = e
            if e.code < 500 and e.code != 429:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
        if k + 1 < tries:
            time.sleep(3 * (k + 1))
    raise last


def explain(e):
    """Messaggio d'errore comprensibile per i problemi di rete più comuni."""
    import socket
    import ssl
    if isinstance(e, urllib.error.HTTPError):
        return {404: "indirizzo non trovato (404): la fonte potrebbe essere stata spostata",
                403: "accesso negato dal sito (403)", 429: "troppe richieste (429): riprova più tardi"}.get(
            e.code, f"il sito ha risposto con l'errore {e.code}")
    r = getattr(e, "reason", e)
    if isinstance(r, socket.gaierror):
        return "nome del sito non risolto: controlla la connessione a internet e il DNS"
    if isinstance(r, ssl.SSLCertVerificationError) or isinstance(e, ssl.SSLCertVerificationError):
        return "certificato del sito non valido (controlla data e ora del NAS)"
    if isinstance(r, (TimeoutError, socket.timeout)) or "timed out" in str(r):
        return "il sito non risponde (tempo scaduto)"
    if isinstance(r, ConnectionRefusedError):
        return "connessione rifiutata"
    if isinstance(r, (ConnectionResetError, ConnectionAbortedError)):
        return "connessione interrotta durante lo scaricamento"
    return str(r)[:200] or e.__class__.__name__
