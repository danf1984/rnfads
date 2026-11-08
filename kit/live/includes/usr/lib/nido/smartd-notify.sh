#!/bin/sh
# Chiamato da smartd quando un disco ha un problema: inoltra l'avviso ai canali configurati.
PYTHONPATH=/usr/lib/nido/panel exec /usr/bin/python3 -m nidopanel.cli notify \
  "Disco ${SMARTD_DEVICE:-?}: problema rilevato" "${SMARTD_MESSAGE:-Controlla la pagina Dischi.}" error disk_health
