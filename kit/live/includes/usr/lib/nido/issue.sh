#!/bin/sh
# Scrive /etc/issue (schermata della console) e /etc/motd nella lingua del sistema.
# Uso: issue.sh [it|en|es|de]   (senza argomento: lingua da /etc/nido/ui-language.json)
set -u
. /etc/nido/nido.conf
L=${1:-}
if [ -z "$L" ] && [ -f /etc/nido/ui-language.json ]; then
  L=$(sed -n 's/.*"lang"[^"]*"\([a-z][a-z]\)".*/\1/p' /etc/nido/ui-language.json | head -1)
fi
case "$L" in
  en) OPEN="Open the interface from the browser of another device:"
      SEC="Secure connection: https://\\\\n.local (home certificate in Settings > Secure access)"
      BASED="based on Ubuntu."; WEB="Web interface: http://<host-name>.local or the IP address of the NAS"
      FORGOT="Forgot the interface password: sudo nido-ui-user <name>" ;;
  es) OPEN="Abre la interfaz desde el navegador de otro dispositivo:"
      SEC="Conexión segura: https://\\\\n.local (certificado de casa en Ajustes > Acceso seguro)"
      BASED="basado en Ubuntu."; WEB="Interfaz web: http://<nombre-host>.local o la dirección IP del NAS"
      FORGOT="¿Olvidaste la contraseña de la interfaz?: sudo nido-ui-user <nombre>" ;;
  de) OPEN="Öffne die Oberfläche im Browser eines anderen Geräts:"
      SEC="Sichere Verbindung: https://\\\\n.local (Heimzertifikat unter Einstellungen > Sicherer Zugriff)"
      BASED="basiert auf Ubuntu."; WEB="Weboberfläche: http://<hostname>.local oder die IP-Adresse des NAS"
      FORGOT="Passwort der Oberfläche vergessen: sudo nido-ui-user <name>" ;;
  *)  OPEN="Apri l'interfaccia dal browser di un altro dispositivo:"
      SEC="Connessione protetta: https://\\\\n.local (certificato di casa in Impostazioni > Accesso sicuro)"
      BASED="basato su Ubuntu."; WEB="Interfaccia web: http://<nome-host>.local oppure l'indirizzo IP del NAS"
      FORGOT="Password dell'interfaccia dimenticata: sudo nido-ui-user <nome>" ;;
esac
{
  printf '\n  \\e{bold}%s %s\\e{reset}\n\n' "$NIDO_NAME" "$NIDO_VERSION"
  printf '  %s\n     http://\\4\n     http://\\n.local\n' "$OPEN"
  printf '  %s\n\n' "$SEC" | sed 's/\\\\n/\\n/'
} > /etc/issue.new && mv /etc/issue.new /etc/issue
printf '\n  %s %s — %s\n  %s\n  %s\n\n' "$NIDO_NAME" "$NIDO_VERSION" "$BASED" "$WEB" "$FORGOT" > /etc/motd
exit 0
