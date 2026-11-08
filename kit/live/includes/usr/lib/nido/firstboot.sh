#!/bin/bash
# Primo avvio dopo l'installazione: prepara gli snapshot del sistema.
set -uo pipefail

mkdir -p /var/lib/nido
exec >>/var/log/nido-firstboot.log 2>&1
echo "=== primo avvio: $(date -Is)"

# --- Snapshot del sistema (Btrfs + snapper) -----------------------------------
# Lo snapshot riguarda solo il sottovolume di sistema (@): Docker (@docker),
# dati delle app (@appdata) e log (@log) restano fuori e non tornano indietro.
if [ "$(findmnt -no FSTYPE /)" = btrfs ] && command -v snapper >/dev/null 2>&1 \
   && [ ! -f /etc/snapper/configs/root ]; then
  echo "configuro snapper"
  # snapper vuole creare da sé /.snapshots: lo lasciamo fare e poi rimettiamo
  # al suo posto il sottovolume @snapshots montato da fstab.
  if mountpoint -q /.snapshots; then umount /.snapshots; fi
  rmdir /.snapshots 2>/dev/null || true
  if snapper --no-dbus -c root create-config /; then
    btrfs subvolume delete /.snapshots
    mkdir /.snapshots
    mount /.snapshots
    chmod 750 /.snapshots
    snapper --no-dbus -c root set-config \
      NUMBER_CLEANUP=yes NUMBER_LIMIT=10 NUMBER_LIMIT_IMPORTANT=5 \
      TIMELINE_CREATE=no TIMELINE_CLEANUP=yes
    snapper --no-dbus -c root create --description "Installazione iniziale" --userdata important=yes
  else
    echo "snapper: configurazione non riuscita"
    mkdir -p /.snapshots
    mount /.snapshots || true
  fi
fi

# Condivisioni: cartelle personali degli utenti, NFS spento finché non servono
PYTHONPATH=/usr/lib/nido/panel python3 -c 'from nidopanel import shares; shares.apply_all()' \
  || echo "condivisioni: configurazione iniziale non riuscita"

# HTTPS: certificato di casa per il nome e gli indirizzi definitivi, poi configurazione di Caddy
PYTHONPATH=/usr/lib/nido/panel python3 -m nidopanel.cli https-apply \
  || echo "https: configurazione iniziale non riuscita (resta HTTP)"

touch /var/lib/nido/firstboot.done
echo "=== primo avvio completato"
