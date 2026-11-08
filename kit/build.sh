#!/bin/bash
# =============================================================================
#  Genera la ISO installabile (base Ubuntu, avvio BIOS + UEFI + Secure Boot).
#  Va lanciato come root su Ubuntu o Debian a 64 bit.
#  Da Windows o da altre distro usa build-windows.ps1 / build-docker.sh,
#  che lo eseguono dentro un container Ubuntu.
# =============================================================================
set -euo pipefail

ROOT=${NIDO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}
WORK="${NIDO_WORK:-$ROOT/work}"
CACHE="${NIDO_CACHE:-$ROOT/.cache}"
OUT="$ROOT/out"
CHROOT="$WORK/rootfs"
ISO_DIR="$WORK/iso"

log()  { printf '\n\033[1;35m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*" >&2; }
die()  { printf '\033[1;31mERRORE: %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "va lanciato come root (sudo ./build.sh)"
[ -r /etc/debian_version ] || die "serve Ubuntu o Debian; da altri sistemi usa build-docker.sh o build-windows.ps1"
[ "$(dpkg --print-architecture)" = amd64 ] || die "serve un sistema amd64 (x86 a 64 bit)"

# --- Configurazione -------------------------------------------------------------
CONFIG_CLEAN=$(mktemp)
tr -d '\r' < "$ROOT/config.env" > "$CONFIG_CLEAN"
# shellcheck source=config.env
. "$CONFIG_CLEAN"
rm -f "$CONFIG_CLEAN"

[[ "$NIDO_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9\ ._-]{0,23}$ ]] \
  || die "NIDO_NAME non valido: usa lettere, numeri, spazi, . _ - (max 24 caratteri)"
[[ "$NIDO_VERSION" =~ ^[A-Za-z0-9._-]{1,20}$ ]] || die "NIDO_VERSION non valida"
[[ "$NIDO_HOSTNAME" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] || die "NIDO_HOSTNAME non valido"
[[ "$NIDO_ACCENT" =~ ^#[0-9a-fA-F]{6}$ ]] || die "NIDO_ACCENT deve essere nel formato #rrggbb"
[[ "${NIDO_WORDMARK:-}" =~ ^[A-Za-z0-9]*(\|[A-Za-z0-9]*){0,11}$ ]] || die "NIDO_WORDMARK non valido (es. \"R|N|F|A|D|S\")"

SLUG=$(printf '%s' "$NIDO_NAME" | tr 'A-Z ' 'a-z-' | tr -cd 'a-z0-9-')
ISO_VOLUME=$(printf '%s_%s' "$NIDO_NAME" "$NIDO_VERSION" | tr 'a-z .-' 'A-Z___' | tr -cd 'A-Z0-9_' | cut -c1-32)

# --- Strumenti di build ---------------------------------------------------------------
log "Installo gli strumenti di build"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq debootstrap squashfs-tools xorriso mtools dosfstools librsvg2-bin curl ca-certificates openssl >/dev/null
# 7-Zip per consegnare la ISO in volumi da 350 MB (facoltativo)
apt-get install -y -qq 7zip >/dev/null 2>&1 || apt-get install -y -qq p7zip-full >/dev/null 2>&1 || true
# debootstrap di sistemi più vecchi non conosce ancora le ultime versioni di Ubuntu
if [ ! -e "/usr/share/debootstrap/scripts/$UBUNTU_SUITE" ]; then
  ln -s gutsy "/usr/share/debootstrap/scripts/$UBUNTU_SUITE"
fi

# --- Pulizia di una build precedente interrotta ------------------------------------------
umount_chroot() {
  for m in var/cache/apt/archives dev/pts dev proc sys run; do
    if mountpoint -q "$CHROOT/$m" 2>/dev/null; then umount -l "$CHROOT/$m" || true; fi
  done
}
trap umount_chroot EXIT
umount_chroot
rm -rf "$CHROOT" "$ISO_DIR"
mkdir -p "$WORK" "$CACHE/debs" "$OUT"

# --- 1. Sistema di base ----------------------------------------------------------------------
log "Creo il sistema di base (Ubuntu $UBUNTU_SUITE)"
debootstrap --arch=amd64 --variant=minbase --components=main,restricted,universe,multiverse \
  --cache-dir="$CACHE/debs" "$UBUNTU_SUITE" "$CHROOT" "$UBUNTU_MIRROR" \
  || die "debootstrap non riuscito (controlla la connessione)"

mount --bind /dev "$CHROOT/dev"
mount --bind /dev/pts "$CHROOT/dev/pts"
mount -t proc proc "$CHROOT/proc"
mount -t sysfs sysfs "$CHROOT/sys"
mount -t tmpfs tmpfs "$CHROOT/run"
rm -f "$CHROOT/etc/resolv.conf"
cp -L /etc/resolv.conf "$CHROOT/etc/resolv.conf"

in_chroot() { chroot "$CHROOT" /usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  LANG=C.UTF-8 DEBIAN_FRONTEND=noninteractive "$@"; }

# Sorgenti dei pacchetti del sistema finale
rm -f "$CHROOT/etc/apt/sources.list"
cat > "$CHROOT/etc/apt/sources.list.d/ubuntu.sources" <<EOF
Types: deb
URIs: $UBUNTU_MIRROR
Suites: $UBUNTU_SUITE $UBUNTU_SUITE-updates $UBUNTU_SUITE-backports
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg

Types: deb
URIs: $UBUNTU_SECURITY
Suites: $UBUNTU_SUITE-security
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
EOF

# Durante la build nessun servizio deve partire davvero
printf '#!/bin/sh\nexit 101\n' > "$CHROOT/usr/sbin/policy-rc.d"
chmod +x "$CHROOT/usr/sbin/policy-rc.d"
# Niente pacchetti "consigliati" non richiesti: sistema più snello
echo 'APT::Install-Recommends "false";' > "$CHROOT/etc/apt/apt.conf.d/90nido-norecommends"
# Pacchetti scaricati riusati tra una build e l'altra
mkdir -p "$CHROOT/var/cache/apt/archives"
mount --bind "$CACHE/debs" "$CHROOT/var/cache/apt/archives"

log "Aggiorno il sistema di base"
in_chroot apt-get update -qq
in_chroot apt-get -y -qq full-upgrade >/dev/null

# --- 2. Pacchetti --------------------------------------------------------------------------------
read_list() { sed -e 's/#.*//' -e 's/[[:space:]]//g' "$1" | grep -v '^$' || true; }
mapfile -t REQUIRED < <(read_list "$ROOT/live/package-lists/nido.list")
OPTIONAL=()
while read -r p; do
  if in_chroot apt-cache show "$p" >/dev/null 2>&1; then OPTIONAL+=("$p"); else warn "pacchetto facoltativo non disponibile, salto: $p"; fi
done < <(read_list "$ROOT/live/package-lists/nido-optional.list")

MISSING=()
for p in "${REQUIRED[@]}"; do in_chroot apt-cache show "$p" >/dev/null 2>&1 || MISSING+=("$p"); done
[ ${#MISSING[@]} -eq 0 ] || die "pacchetti obbligatori non trovati: ${MISSING[*]}"

log "Installo ${#REQUIRED[@]} pacchetti obbligatori e ${#OPTIONAL[@]} facoltativi (la parte più lunga)"
if ! in_chroot apt-get install -y -q "${REQUIRED[@]}" "${OPTIONAL[@]}" > "$WORK/apt.log" 2>&1; then
  tail -20 "$WORK/apt.log"
  die "installazione dei pacchetti non riuscita (vedi $WORK/apt.log)"
fi
for p in "${REQUIRED[@]}"; do
  in_chroot dpkg -s "$p" >/dev/null 2>&1 || die "pacchetto non installato: $p (vedi $WORK/apt.log)"
done

# --- 3. File e configurazione del sistema ---------------------------------------------------------
log "Copio i file di $NIDO_NAME"
cp -a "$ROOT/live/includes/." "$CHROOT/"
# Toglie i fine riga di Windows dai file di testo copiati
( cd "$ROOT/live/includes" && find . -type f -print0 ) | while IFS= read -r -d '' f; do
  if grep -Iq . "$CHROOT/$f" 2>/dev/null; then sed -i 's/\r$//' "$CHROOT/$f"; fi
done
chmod +x "$CHROOT"/usr/local/sbin/* "$CHROOT"/usr/lib/nido/*.sh "$CHROOT"/etc/kernel/post*.d/*

# Pacchetto del NAS (nido-nas): lo stesso che si usa per aggiornare senza rifare la ISO.
# Installato con dpkg, così il NAS conosce la sua versione e si può aggiornare con un .deb nuovo.
log "Creo il pacchetto di aggiornamento"
NIDO_OUT="$OUT" NIDO_BUILD_STAMP="$(date -u +%Y%m%d%H%M)" "$ROOT/make-deb.sh"
DEBFILE=$(ls -t "$OUT/${SLUG}"_*_all.deb | head -1)
mkdir -p "$CHROOT/var/lib/nido/updates/installed"
cp "$DEBFILE" "$CHROOT/var/lib/nido/updates/installed/nido-nas_$(dpkg-deb -f "$DEBFILE" Version)_all.deb"

mkdir -p "$CHROOT/etc/nido" "$CHROOT/etc/default/grub.d"
cat > "$CHROOT/etc/nido/nido.conf" <<EOF
# Generato da build.sh — impostazioni di base del sistema.
NIDO_NAME="$NIDO_NAME"
NIDO_VERSION="$NIDO_VERSION"
NIDO_HOSTNAME="$NIDO_HOSTNAME"
NIDO_ACCENT="$NIDO_ACCENT"
NIDO_FONT="$NIDO_FONT"
NIDO_LOCALE="$NIDO_LOCALE"
NIDO_KEYMAP="$NIDO_KEYMAP"
NIDO_TIMEZONE="$NIDO_TIMEZONE"
NIDO_WORDMARK="${NIDO_WORDMARK:-}"
NIDO_PROJECT_URL="${NIDO_PROJECT_URL:-}"
NIDO_UPDATE_URL="${NIDO_UPDATE_URL:-}"
NIDO_DONATE_PAYPAL="${NIDO_DONATE_PAYPAL:-}"
NIDO_DONATE_KOFI="${NIDO_DONATE_KOFI:-}"
NIDO_DONATE_GITHUB="${NIDO_DONATE_GITHUB:-}"
NIDO_DONATE_LIBERAPAY="${NIDO_DONATE_LIBERAPAY:-}"
EOF
cat > "$CHROOT/etc/default/grub.d/10-nido.cfg" <<EOF
GRUB_DISTRIBUTOR="$NIDO_NAME"
GRUB_TIMEOUT=3
GRUB_TIMEOUT_STYLE=menu
GRUB_CMDLINE_LINUX_DEFAULT="quiet"
EOF
echo "$NIDO_HOSTNAME-live" > "$CHROOT/etc/hostname"

in_chroot dpkg -i "/var/lib/nido/updates/installed/$(ls "$CHROOT/var/lib/nido/updates/installed" | head -1)" >/dev/null \
  || die "installazione del pacchetto nido-nas non riuscita"

# --- 4. Configurazione dentro il sistema ------------------------------------------------------
log "Configuro il sistema"
for h in "$ROOT"/live/hooks/*.hook.chroot; do
  tr -d '\r' < "$h" > "$CHROOT/tmp/hook.sh"
  in_chroot bash /tmp/hook.sh
  rm -f "$CHROOT/tmp/hook.sh"
done

# Elenco dei pacchetti (con versioni) e dei pacchetti sorgente: serve per la GPL
log "Preparo l'elenco dei pacchetti e dei sorgenti"
in_chroot dpkg-query -W -f '${Package} ${Version} ${source:Package} ${source:Version}\n' \
  | sort > "$CHROOT/usr/share/doc/nido/packages.txt"
awk '{print $3, $4}' "$CHROOT/usr/share/doc/nido/packages.txt" | sort -u > "$CHROOT/usr/share/doc/nido/sources.txt"
echo "  $(wc -l < "$CHROOT/usr/share/doc/nido/packages.txt") pacchetti, $(wc -l < "$CHROOT/usr/share/doc/nido/sources.txt") pacchetti sorgente"

# --- 5. Pulizia ----------------------------------------------------------------------------------
log "Pulisco il sistema"
umount "$CHROOT/var/cache/apt/archives"
in_chroot apt-get clean
rm -f "$CHROOT/usr/sbin/policy-rc.d"
rm -rf "$CHROOT"/tmp/* "$CHROOT"/var/tmp/* "$CHROOT"/root/.bash_history
: > "$CHROOT/etc/machine-id"
rm -f "$CHROOT/var/lib/dbus/machine-id" "$CHROOT"/etc/ssh/ssh_host_*
# resolv.conf come in una installazione normale (systemd-resolved)
rm -f "$CHROOT/etc/resolv.conf"
ln -s ../run/systemd/resolve/stub-resolv.conf "$CHROOT/etc/resolv.conf"
find "$CHROOT/var/log" -type f -exec truncate -s 0 {} +

KVER=$(find "$CHROOT/boot" -maxdepth 1 -name 'vmlinuz-*' -printf '%f\n' | sed 's/^vmlinuz-//' | sort -V | tail -1)
[ -n "$KVER" ] || die "kernel non trovato"
[ -f "$CHROOT/boot/initrd.img-$KVER" ] || die "initrd non trovato per $KVER"

# --- 6. Avvio: GRUB per BIOS, shim + GRUB firmati per UEFI e Secure Boot -------------------------
log "Preparo l'avvio (BIOS, UEFI, Secure Boot)"
mkdir -p "$ISO_DIR/live" "$ISO_DIR/boot/grub/i386-pc" "$ISO_DIR/EFI/boot" "$ISO_DIR/EFI/ubuntu" "$ISO_DIR/.disk"
printf '%s %s (Ubuntu %s) amd64 %s\n' "$NIDO_NAME" "$NIDO_VERSION" "$UBUNTU_SUITE" "$(date +%Y%m%d)" > "$ISO_DIR/.disk/info"
cat > "$ISO_DIR/boot/grub/grub.cfg" <<EOF
set default=0
set timeout=5
set timeout_style=menu
set menu_color_normal=white/black
set menu_color_highlight=black/light-magenta
search --no-floppy --set=root --file /.disk/info

menuentry "Install $NIDO_NAME $NIDO_VERSION" {
  linux /live/vmlinuz boot=live components quiet loglevel=3 modprobe.blacklist=vmwgfx nomodeset
  initrd /live/initrd.img
}
menuentry "Install $NIDO_NAME (show boot messages)" {
  linux /live/vmlinuz boot=live components modprobe.blacklist=vmwgfx nomodeset
  initrd /live/initrd.img
}
menuentry "Install $NIDO_NAME (copy everything to RAM)" {
  linux /live/vmlinuz boot=live components toram quiet modprobe.blacklist=vmwgfx nomodeset
  initrd /live/initrd.img
}
EOF
# Il GRUB firmato cerca la configurazione anche qui
cp "$ISO_DIR/boot/grub/grub.cfg" "$ISO_DIR/EFI/ubuntu/grub.cfg"
# Note legali e sorgenti anche nella radice della ISO e accanto alla ISO in out/
mkdir -p "$ISO_DIR/licenze"
cp "$CHROOT"/usr/share/doc/nido/{THIRD_PARTY_NOTICES.txt,packages.txt,sources.txt,fetch-sources.sh} "$ISO_DIR/licenze/"
cp "$CHROOT"/usr/share/doc/nido/licenses/{Apache-2.0.txt,GPL-3.0.txt} "$ISO_DIR/licenze/"
for f in THIRD_PARTY_NOTICES.txt packages.txt sources.txt fetch-sources.sh; do
  cp "$CHROOT/usr/share/doc/nido/$f" "$OUT/${SLUG}-${NIDO_VERSION}-$f"
done

# BIOS: immagine El Torito di GRUB (creata con il GRUB del sistema appena costruito)
GRUB_PC="$CHROOT/usr/lib/grub/i386-pc"
cp "$GRUB_PC"/*.mod "$GRUB_PC"/*.lst "$ISO_DIR/boot/grub/i386-pc/"
in_chroot grub-mkimage -O i386-pc-eltorito -p /boot/grub -o /tmp/eltorito.img \
  biosdisk iso9660 part_msdos part_gpt search search_fs_file normal configfile linux echo test \
  all_video gfxterm font ls cat
mv "$CHROOT/tmp/eltorito.img" "$ISO_DIR/boot/grub/i386-pc/eltorito.img"
cp "$GRUB_PC/boot_hybrid.img" "$WORK/boot_hybrid.img"
umount_chroot

# UEFI: shim (firmato Microsoft) + GRUB (firmato Canonical)
# shimx64.efi.signed è un collegamento assoluto (alternatives): va risolto dentro il chroot
SHIM=""
for s in /usr/lib/shim/shimx64.efi.signed /usr/lib/shim/shimx64.efi.signed.latest; do
  t=$(chroot "$CHROOT" readlink -f "$s" 2>/dev/null || true)
  if [ -n "$t" ] && [ -f "$CHROOT$t" ]; then SHIM="$CHROOT$t"; break; fi
done
MM=$(ls "$CHROOT"/usr/lib/shim/mmx64.efi 2>/dev/null | head -1 || true)
GRUBEFI=$(ls "$CHROOT"/usr/lib/grub/x86_64-efi-signed/gcdx64.efi.signed 2>/dev/null | head -1 || true)
[ -n "$SHIM" ] && [ -n "$GRUBEFI" ] || die "shim o GRUB firmati non trovati"
cp "$SHIM" "$ISO_DIR/EFI/boot/bootx64.efi"
cp "$GRUBEFI" "$ISO_DIR/EFI/boot/grubx64.efi"
if [ -n "$MM" ]; then cp "$MM" "$ISO_DIR/EFI/boot/mmx64.efi"; fi

# Partizione EFI (FAT) incorporata nella ISO
EFI_IMG="$WORK/efi.img"
rm -f "$EFI_IMG"
mkfs.vfat -C -n NIDO_EFI "$EFI_IMG" 8192 >/dev/null
export MTOOLS_SKIP_CHECK=1
mmd -i "$EFI_IMG" ::/EFI ::/EFI/boot ::/EFI/ubuntu ::/boot ::/boot/grub ::/.disk
mcopy -i "$EFI_IMG" "$ISO_DIR"/EFI/boot/*.efi ::/EFI/boot/
mcopy -i "$EFI_IMG" "$ISO_DIR/boot/grub/grub.cfg" ::/EFI/ubuntu/grub.cfg
mcopy -i "$EFI_IMG" "$ISO_DIR/boot/grub/grub.cfg" ::/boot/grub/grub.cfg

# --- 7. Immagine del sistema (squashfs) ------------------------------------------------------
log "Comprimo il sistema (qualche minuto)"
cp "$CHROOT/boot/vmlinuz-$KVER" "$ISO_DIR/live/vmlinuz"
cp "$CHROOT/boot/initrd.img-$KVER" "$ISO_DIR/live/initrd.img"
mksquashfs "$CHROOT" "$ISO_DIR/live/filesystem.squashfs" -noappend -comp xz -b 1M -Xbcj x86 -quiet \
  -wildcards -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'tmp/*' 'boot/efi/*'

# --- 8. ISO ibrida (chiavetta USB o DVD, BIOS e UEFI) ------------------------------------------
log "Creo la ISO"
FINAL="$OUT/${SLUG}-${NIDO_VERSION}-amd64.iso"
rm -f "$FINAL"
xorriso -as mkisofs -r -V "$ISO_VOLUME" -o "$FINAL" \
  -J -joliet-long -l -iso-level 3 \
  -partition_offset 16 --grub2-mbr "$WORK/boot_hybrid.img" \
  -append_partition 2 0xef "$EFI_IMG" -appended_part_as_gpt \
  -c boot.catalog \
  -b boot/grub/i386-pc/eltorito.img -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
  -eltorito-alt-boot -e '--interval:appended_partition_2:all::' -no-emul-boot \
  "$ISO_DIR" > "$WORK/xorriso.log" 2>&1 || { tail -20 "$WORK/xorriso.log"; die "xorriso non riuscito"; }
[ -s "$FINAL" ] || die "la ISO non è stata creata"
(cd "$OUT" && sha256sum "$(basename "$FINAL")" > "$(basename "$FINAL").sha256")

log "Fatto: $FINAL ($(du -h "$FINAL" | cut -f1))"

# --- 9. Consegna: volumi 7-Zip da 350 MB + SHA256 --------------------------------------------------
SEVEN=$(command -v 7z || command -v 7zz || true)
if [ -n "$SEVEN" ] && [ "${NIDO_NO_7Z:-}" != 1 ]; then
  log "Preparo i volumi 7-Zip da 350 MB per la consegna"
  rm -f "$FINAL".7z.*
  "$SEVEN" a -t7z -mx=1 -v350m "$FINAL.7z" "$FINAL" >/dev/null
  (cd "$OUT" && sha256sum "$(basename "$FINAL")" "$(basename "$FINAL")".7z.* "$(basename "$DEBFILE")" > SHA256SUMS.txt)
  log "Volumi: $(ls "$FINAL".7z.* | wc -l) file $(basename "$FINAL").7z.001… (Windows: tasto destro sul .001 → 7-Zip → Estrai qui)"
fi
