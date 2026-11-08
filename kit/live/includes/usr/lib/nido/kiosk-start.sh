#!/bin/sh
# Avvia lo schermo del NAS (utente nido-kiosk, da nido-kiosk.service): cage a tutto schermo con kiosk.py.
# La tastiera è quella scelta nell'installer (/etc/default/keyboard).
[ -f /etc/default/keyboard ] && . /etc/default/keyboard
export XKB_DEFAULT_LAYOUT="${XKBLAYOUT:-us}" XKB_DEFAULT_VARIANT="${XKBVARIANT:-}"
export XDG_SESSION_TYPE=wayland WLR_RENDERER=pixman GSK_RENDERER=cairo WEBKIT_DISABLE_COMPOSITING_MODE=1
# Il sandbox (bwrap) di WebKit non parte in tutti i sistemi e VM: qui si aprono solo pagine del NAS (127.0.0.1)
export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1
# Lingua dell'interfaccia di GTK (menu del tasto destro ecc.)
[ -f /etc/default/locale ] && . /etc/default/locale && export LANG
exec /usr/bin/cage -d -s -- /usr/bin/python3 /usr/lib/nido/kiosk.py
