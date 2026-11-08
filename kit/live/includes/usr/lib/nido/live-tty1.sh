#!/bin/bash
# Sistema live (chiavetta): apre l'installer sulla prima console.
# Per i test automatici accetta parametri dal menu di avvio:
#   nido.auto=1 nido.disk=/dev/sdX nido.user=NOME nido.password=PASSWORD [nido.hostname=NOME] [nido.lang=it|en|es|de] [nido.poweroff=1]
export TERM=linux
arg() { tr ' ' '\n' < /proc/cmdline | sed -n "s/^nido\.$1=//p" | tail -1; }

clear
if [ "$(arg auto)" = 1 ]; then
  NIDO_AUTO=1 NIDO_DISK=$(arg disk) NIDO_USER=$(arg user) NIDO_PASSWORD=$(arg password) \
    NIDO_NEW_HOSTNAME=$(arg hostname) NIDO_LANG=$(arg lang) /usr/local/sbin/nido-install
  rc=$?
  echo "NIDO-INSTALL-EXIT=$rc" | tee /dev/ttyS0 2>/dev/null
  if [ "$(arg poweroff)" = 1 ]; then sync; systemctl poweroff; fi
else
  /usr/local/sbin/nido-install
fi
echo
case "$(cat /run/nido-install-lang 2>/dev/null)" in
  en) echo "To reopen the installer type:  nido-install" ;;
  es) echo "Para volver a abrir el instalador escribe:  nido-install" ;;
  de) echo "Um das Installationsprogramm erneut zu öffnen, gib ein:  nido-install" ;;
  it) echo "Per riaprire l'installer scrivi:  nido-install" ;;
  *)  echo "To reopen the installer type:  nido-install" ;;
esac
echo
exec /sbin/agetty --autologin root --noclear tty1 linux
