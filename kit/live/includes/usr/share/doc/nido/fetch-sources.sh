#!/bin/bash
# Scarica il codice sorgente di tutti i pacchetti inclusi nel sistema, nelle stesse
# versioni (obbligo della GPL per chi ridistribuisce la ISO).
# Uso: fetch-sources.sh <cartella-di-destinazione> [file-elenco]
# L'elenco ha una riga per pacchetto: "<pacchetto-sorgente> <versione>".
# Prima prova con apt-get source (servono le righe deb-src), poi scarica da Launchpad.
set -uo pipefail

DEST=${1:?Uso: fetch-sources.sh <cartella-di-destinazione> [file-elenco]}
LIST=${2:-/usr/share/doc/nido/sources.txt}
[ -r "$LIST" ] || { echo "Elenco non trovato: $LIST" >&2; exit 1; }
mkdir -p "$DEST"
cd "$DEST" || exit 1

ok=0; fail=0
: > MISSING.txt
while read -r src ver; do
  [ -n "$src" ] || continue
  case "$src" in \#*) continue ;; esac
  if apt-get source --download-only -q "$src=$ver" >/dev/null 2>&1; then
    ok=$((ok + 1)); continue
  fi
  # Launchpad conserva tutte le versioni pubblicate: il file .dsc e i file collegati
  base="https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/$src/$ver"
  vnoepoch=${ver#*:}
  dsc="${src}_${vnoepoch}.dsc"
  if curl -fsSL -o "$dsc" "$base/$dsc"; then
    for f in $(awk '/^Files:/{f=1;next} /^[A-Z]/{f=0} f{print $3}' "$dsc"); do
      curl -fsSL -o "$f" "$base/$f" || echo "$src $ver $f" >> MISSING.txt
    done
    ok=$((ok + 1))
  else
    echo "$src $ver" >> MISSING.txt
    fail=$((fail + 1))
  fi
done < "$LIST"

echo "Sorgenti scaricati: $ok pacchetti. Non trovati: $fail (vedi MISSING.txt)."
