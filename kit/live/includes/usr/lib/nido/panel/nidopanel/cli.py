"""Comandi eseguiti da timer e operazioni lunghe (systemd-run).

  python3 -m nidopanel.cli backup-run <id>
  python3 -m nidopanel.cli backup-restore <id> <snapshot> <cartella>
  python3 -m nidopanel.cli updates-check | updates-install
  python3 -m nidopanel.cli monitor
  python3 -m nidopanel.cli notify "<titolo>" "<messaggio>" [livello] [evento]
  python3 -m nidopanel.cli catalog-build          aggiorna il catalogo delle app
  python3 -m nidopanel.cli apps-autoupdate        controllo e aggiornamento notturno delle app
  python3 -m nidopanel.cli netmounts-mount        ricollega i dischi e le cartelle di rete (all'avvio)
  python3 -m nidopanel.cli ui-user <nome>         crea un account o ne cambia la password
  python3 -m nidopanel.cli standby-daemon         standby dei dischi (servizio nido-standby)
  python3 -m nidopanel.cli https-apply            certificato di casa + configurazione di Caddy (primo avvio)
  python3 -m nidopanel.cli mdns                   nomi .local delle app (servizio nido-mdns)
  python3 -m nidopanel.cli power-scheduled        spegnimento programmato (timer nido-poweroff)
  python3 -m nidopanel.cli uptime-tick | uptime-shutdown   contatore del tempo di accensione
  python3 -m nidopanel.cli apps-move <disco>       sposta Docker e AppData su un altro disco
  python3 -m nidopanel.cli apps-move-back          riporta Docker e AppData sul disco di sistema
  python3 -m nidopanel.cli release-upgrade         passa alla versione nuova di Ubuntu
  python3 -m nidopanel.cli release-verify          controlli dopo il passaggio (al primo avvio)
  python3 -m nidopanel.cli selfupdate-install      installa l'aggiornamento caricato (pacchetto .deb)
  python3 -m nidopanel.cli selfupdate-rollback     rimette la versione precedente del pacchetto
  python3 -m nidopanel.cli network-rollback        rimette le impostazioni di rete di prima (timer dopo una modifica)
  python3 -m nidopanel.cli screen-install          installa i componenti dello schermo del NAS
  python3 -m nidopanel.cli selfupdate-online       scarica e installa l'aggiornamento online del canale scelto
  python3 -m nidopanel.cli selfupdate-check        controlla il canale online (timer notturno: avvisa o installa)
"""
import sys


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, args = argv[0], argv[1:]
    if cmd == "backup-run":
        from .backup import run_job
        return 0 if run_job(args[0]) else 1
    if cmd == "backup-restore":
        from .backup import run_restore
        return 0 if run_restore(*args[:3]) else 1
    if cmd == "updates-check":
        from .updates import run_check
        return 0 if run_check() else 1
    if cmd == "updates-install":
        from .updates import run_install
        return 0 if run_install() else 1
    if cmd == "monitor":
        from .monitor import run_monitor
        run_monitor()
        return 0
    if cmd == "remote-install":
        from .remote import run_install
        return 0 if run_install(args[0]) else 1
    if cmd in ("uptime-tick", "uptime-shutdown"):
        from .uptime import tick
        tick(final=cmd == "uptime-shutdown")
        return 0
    if cmd == "apps-move":
        from .appmove import run_move
        return 0 if run_move(args[0]) else 1
    if cmd == "apps-move-back":
        from .appmove import run_move_back
        return 0 if run_move_back() else 1
    if cmd == "selfupdate-install":
        from .selfupdate import run_install
        return 0 if run_install() else 1
    if cmd == "network-rollback":
        from .network import rollback
        rollback()
        return 0
    if cmd == "screen-install":
        from .screen import run_install
        return 0 if run_install() else 1
    if cmd == "selfupdate-online":
        from .online import run_install
        return 0 if run_install() else 1
    if cmd == "selfupdate-check":
        from .online import run_check
        return 0 if run_check() else 1
    if cmd == "selfupdate-rollback":
        from .selfupdate import run_rollback
        return 0 if run_rollback() else 1
    if cmd == "release-upgrade":
        from .release import run_upgrade
        return 0 if run_upgrade() else 1
    if cmd == "release-verify":
        from .release import run_verify
        return 0 if run_verify() else 1
    if cmd == "catalog-build":
        from .catalog import build
        idx = build()
        return 0 if idx.get("apps") else 1
    if cmd == "apps-autoupdate":
        from .apps import nightly
        nightly()
        return 0
    if cmd == "netmounts-mount":
        from .disks import mount_boot_disks
        from .netmounts import mount_all
        try:
            mount_boot_disks()
        except Exception as e:  # noqa: BLE001 — le cartelle di rete vanno collegate comunque
            print(f"dischi: {e}", flush=True)
        mount_all()
        return 0
    if cmd == "standby-daemon":
        from .standby import run_daemon
        run_daemon()
        return 0
    if cmd == "https-apply":
        from .https import apply
        from .util import ApiError
        try:
            print(apply())
        except ApiError as e:
            print(e.message)
            return 1
        return 0
    if cmd == "mdns":
        from .https import run_mdns
        run_mdns()
        return 0
    if cmd == "ui-user":
        import getpass
        from . import auth
        from .util import ApiError
        if not args:
            print("Uso: ui-user <nome>")
            return 2
        pw = getpass.getpass("Nuova password: ")
        if pw != getpass.getpass("Ripeti la password: "):
            print("Le password non coincidono")
            return 1
        try:
            if any(u["name"] == args[0] for u in auth.list_users()):
                auth.set_password(args[0], pw)
                print("Password cambiata")
            else:
                auth.create_user(args[0], pw, admin=True)
                print("Account amministratore creato")
        except ApiError as e:
            print(e.message)
            return 1
        return 0
    if cmd == "power-scheduled":
        from .powersched import run_scheduled
        return run_scheduled(dry_run="--dry-run" in args)
    if cmd == "notify":
        from .notify import event
        title = args[0] if args else "Avviso"
        message = args[1] if len(args) > 1 else ""
        level = args[2] if len(args) > 2 else "warning"
        kind = args[3] if len(args) > 3 else "disk_health"
        print(event(kind, title, message, level))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
