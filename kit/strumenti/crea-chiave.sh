#!/bin/sh
# Crea la coppia di chiavi Ed25519 per firmare gli aggiornamenti (da fare UNA volta, sul tuo PC).
#   ./crea-chiave.sh [cartella]     (predefinita: ~/rnfads-chiavi)
# Tieni la chiave privata al sicuro (e fanne una copia): chi la possiede può firmare aggiornamenti.
set -e
DIR=${1:-$HOME/rnfads-chiavi}
mkdir -p "$DIR" && chmod 700 "$DIR"
[ -e "$DIR/aggiornamenti-privata.pem" ] && { echo "Esiste già $DIR/aggiornamenti-privata.pem: non la sovrascrivo."; exit 1; }
openssl genpkey -algorithm ed25519 -out "$DIR/aggiornamenti-privata.pem"
chmod 600 "$DIR/aggiornamenti-privata.pem"
openssl pkey -in "$DIR/aggiornamenti-privata.pem" -pubout -out "$DIR/aggiornamenti-pubblica.pem"
echo "Fatto."
echo "  Privata (resta qui, NON nel kit): $DIR/aggiornamenti-privata.pem"
echo "  Pubblica (copiala in kit/chiavi/): $DIR/aggiornamenti-pubblica.pem"
