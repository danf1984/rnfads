# RNFADS (prima RFD-NAS) — modifiche da fare (aggiornato il 1/11/2026, versione 1.0)

Regola: **niente prove in VM**. Si fa la build, la prova l'utente e riporta gli errori.
La ISO si consegna in **volumi 7-Zip da 350 MB** (`.7z.001`, `.7z.002`… → su Windows tasto destro sul `.001` → 7-Zip →
Estrai qui) con `SHA256SUMS.txt`. Da questa versione le modifiche si possono consegnare anche come **pacchetto .deb**
(pochi KB/MB) da caricare in Impostazioni → Aggiornamenti di sistema, senza reinstallare. Dettagli in SPEC.md §3.7 e §10.

## ISO 0.3-beta1 costruita il 31/10/2026 (08:28)
`rnfads-0.3-beta1-amd64.iso` (SHA256 `49188601…efabddf`), 5 volumi 7-Zip, pacchetto `rnfads_0.3~beta1+202610310717_all.deb`
non firmato. Build al primo colpo, controlli senza VM superati (STATO-FASE1B.md). **Senza chiave pubblica per le firme**: la ISO
accetta i pacchetti solo in modalità sviluppatore (vedi "Prima della build" qui sotto per aggiungerla).

## Prossima ISO (decisione dell'utente, 7/11/2026)
- ✅ **Tolta la scelta dello stile** (Originale / KDE Breeze) già nel kit: resta solo lo stile originale. `breeze.css` è
  conservato in `kit/strumenti/archivio/` ma non viene più caricato; chi aveva scelto Breeze nella 1.2.2 torna da solo
  all'originale (la scelta salvata nel browser viene ignorata). Restano i permessi "Sola lettura" / "Lettura e scrittura".
- ✅ ISO 1.2.3 costruita il 7/11/2026 (versione alzata a 1.2.3).

## Versione 1.2 (1/11/2026) — ISO 1.2 con tutto, da provare
- ✅ Schermo del NAS installato e attivo nella ISO; ✅ condivisioni di cartelle sul disco di sistema più semplici;
  ✅ reti Wi-Fi nascoste.
- ✅ **Servizi cloud dall'interfaccia** (Impostazioni → Servizi cloud): Google Drive, OneDrive, Dropbox, Box, MEGA, WebDAV,
  S3, B2, SFTP, FTP; cartella in File e destinazione dei backup. Da provare con account veri.
- ✅ **Rete** dall'interfaccia (DHCP/fisso, DNS, Wi-Fi, ritorno automatico dopo 3 minuti) e **Schermo del NAS** (interfaccia
  sul monitor del NAS con cage + WebKitGTK, componenti facoltativi). Da provare su PC vero o VM con VBoxSVGA.

## Versione 1.1 (1/11/2026) — nel kit, ISO unica da fare quando arrivano chiave e nome utente GitHub
- ✅ 14. **Lingua nell'installer** (it/en/es/de) + tastiera + fuso orario, applicati al sistema installato e all'interfaccia.
- ✅ 13 (resto). **Installer, console e notifiche tradotti** (`installer.tsv`, `issue.sh`, `nidopanel/i18n.py`).
- ✅ 8. **Aggiornamento online** (canale firmato su GitHub Pages, stabile/beta, avviso o installazione notturna, "Aggiorna ora",
  entità "update" in Home Assistant). Indirizzo facoltativo (`NIDO_UPDATE_URL` o Impostazioni): anche http:// in casa.
- ✅ 3. **Chiave pubblica** dell'utente in `kit/chiavi/aggiornamenti-pubblica.pem` (1/11/2026).
- ✅ **Fonti CasaOS, ZimaOS e Unraid** in un pacchetto a parte solo per l'utente (`make-extra-deb.sh`), non nella ISO.
- ✅ VMSVGA: console ferma sulla riga di avvio → `nomodeset` automatico solo con la scheda VMSVGA. ✅ Installer parte in inglese.
- ⬜ 12 (resto). Cloudflare Tunnel: lasciato fuori (Tailscale/ZeroTier bastano), solo se l'utente lo chiede.
- Poi: **una sola ISO 1.1** con tutto. **Pubblicazione su GitHub rimandata**: per ora l'utente tiene il sistema per sé
  (1/11/2026). Se un giorno pubblica: sorgenti e note legali accanto alla ISO (GPL), `fetch-sources.sh`.

## Versione 1.0.1 (1/11/2026) — ISO ricostruita, da provare
- ✅ Schermo nero VMSVGA corretto davvero (vedi SPEC.md §3.10).
- ✅ "Lingua non supportata" cambiando lingua.

## Versione 1.0 (1/11/2026) — ISO ricostruita, da provare
- ✅ 12. **Accesso da fuori casa**: Tailscale e ZeroTier da Impostazioni → Accesso remoto (installati su richiesta dagli
  archivi ufficiali). ⬜ Cloudflare Tunnel.
- ✅ **Fonte Runtipi** nello store (232 app convertite).
- Contiene tutto quello qui sotto (pacchetti del 31/10: VMSVGA, Riavvia/Spegni, Aggiorna tutto, lingue, Docker Hub, store).

## Pacchetto del 31/10/2026 sera (ISO da rifare quando tutto funziona) — da provare
- ✅ 5. **Schermata account Docker Hub** (Impostazioni → App store).
- ✅ 13. **Traduzioni** dell'interfaccia: inglese, spagnolo, tedesco; Impostazioni → Generale → Lingua (installer, console e
  notifiche restano in italiano).
- ✅ **Fonti CasaOS, ZimaOS e Unraid tolte** dallo store (restano Big Bear, LinuxServer, CoolStore, Docker Hub).
- ✅ **Marchio RNFADS**: verifica chiusa (TMview, WIPO, USPTO: nessun marchio).
- Più le aggiunte del pacchetto 1339 qui sotto (VMSVGA, Riavvia/Spegni, "Aggiorna tutto", 6 ore).

## Pacchetto 0.3~beta1+202610311339 (31/10/2026 pomeriggio) — da provare, ISO da rifare quando tutto funziona
- Correzione dello **schermo nero con la scheda VMSVGA** di VirtualBox (driver `vmwgfx` tolto).
- Pulsante **Riavvia / Spegni** nella barra in alto.
- App store: **"Aggiorna tutto"**; fonti aggiornate all'avvio e poi **ogni 6 ore** (predefinito).

## Fatto nel kit il 31/10/2026 (fase 1D) — nella ISO 0.3-beta1, da provare
1. ✅ **Aggiornamento con pacchetto locale** (.deb firmato, controllo della firma, snapshot, ritorno automatico se l'interfaccia
   non riparte, "Torna alla versione precedente", modalità sviluppatore). `kit/make-deb.sh` crea solo il pacchetto.
2. ✅ **Nome RNFADS** (`rnfads.local`, R F D in Orbitron, N A S in JetBrains Mono).
3. ✅ **Fonti dello store aggiornate in automatico** (all'avvio e ogni 6/12/24 ore/settimana/mai, "Aggiorna ora" per fonte).
4. ✅ **Consegna in volumi 7-Zip da 350 MB** fatta da `build.sh`.
6. ✅ **Notifiche** quando un'app si aggiorna o torna alla versione di prima.
7. ✅ **Pulizia delle immagini di riserva** delle app dopo 7 giorni.
9. ✅ **Più account dell'interfaccia con ruoli** (Amministratore / Utente).
11. ✅ **Procedura guidata al primo avvio** (si riapre da Impostazioni → Generale).

## Prima della build (l'utente)
- **Chiave per firmare gli aggiornamenti** (consigliata prima della build, una volta sola): sul tuo PC
  `kit/strumenti/crea-chiave.ps1` (Windows, serve openssl di Git for Windows) o `crea-chiave.sh` (Linux). Copia SOLO
  `aggiornamenti-pubblica.pem` in `kit/chiavi/`. La privata resta da te (fanne una copia di sicurezza).
  Senza chiave pubblica nella ISO i pacchetti si installano solo in modalità sviluppatore (la chiave si può aggiungere dopo
  con un pacchetto installato in modalità sviluppatore, oppure copiandola in `/etc/nido/update-keys/` via SSH).

## Cosa provare sulla ISO (0.3-beta1 → ora 1.0)
1. Primo accesso: si apre la **procedura guidata**; cambia il nome del NAS (poi `https://<nome>.local`), crea "Condivisa".
2. Impostazioni → Account: crea un account **Utente**, entra con quello (solo Home, App store, Impostazioni → Account).
3. Impostazioni → App store: frequenza "ogni 6 ore", "Aggiorna ora" su una fonte sola.
4. **Aggiornamento con pacchetto** (la ISO 0.3-beta1 non ha la chiave pubblica: o attivi la **modalità sviluppatore**, o prima
   copi `aggiornamenti-pubblica.pem` in `/etc/nido/update-keys/` via SSH): io ti mando un `.deb` nuovo (e tu lo firmi con `firma-pacchetto`), lo carichi con la firma,
   controlli versione e novità, installi; la pagina si ricarica con la versione nuova. Prova anche "Torna alla versione
   precedente" e un pacchetto modificato a mano (deve essere rifiutato).
5. Notifiche: attiva l'evento "App aggiornate, tornate indietro o spostate" e aggiorna un'app.
6. Le prove ancora aperte della 0.2: modifica dell'installazione di un'app, spostamento delle app su un altro disco,
   spegnimento brusco con il contatore di accensione, sensori nuovi in Home Assistant.

## NON fatto (resta da fare)
- 8. **Aggiornamento online**: archivio apt firmato (es. GitHub Pages), canali stabile/beta, notifica e sensore in Home
  Assistant quando c'è una versione nuova, installazione con "Aggiorna ora" o di notte. Il pacchetto `nido-nas` è già quello
  giusto: manca l'archivio e la pagina.
- 10. **Verifica in due passaggi** per l'accesso all'interfaccia.
- 12. Accesso da fuori casa: ✅ Tailscale e ZeroTier; ⬜ Cloudflare Tunnel.
- 13. Traduzioni: ✅ interfaccia; restano installer, console e notifiche.
- 14. **Scelta della lingua nell'installer** (serve una ISO nuova: l'installer non si aggiorna col pacchetto).
- ✅ Marchio RNFADS: verifica fatta (TMview, WIPO, USPTO: nessun marchio), considerata chiusa.
- **Link per le donazioni** (PayPal, Ko-fi…): li dà l'utente, vanno in `config.env`.
- Alla pubblicazione: sorgenti, elenco dei pacchetti e note legali accanto alla ISO (`fetch-sources.sh`).

## Provato dall'utente sulla ISO del 30/10 sera (31/10/2026)
- ✅ Docker Hub, ✅ file manager, ✅ fonte Unraid CA.
- ✅ Versione di Ubuntu: "Non ci sono versioni più nuove" è giusto (al 31/10 il `meta-release` ufficiale finisce con
  26.04.1 LTS: Ubuntu non ha ancora aperto il passaggio alla 26.10). Corretto il difetto "LTS LTS".
