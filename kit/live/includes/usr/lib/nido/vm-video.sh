#!/bin/sh
# Scheda video VMSVGA / VMware SVGA II (PCI 15ad:0405, VirtualBox e VMware): con il driver vmwgfx lo schermo
# resta nero, e anche senza (solo simpledrm) la console resta ferma sulla riga di avvio. Con "nomodeset" la
# console funziona (provato dall'utente). Solo su queste VM: sui PC veri nomodeset spegnerebbe i driver grafici
# (es. la transcodifica hardware Intel di Jellyfin/Plex).
# Scrive o toglie /etc/default/grub.d/16-nido-vmsvga.cfg. Non rifà GRUB: lo fa chi lo chiama.
F=/etc/default/grub.d/16-nido-vmsvga.cfg
found=0
for d in /sys/bus/pci/devices/*; do
  [ "$(cat "$d/vendor" 2>/dev/null)" = 0x15ad ] && [ "$(cat "$d/device" 2>/dev/null)" = 0x0405 ] && found=1
done
if [ "$found" = 1 ]; then
  mkdir -p /etc/default/grub.d
  cat > "$F" <<'EOT'
# RNFADS: scheda VMSVGA/VMware SVGA trovata (scritto da /usr/lib/nido/vm-video.sh): console con nomodeset
case " ${GRUB_CMDLINE_LINUX_DEFAULT} " in *" nomodeset "*) ;; *) GRUB_CMDLINE_LINUX_DEFAULT="${GRUB_CMDLINE_LINUX_DEFAULT} nomodeset" ;; esac
EOT
else
  rm -f "$F"
fi
exit 0
