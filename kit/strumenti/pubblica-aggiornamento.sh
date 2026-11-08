#!/bin/sh
# Pubblica un aggiornamento sul canale online (cartella del sito GitHub Pages).
#   ./pubblica-aggiornamento.sh <pacchetto.deb> <stable|beta> <cartella-del-sito> [chiave-privata.pem] [novita.txt]
# Crea/aggiorna nella cartella del sito:
#   pool/<pacchetto>.deb  pool/<pacchetto>.deb.sig  <canale>.json  <canale>.json.sig  index.html
# Poi nella cartella del sito: git add -A && git commit -m "RNFADS <versione>" && git push
set -e
DEB="$1"; CH="$2"; SITE="$3"; KEY=${4:-$HOME/rnfads-chiavi/aggiornamenti-privata.pem}; NOTES_FILE=${5:-}
[ -f "$DEB" ] && [ -n "$SITE" ] || { echo "Uso: $0 <pacchetto.deb> <stable|beta> <cartella-del-sito> [chiave.pem] [novita.txt]"; exit 2; }
case "$CH" in stable|beta) ;; *) echo "Canale: stable o beta"; exit 2 ;; esac
[ -f "$KEY" ] || { echo "Chiave privata non trovata: $KEY"; exit 2; }
NAME=$(basename "$DEB")
PV=$(printf '%s' "$NAME" | sed -n 's/^[a-z0-9-]*_\(.*\)_all\.deb$/\1/p')
[ -n "$PV" ] || { echo "Nome del pacchetto non riconosciuto: $NAME (atteso nome_versione_all.deb)"; exit 2; }
VER=$(printf '%s' "${PV%%+*}" | tr '~' '-')
mkdir -p "$SITE/pool"
cp "$DEB" "$SITE/pool/$NAME"
openssl pkeyutl -sign -inkey "$KEY" -rawin -in "$SITE/pool/$NAME" -out "$SITE/pool/$NAME.sig"
SHA=$(sha256sum "$SITE/pool/$NAME" | cut -d' ' -f1)
SIZE=$(wc -c < "$SITE/pool/$NAME" | tr -d ' ')
if [ -n "$NOTES_FILE" ]; then NOTES=$(cat "$NOTES_FILE"); else NOTES=$(dpkg-deb -f "$DEB" Description 2>/dev/null | tail -n +2 | sed 's/^ //; s/^\.$//' || true); fi
python3 - "$SITE/$CH.json" "$CH" "$VER" "$PV" "$NAME" "$SHA" "$SIZE" "$NOTES" <<'PY'
import json, sys, datetime
out, ch, ver, pv, deb, sha, size, notes = sys.argv[1:]
m = {"name": "RNFADS", "package": "nido-nas", "channel": ch, "version": ver, "package_version": pv,
     "deb": deb, "sha256": sha, "size": int(size), "notes": notes.strip(),
     "date": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
open(out, "w", encoding="utf-8", newline="\n").write(json.dumps(m, ensure_ascii=False, indent=1) + "\n")
PY
openssl pkeyutl -sign -inkey "$KEY" -rawin -in "$SITE/$CH.json" -out "$SITE/$CH.json.sig"
[ -f "$SITE/index.html" ] || printf '<!doctype html><meta charset="utf-8"><title>RNFADS updates</title><p>Canale degli aggiornamenti di RNFADS: <a href="stable.json">stable</a> · <a href="beta.json">beta</a></p>\n' > "$SITE/index.html"
touch "$SITE/.nojekyll"
echo "Pubblicato $VER ($PV) sul canale $CH in $SITE"
echo "Ora: cd \"$SITE\" && git add -A && git commit -m \"RNFADS $VER ($CH)\" && git push"
