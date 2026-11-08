# Novità di RNFADS

## 1.2.3 (ISO)
- ISO con tutto quello della 1.2 più: scelta della cartella con il mouse anche nella tabella avanzata delle app (1.2.1) e
  permessi delle condivisioni "Sola lettura" / "Lettura e scrittura" (1.2.2). Solo lo stile originale (la scelta dello
  stile della 1.2.2 non c'è). Le fonti CasaOS, ZimaOS e Unraid restano nel pacchetto a parte.

## 1.2.2
- Due stili per l'interfaccia (Impostazioni > Generale > Aspetto): "Originale" (predefinito) e "KDE Breeze", con barra
  laterale a gruppi e ricerca, colori Breeze, angoli squadrati e barra di stato in basso. Ognuno chiaro, scuro o automatico.
  La scelta vale per il browser in cui la fai.
- Condivisioni: i permessi si chiamano "Sola lettura" e "Lettura e scrittura" (prima "Lettura" e "Scrittura"), anche per NFS
  e nell'elenco delle condivisioni.

## 1.2.1
- Installazione e modifica delle app: nella tabella "Cartella del NAS" (modalità avanzata) c'è il pulsante con la cartella
  per scegliere il percorso navigando con il mouse, come nella modalità semplice. Se la cartella non esiste ancora, la
  scelta parte dalla prima cartella che c'è (es. /DATA/AppData); con "Nuova" la crei.

## 1.2
- Servizi cloud dall'interfaccia (Impostazioni > Servizi cloud), senza terminale: Google Drive, OneDrive, Dropbox e Box
  (accesso con il tuo account dal browser), MEGA, WebDAV/Nextcloud, S3 (Amazon, Wasabi, Cloudflare R2, MinIO…),
  Backblaze B2, SFTP e FTP.
- Ogni servizio si può mostrare come cartella in File (/media/cloud/<nome>, anche per le app e le condivisioni) e usare
  come destinazione dei backup. Prova del collegamento con lo spazio usato e libero.
- Rete (Impostazioni > Rete): indirizzo automatico o fisso, gateway, DNS e Wi-Fi. Dopo ogni modifica hai 3 minuti per
  confermare, altrimenti tornano da sole le impostazioni di prima.
- Schermo del NAS (Impostazioni > Schermo del NAS): l'interfaccia sul monitor collegato al NAS, con tastiera e mouse, per
  configurarlo anche senza rete; la pagina di accesso mostra gli indirizzi per gli altri dispositivi. Nella ISO 1.2 è già
  installato e attivo (serve una scheda video con driver); chi aggiorna con il pacchetto installa i componenti dall'interfaccia.
- Rete: anche le reti Wi-Fi nascoste.
- Condivisioni: scrivi il nome e la cartella sul disco di sistema (/DATA/<nome>) viene proposta e creata da sola.

## 1.1
- Installer in 4 lingue: il primo schermo fa scegliere italiano, inglese, spagnolo o tedesco; poi tastiera e fuso orario.
  Lingua, tastiera e fuso valgono anche per il sistema installato e per l'interfaccia web.
- Schermata della console (indirizzo dell'interfaccia) e notifiche (Telegram, ntfy, email, webhook) nella lingua del NAS.
- Aggiornamenti online: Impostazioni > Aggiornamenti di sistema > Aggiornamenti online. Canale stabile o beta, controllo ogni
  notte, avviso oppure installazione automatica di notte, pulsante "Aggiorna ora". Pacchetti e manifesti firmati.
- Installer in inglese all'avvio (poi la lingua scelta); menu della chiavetta in inglese.
- Scheda VMSVGA di VirtualBox/VMware: la console non resta più ferma sulla riga di avvio (nomodeset solo su queste VM).
- Pacchetti aggiuntivi "nido-extra-*" installabili da Impostazioni > Aggiornamenti di sistema.
- Chiave per le firme degli aggiornamenti inclusa: da questa versione i pacchetti firmati si installano senza modalità sviluppatore.
- Home Assistant: nuova entità "Sistema" (aggiornamento del NAS installabile da Home Assistant).

## 1.0.1
- Corretto davvero lo schermo nero con la scheda VMSVGA di VirtualBox/VMware: il driver vmwgfx è escluso anche nella
  riga di avvio di GRUB e nell'initramfs (nella 1.0 la regola non veniva letta all'avvio).
- Corretto: cambiando lingua in Impostazioni > Generale compariva "Lingua non supportata".

## 1.0
Prima versione stabile (prima: 0.3-beta1).
- Accesso da fuori casa: Tailscale e ZeroTier da Impostazioni > Accesso remoto (installati dagli archivi ufficiali).
- App store: nuova fonte Runtipi (oltre 230 app).
- Lingue: italiano, inglese, spagnolo e tedesco (Impostazioni > Generale > Lingua).
- App store: tolte le fonti CasaOS, ZimaOS e Unraid; restano Big Bear, LinuxServer, CoolStore e Docker Hub (più Runtipi dalla 1.0).
- Account Docker Hub in Impostazioni > App store (più download, controllo dei download rimasti).
- Pulsante di accensione nella barra in alto: Riavvia o Spegni il NAS da ogni pagina.
- App store: pulsante "Aggiorna tutto" (tutte le fonti); fonti aggiornate di base all'avvio e poi ogni 6 ore.
- Corretto: schermo nero dopo GRUB nelle VM VirtualBox/VMware con scheda VMSVGA (driver vmwgfx tolto).
- Nome nuovo: RNFADS (scritta R F D in Orbitron, N A S in JetBrains Mono).
- Aggiornamento del sistema con un pacchetto locale (.deb firmato): Impostazioni > Aggiornamenti di sistema.
- Catalogo delle app aggiornato all'avvio e ogni 6 ore (frequenza a scelta), "Aggiorna ora" per ogni fonte.
- Notifiche quando un'app si aggiorna o torna alla versione di prima; immagini di riserva tolte dopo 7 giorni.
- Più account dell'interfaccia con i ruoli Amministratore e Utente.
- Procedura guidata al primo avvio (nome, fuso orario, dischi, cartella condivisa, sicurezza).

## 0.2-beta1
- File manager completo, modifica dell'installazione delle app, app su un altro disco, contatore di accensione,
  passaggio alla versione nuova di Ubuntu.
