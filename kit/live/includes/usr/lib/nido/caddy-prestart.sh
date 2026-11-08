#!/bin/bash
# Chiamato da caddy.service (ExecStartPre): se l'interfaccia del NAS tiene aperta la porta 80 di riserva
# (perché Caddy era fermo) le chiede di chiuderla e aspetta che sia libera. Non blocca mai Caddy.
busy() { ss -Hltn 'sport = :80' 2>/dev/null | grep -q .; }
busy || exit 0
systemctl is-active -q nido-ui || exit 0
systemctl kill -s USR1 --kill-whom=main nido-ui 2>/dev/null || exit 0
for _ in $(seq 1 30); do busy || exit 0; sleep 0.5; done
echo "la porta 80 è ancora occupata" >&2
exit 0
