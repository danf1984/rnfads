#!/bin/sh
# Rimette nome e versione del sistema dopo il passaggio a una versione nuova di Ubuntu
# (base-files riscrive os-release, lsb-release e issue). Stesse regole dell'hook della build:
# il nome resta "basato su Ubuntu", ID e DISTRIB_ID non cambiano.
set -u
. /etc/nido/nido.conf
if [ -e /usr/lib/os-release.base ]; then
  BASE=$(. /usr/lib/os-release.base && echo "${NAME:-Linux} ${VERSION_ID:-}")
  {
    grep -vE '^(NAME|PRETTY_NAME|HOME_URL|SUPPORT_URL|BUG_REPORT_URL|PRIVACY_POLICY_URL|LOGO)=' /usr/lib/os-release.base
    echo "NAME=\"$NIDO_NAME\""
    echo "PRETTY_NAME=\"$NIDO_NAME $NIDO_VERSION ($BASE)\""
  } > /usr/lib/os-release.new && mv /usr/lib/os-release.new /usr/lib/os-release
  ln -sf ../usr/lib/os-release /etc/os-release
  BASE_DESC=$(. /usr/lib/os-release.base && echo "${PRETTY_NAME:-Ubuntu}")
else
  BASE_DESC=$(. /etc/lsb-release && echo "${DISTRIB_DESCRIPTION:-Ubuntu}" | sed 's/^.*(basato su \(.*\))$/\1/')
fi
if [ -f /etc/lsb-release ]; then
  sed -i "s|^DISTRIB_DESCRIPTION=.*|DISTRIB_DESCRIPTION=\"$NIDO_NAME $NIDO_VERSION (basato su $BASE_DESC)\"|" /etc/lsb-release
fi
printf '%s %s\n' "$NIDO_NAME" "$NIDO_VERSION" > /etc/issue.net
# Schermata della console e motd nella lingua del sistema (base-files li riscrive)
[ -x /usr/lib/nido/issue.sh ] && /usr/lib/nido/issue.sh
# Messaggi di benvenuto di Ubuntu e loghi
for m in 10-help-text 50-motd-news; do [ -f "/etc/update-motd.d/$m" ] && chmod -x "/etc/update-motd.d/$m"; done
[ -f /etc/default/motd-news ] && sed -i 's/^ENABLED=.*/ENABLED=0/' /etc/default/motd-news
rm -f /usr/share/pixmaps/ubuntu-logo* /usr/share/plymouth/ubuntu-logo* /usr/share/plymouth/themes/spinner/watermark.png
# L'hook di snapper di Ubuntu resta messo da parte (gli snapshot di apt li fa snapshot-apt.sh)
if [ -e /etc/apt/apt.conf.d/80snapper ] && ! dpkg-divert --list /etc/apt/apt.conf.d/80snapper | grep -q nido; then
  mkdir -p /usr/share/nido
  dpkg-divert --local --rename --divert /usr/share/nido/80snapper.ubuntu --add /etc/apt/apt.conf.d/80snapper >/dev/null
fi
# GRUB con il nome del sistema
command -v update-grub >/dev/null && update-grub >/dev/null 2>&1 || true
exit 0
