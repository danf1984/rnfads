"""Controllo periodico (ogni 15 minuti): salute e temperatura dei dischi, spazio, aggiornamenti."""
from . import disks, notify, updates


def run_monitor():
    conf = notify.load()
    for d in disks.list_disks():
        name = f"{d['model'] or d['name']} ({d['name']})"
        h = d["health"]
        if h in ("guasto", "attenzione"):
            notify.event("disk_health",
                         f"Disco {name}: stato {h}",
                         "Il controllo SMART segnala un problema. Fai subito un backup dei dati.",
                         level="error", key=f"health-{d.get('serial') or d['name']}-{h}")
        t = d["smart"].get("temperature")
        if t and t >= conf["temp_threshold"]:
            notify.event("disk_temp", f"Disco {name} caldo: {t} °C",
                         f"Soglia impostata: {conf['temp_threshold']} °C. Controlla la ventilazione.",
                         level="warning", key=f"temp-{d['name']}")
    for fs in disks.filesystems_usage():
        if fs["percent"] >= conf["space_threshold"]:
            notify.event("disk_space", f"Spazio quasi finito in {fs['mount']}",
                         f"Occupato il {fs['percent']}%.", level="warning",
                         key=f"space-{fs['mount']}")
    data = updates.refresh_cache()
    pkgs = data.get("packages", [])
    if pkgs:
        sec = sum(1 for p in pkgs if p.get("security"))
        msg = f"{len(pkgs)} pacchetti da aggiornare" + (f", di cui {sec} di sicurezza" if sec else "")
        notify.event("updates", "Aggiornamenti disponibili", msg, level="info",
                     key=f"updates-{len(pkgs)}-{sec}")
    # Certificato di casa: si rinnova da solo se sta per scadere o se è cambiato l'indirizzo IP
    try:
        from . import https
        https.daily()
    except Exception as e:  # noqa: BLE001
        print("https:", e)
