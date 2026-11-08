#!/bin/bash
# Snapshot automatico prima e dopo ogni installazione/aggiornamento di pacchetti.
# Chiamato da /etc/apt/apt.conf.d/80nido-snapshot. Non blocca mai apt.
#   snapshot-apt.sh pre | post
STATE=/run/nido-apt-snapshot

# L'aggiornamento avviato dall'interfaccia crea già la sua coppia di snapshot
[ -n "${NIDO_NO_APT_SNAPSHOT:-}" ] && exit 0
# Se c'è ancora l'hook di Ubuntu per snapper (non messo da parte), non facciamo doppioni
[ -e /etc/apt/apt.conf.d/80snapper ] && exit 0
[ -f /etc/snapper/configs/root ] || exit 0
command -v snapper >/dev/null 2>&1 || exit 0

case "${1:-}" in
  pre)
    num=$(snapper --no-dbus -c root create --type pre --print-number \
            --cleanup-algorithm number --description "prima di apt") || exit 0
    echo "$num" > "$STATE"
    ;;
  post)
    [ -f "$STATE" ] || exit 0
    pre=$(cat "$STATE"); rm -f "$STATE"
    snapper --no-dbus -c root create --type post --pre-number "$pre" \
      --cleanup-algorithm number --description "dopo apt" || true
    ;;
esac
exit 0
