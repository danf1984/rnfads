#!/bin/bash
# =============================================================================
#  Crea il pacchetto di aggiornamento del sistema (nido-nas) senza rifare la ISO.
#    ./make-deb.sh                          -> out/<nome>_<versione>_all.deb
#    NIDO_SIGN_KEY=/percorso/privata.pem ./make-deb.sh   -> anche la firma .deb.sig
#  Il pacchetto contiene tutto il codice del NAS (interfaccia, servizi nido-*, script,
#  note legali, chiavi pubbliche per le firme). Le impostazioni cambiate dall'interfaccia
#  non sono nel pacchetto: un aggiornamento non le tocca.
#  Si installa da Impostazioni → Aggiornamenti di sistema → Aggiornamento di <nome>.
#  Basta Linux con dpkg-deb (Ubuntu o Debian; da Windows usa WSL o build-docker.sh).
# =============================================================================
set -euo pipefail
ROOT=${NIDO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
OUT="${NIDO_OUT:-$ROOT/out}"
CONFIG_CLEAN=$(mktemp)
tr -d '\r' < "$ROOT/config.env" > "$CONFIG_CLEAN"
# shellcheck source=config.env
. "$CONFIG_CLEAN"
rm -f "$CONFIG_CLEAN"
command -v dpkg-deb >/dev/null || { echo "ERRORE: serve dpkg-deb (Ubuntu o Debian)" >&2; exit 1; }

SLUG=$(printf '%s' "$NIDO_NAME" | tr 'A-Z ' 'a-z-' | tr -cd 'a-z0-9-')
# Versione Debian: "0.3-beta1" diventa "0.3~beta1" (così la 0.3 finale viene dopo) e ogni build ha
# un numero più alto della precedente (data e ora), anche senza cambiare NIDO_VERSION.
STAMP=${NIDO_BUILD_STAMP:-$(date -u +%Y%m%d%H%M)}
DEBVER="$(printf '%s' "$NIDO_VERSION" | tr '-' '~')+$STAMP"
INC="$ROOT/live/includes"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

# --- file del pacchetto ---------------------------------------------------------------------------
copy() {   # copy <percorso relativo dentro includes> (file o cartella)
  local rel="$1"
  [ -e "$INC/$rel" ] || return 0
  mkdir -p "$STAGE/$(dirname "$rel")"
  cp -a "$INC/$rel" "$STAGE/$rel"
}
copy usr/lib/nido
copy usr/share/doc/nido
copy usr/share/nido
copy etc/tmpfiles.d/nido.conf
copy etc/apt/apt.conf.d/80nido-snapshot
copy etc/systemd/system/caddy.service.d/10-nido.conf
for f in "$INC"/usr/lib/modprobe.d/nido-*.conf "$INC"/etc/default/grub.d/1[5-9]-nido-*.cfg; do [ -e "$f" ] && copy "${f#$INC/}"; done
for f in "$INC"/usr/local/sbin/nido-* "$INC"/etc/systemd/system/nido-* "$INC"/etc/kernel/post*.d/zz-nido-*; do
  [ -e "$f" ] && copy "${f#$INC/}"
done
find "$STAGE" -name __pycache__ -prune -exec rm -rf {} +
# Fine riga di Windows
find "$STAGE" -type f -print0 | while IFS= read -r -d '' f; do
  if grep -Iq . "$f" 2>/dev/null; then sed -i 's/\r$//' "$f"; fi
done
chmod 755 "$STAGE"/usr/lib/nido/*.sh "$STAGE"/usr/local/sbin/* "$STAGE"/etc/kernel/post*.d/* 2>/dev/null || true

# Chiavi pubbliche per controllare le firme degli aggiornamenti (kit/chiavi/*.pem)
mkdir -p "$STAGE/usr/share/nido/update-keys"
if ls "$ROOT"/chiavi/*.pem >/dev/null 2>&1; then
  for k in "$ROOT"/chiavi/*.pem; do
    if grep -q "PRIVATE KEY" "$k"; then echo "ERRORE: $k è una chiave PRIVATA: non va nel kit!" >&2; exit 1; fi
    cp "$k" "$STAGE/usr/share/nido/update-keys/"
  done
fi

# Identità del sistema (nome, versione, scritta, link): il pacchetto la porta con sé e postinst
# la riscrive in /etc/nido/nido.conf. Il nome host scelto all'installazione non cambia.
cat > "$STAGE/usr/lib/nido/identity.conf" <<EOF
NIDO_NAME="$NIDO_NAME"
NIDO_VERSION="$NIDO_VERSION"
NIDO_WORDMARK="${NIDO_WORDMARK:-}"
NIDO_PROJECT_URL="${NIDO_PROJECT_URL:-}"
NIDO_UPDATE_URL="${NIDO_UPDATE_URL:-}"
NIDO_DONATE_PAYPAL="${NIDO_DONATE_PAYPAL:-}"
NIDO_DONATE_KOFI="${NIDO_DONATE_KOFI:-}"
NIDO_DONATE_GITHUB="${NIDO_DONATE_GITHUB:-}"
NIDO_DONATE_LIBERAPAY="${NIDO_DONATE_LIBERAPAY:-}"
EOF
echo "$DEBVER" > "$STAGE/usr/lib/nido/PACKAGE_VERSION"

# --- control e script -----------------------------------------------------------------------------
NOTES=""
if [ -f "$ROOT/NOVITA.md" ]; then
  # Prima sezione di NOVITA.md (fino alla seconda riga che inizia con "## ")
  NOTES=$(tr -d '\r' < "$ROOT/NOVITA.md" | awk 'BEGIN{n=0} /^## /{n++; if(n==2) exit} n>=1' | sed 's/^$/./; s/^/ /')
fi
mkdir -p "$STAGE/DEBIAN"
SIZE=$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)
cat > "$STAGE/DEBIAN/control" <<EOF
Package: nido-nas
Version: $DEBVER
Architecture: all
Maintainer: $NIDO_NAME <noreply@localhost>
Installed-Size: $SIZE
Section: admin
Priority: optional
Depends: python3 (>= 3.12), python3-yaml, python3-cryptography, python3-pil, rsync, zip, 7zip, ffmpegthumbnailer, caddy, docker-compose-v2 | docker-compose-plugin, smbclient, avahi-utils, rclone, fuse3, nfs-common, hdparm, xfsprogs, smartmontools
Description: $NIDO_NAME $NIDO_VERSION - interfaccia e servizi del NAS
${NOTES:- Interfaccia web, servizi e script di $NIDO_NAME.}
EOF
cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
# Dopo l'installazione o l'aggiornamento del pacchetto del NAS
set -e
[ "$1" = configure ] || exit 0
# Nome, versione e scritta del sistema dal pacchetto
if [ -f /usr/lib/nido/identity.conf ] && [ -f /etc/nido/nido.conf ]; then
  while IFS= read -r line; do
    key=${line%%=*}
    [ -n "$key" ] || continue
    if grep -q "^$key=" /etc/nido/nido.conf; then
      tmp=$(mktemp); grep -v "^$key=" /etc/nido/nido.conf > "$tmp"; echo "$line" >> "$tmp"
      cat "$tmp" > /etc/nido/nido.conf; rm -f "$tmp"
    else
      echo "$line" >> /etc/nido/nido.conf
    fi
  done < /usr/lib/nido/identity.conf
fi
find /usr/lib/nido/panel -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
mkdir -p /var/lib/nido/apps /var/lib/nido/catalog /var/lib/nido/updates/installed /var/log/nido
# La licenza GPL nella pagina "Informazioni e licenze"
[ -f /usr/share/common-licenses/GPL-3 ] && cp /usr/share/common-licenses/GPL-3 /usr/lib/nido/panel/ui/LICENSE.txt || true
# Sul sistema acceso (non durante la build della ISO): servizi nuovi abilitati e interfaccia riavviata
if [ -d /run/systemd/system ] && ! systemd-detect-virt --chroot >/dev/null 2>&1; then
  systemctl daemon-reload || true
  for u in nido-ui.service nido-standby.service nido-mdns.service nido-netmounts.service nido-uptime.service \
           nido-release-verify.service nido-monitor.timer nido-catalog.timer nido-apps-update.timer nido-selfupdate-check.timer; do
    [ -f "/etc/systemd/system/$u" ] && systemctl enable "$u" >/dev/null 2>&1 || true
  done
  systemd-tmpfiles --create /etc/tmpfiles.d/nido.conf >/dev/null 2>&1 || true
  [ -x /usr/lib/nido/rebrand.sh ] && /usr/lib/nido/rebrand.sh >/dev/null 2>&1 || true
  # Moduli del kernel (es. vmwgfx tolto) e riga di avvio: initramfs e GRUB rifatti solo se sono cambiati
  rm -f /etc/modprobe.d/nido-vmwgfx.conf        # la 0.3 lo metteva qui, dove l'initramfs non lo legge
  [ -x /usr/lib/nido/vm-video.sh ] && /usr/lib/nido/vm-video.sh || true   # nomodeset solo con la scheda VMSVGA
  sum=$(cat /usr/lib/modprobe.d/nido-*.conf /etc/default/grub.d/1[5-9]-nido-*.cfg 2>/dev/null | sha256sum | cut -d' ' -f1)
  if [ "$sum" != "$(cat /var/lib/nido/boot.sum 2>/dev/null)" ]; then
    ok=1
    if command -v update-initramfs >/dev/null 2>&1; then update-initramfs -u -k all >/dev/null 2>&1 || ok=0; fi
    if [ -e /boot/grub/grub.cfg ] && [ ! -d /run/live/medium ] && command -v update-grub >/dev/null 2>&1; then
      update-grub >/dev/null 2>&1 || ok=0
    fi
    [ "$ok" = 1 ] && echo "$sum" > /var/lib/nido/boot.sum || true
  fi
  systemctl try-restart nido-standby.service nido-mdns.service >/dev/null 2>&1 || true
  systemctl restart nido-ui.service || true
  systemctl restart nido-uptime.service >/dev/null 2>&1 || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

mkdir -p "$OUT"
DEB="$OUT/${SLUG}_${DEBVER}_all.deb"
rm -f "$OUT/${SLUG}"_*_all.deb "$OUT/${SLUG}"_*_all.deb.sig
dpkg-deb --root-owner-group -Zxz --build "$STAGE" "$DEB" >/dev/null
echo "Pacchetto: $DEB ($(du -h "$DEB" | cut -f1)), versione $DEBVER"

# --- firma (facoltativa) ---------------------------------------------------------------------------
if [ -n "${NIDO_SIGN_KEY:-}" ]; then
  [ -r "$NIDO_SIGN_KEY" ] || { echo "ERRORE: chiave privata non leggibile: $NIDO_SIGN_KEY" >&2; exit 1; }
  openssl pkeyutl -sign -inkey "$NIDO_SIGN_KEY" -rawin -in "$DEB" -out "$DEB.sig"
  echo "Firma: $DEB.sig"
else
  echo "Nessuna firma (NIDO_SIGN_KEY non impostata): il NAS lo installa solo in modalità sviluppatore."
fi
