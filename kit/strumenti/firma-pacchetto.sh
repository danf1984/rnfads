#!/bin/sh
# Firma un pacchetto di aggiornamento: crea <pacchetto>.deb.sig accanto al .deb.
#   ./firma-pacchetto.sh rnfads_0.3~beta1+202611011200_all.deb [chiave-privata.pem]
set -e
DEB="$1"; KEY=${2:-$HOME/rnfads-chiavi/aggiornamenti-privata.pem}
[ -f "$DEB" ] || { echo "Uso: $0 <pacchetto.deb> [chiave-privata.pem]"; exit 2; }
openssl pkeyutl -sign -inkey "$KEY" -rawin -in "$DEB" -out "$DEB.sig"
echo "Firma creata: $DEB.sig (carica sul NAS il .deb e il .sig insieme)"
