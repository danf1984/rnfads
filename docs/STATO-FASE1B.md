# RFD-NAS (prima CaveNAS) — stato della fase 1B (1B-1: 28–29/10/2026, 1B-2: dal 30/10/2026)

Tappa 1 (Dischi) **finita**: backend e pagina provati dal browser (29/10/2026).

## Fatto e provato (chroot Ubuntu 26.04, dischi finti loop)
- `disks.py` riscritto:
  - dischi montati in `/media/<nome>` (prima finivano in `/DATA/<nome>` e il file manager non li vedeva: era un errore della 1A);
  - montaggio con nome, sola lettura, "monta a ogni avvio" (fstab) e condivisione facoltativa;
    per NTFS: ntfsfix se Windows l'ha chiuso male, poi l'altro driver (ntfs3 → ntfs-3g), messaggio chiaro
    per l'ibernazione ("avvio rapido");
  - formattazione in ext4, Btrfs, exFAT, NTFS, FAT32 e **XFS**, come operazione lunga con avanzamento;
    conferma scritta obbligatoria anche dal server; il disco di sistema rifiutato;
  - SMART più completo (vita residua degli SSD, ore, accensioni, settori difettosi, ultimo test,
    attributi, test breve/completo); non sveglia i dischi in standby;
  - tipo ed etichetta letti con blkid quando udev è in ritardo;
  - prove: `NIDO_TEST_LOOP=1` mostra solo i dischi loop e il disco di sistema (mai i dischi veri).
  - Provati: NTFS, exFAT, ext4 in sola lettura e Btrfs montati e smontati; formattazione di ext4, XFS,
    Btrfs, NTFS ed exFAT riuscita. FAT32 viene creato, ma questo kernel di prova non lo sa montare: da provare in VM.
- `standby.py` + servizio `nido-standby` (nuovo): standby per disco (Mai, 5…240 min, personalizzato), APM,
  eccezione oraria per i backup, "spegni adesso", conteggio delle accensioni. Prende il posto di hdparm -S/hd-idle.
  Provato: spegnimento dopo il tempo scelto, riaccensione rilevata e contata, "spegni adesso".
  Corretto un errore: la lettura dell'elenco dei dischi (blkid) faceva attività e impediva lo standby.
- Pagina **Dischi** (`ui/disks.js`): schede dei dischi con partizioni, salute SMART, menu delle azioni;
  formattazione (6 formati, conferma scritta, avanzamento), montaggio (nome, sola lettura, a ogni avvio,
  condivisione), standby per disco (tempi, personalizzato, orario dei backup, APM, spegni adesso),
  dettagli SMART con test breve e completo, spazio delle app (Docker) con pulizia delle immagini.
- `server.py`: tolte le rotte `/nido/` e il Centro di controllo; tutte le sue funzioni sono sotto `/api/`
  (sistema, dischi, Docker, condivisioni, utenti, backup, aggiornamenti, snapshot, notifiche, chiave API).
- `updates.py` riscritto: elenco diviso in sicurezza / CaveNAS / sistema, snapshot prima e dopo,
  registro in diretta (`/api/updates/log`), impostazioni automatiche (ricerca, sicurezza, riavvio di notte).
- `util.start_job`: funziona anche senza systemd (ambiente di prova).
- Condivisioni: opzione "tutti gli utenti" (lettura o lettura e scrittura).
- xterm.js 5.5.0 e addon-fit 0.10.0 (MIT) già copiati in `ui/vendor/xterm/` con le licenze.
- Tolto `theme.py` (tema di CasaOS, non più usato).

- Tappa 2 **finita** (29/10/2026): pagine **Condivisioni** (Samba, NFS, DLNA, cartelle personali, accesso per
  utente o per tutti), **Utenti** (crea, password, amministratore, elimina), **Backup** (nuovo/modifica, esegui,
  registro in diretta, versioni e ripristino, chiave), e in Impostazioni **Generale** (informazioni, riavvia,
  spegni), **Notifiche** (ntfy, Telegram, email, webhook, eventi e soglie, prova), **Aggiornamenti di sistema**
  ("Cerca aggiornamenti", "Aggiorna ora", elenco diviso, registro in diretta, automatico, avviso di riavvio,
  snapshot), **Home Assistant e API** (package per /config/packages/ con !secret). Cartella `www/` e rotte
  `/nido/` tolte. Provati dal browser: utente creato, cartella condivisa (smb.conf giusto), backup eseguito e
  ripristinato, notifica webhook ricevuta, 22 aggiornamenti cercati e installati con il registro in diretta.

- Tappa 3 **finita** (29/10/2026): **Terminale** con xterm.js 5.5.0 incluso (caricato solo quando serve),
  più schede (come l'utente amministratore con lo stesso nome dell'account, come root, dentro ogni app accesa
  con docker exec), schede che restano aperte cambiando pagina, copia/incolla, dimensione del testo, tasti
  speciali per il telefono. WebSocket scritto nel server (nessuna libreria), solo amministratori e solo dalla
  stessa origine. **Accesso SSH**: acceso/spento, password sì/no, solo dalla rete di casa, porta, chiavi
  autorizzate per gli amministratori (file in `sshd_config.d/10-nido.conf`, controllato con `sshd -t`).
  Provati: comandi nel terminale, Ctrl+C, shell dentro un contenitore, accesso SSH vero con la chiave e
  password rifiutata, origine estranea rifiutata (403), senza accesso (401).

- Tappa 4 **finita** (29/10/2026): **HTTPS con Caddy** (2.6.2 di Ubuntu). L'interfaccia ascolta su
  127.0.0.1:8090, Caddy sulle porte 80 e 443. Certificato di casa creato dal NAS (CA "CaveNAS - certificato di
  casa", 10 anni; certificato del NAS 800 giorni per nome, nome.local, *.nome.local e IP; si rinnova da solo
  se scade o cambia l'IP), scaricabile anche in HTTP da `/certificato-casa.crt`; Let's Encrypt con dominio ed
  email; certificato caricato (controllo che chiave e certificato vadano insieme); reindirizzamento da HTTP;
  sottodomini per le app (jellyfin.cavenas.local) pubblicati con mDNS dal servizio nuovo `nido-mdns`.
  Se Caddy non parte, l'interfaccia apre da sola la porta 80 di riserva. Provati: HTTPS con la CA di casa
  riconosciuta, 308 da HTTP, cookie Secure, terminale via wss attraverso Caddy, sottodominio di un'app (200),
  configurazioni Let's Encrypt, caricato e "solo HTTP" validate da Caddy, chiave sbagliata rifiutata, porta di
  riserva aperta e chiusa. Let's Encrypt vero: da provare con un dominio e le porte aperte.
- Kit: pacchetti `caddy`, `hdparm`, `xfsprogs`; servizi `nido-standby`, `nido-mdns`, `caddy` abilitati (spenti
  nel sistema live); Caddyfile iniziale in HTTP; il primo avvio crea il certificato e attiva l'HTTPS.

- Tappa 5 **finita** (29/10/2026): nome e logo controllati ovunque (favicon identica al logo, scritta "cave"+"nas"
  dal parametro `NIDO_WORDMARK`; tolte le ultime scritte "NidoNAS" nelle intestazioni HTTP e negli User-Agent, ora
  prese da `NIDO_NAME`); note legali con xterm.js e Caddy; pagina "Informazioni e licenze"; `kit/README.md`; SPEC.md
  aggiornata (§3.3, §4, §7.2, §8.3, §9). Controllo finale: tutte le pagine senza errori JavaScript, tema chiaro e
  scuro, telefono a 390 px senza scorrimento orizzontale. Schermate nuove in `schermate/1B/`.

## Prossimi passi
Vedi SPEC.md §9: build della ISO e prove in VM (con le verifiche della 1B-1 che il chroot non permette), poi
verifica in due passaggi, procedura guidata al primo avvio, accesso da fuori casa.

## Errori trovati in SPEC.md (corretti alla tappa 5)
- §1: "CaveNAS (usato nella fase 1A) → CaveNAS" deve dire "KuboraNas (usato nella fase 1A) → CaveNAS".
- §3.2: `NIDO_WORDMARK="cavenas|nas"` deve essere `"cave|nas"` (il kit è già giusto).

## Fase 1B-2 (dal 30/10/2026)

- Tappa 1 **finita** (30/10/2026), provata nel chroot Ubuntu 26.04 con dischi loop:
  - **Nome RFD-NAS** (`NIDO_NAME="RFD-NAS"`, `NIDO_HOSTNAME="rfd-nas"`, `NIDO_WORDMARK="rfd|nas"`): config.env, README,
    prototipo, colori.txt, messaggio di build.sh, foglio del logo rifatto (`logo/rfdnas-logo.png`, simbolo invariato),
    `logo/logo-cavenas.svg` rinominato `logo-rfdnas.svg`; storia del nome in SPEC.md §1.
  - **Standby con programma settimanale** (Dischi → Programma settimanale): fasce "Standby" (i dischi si spengono dopo
    N minuti senza attività anche se il loro tempo è "Mai") e "Sempre accesi"; giorni L–D, orari anche oltre la mezzanotte,
    stessa ora = tutto il giorno, "sempre accesi" vince sulle sovrapposizioni, l'orario dei backup resta valido; per ogni
    disco "Segue il programma settimanale". API `POST /api/disks/standby-schedule`. Provato: dischi in standby con tempo
    "Mai" in una fascia di standby; disco letto in una fascia "sempre accesi" resta acceso (accensione contata).
  - **Spegnimento e accensione programmati** (Impostazioni → Generale, `nidopanel/powersched.py`, servizio
    `nido-poweroff` + timer scritto dall'interfaccia con `Persistent=false`): giorni e ora di spegnimento, giorni e ora di
    accensione con `rtcwake` (impostata a ogni spegnimento, anche da "Spegni"), prova della sveglia del PC, avviso se il
    PC non ha la sveglia o se non viene accettata; prima di spegnere aspetta backup (restic/rclone, job di backup),
    aggiornamenti (job, apt, dpkg, unattended-upgrade, aggiornamento delle app) e altre operazioni lunghe fino a un
    massimo scelto, poi salta lo spegnimento; notifica (evento nuovo "Spegnimento programmato"). Provato in prova
    (`power-scheduled --dry-run`): attesa di un backup finto finché non è finito.
- Tappa 2 **finita** (30/10/2026): **build della ISO** su Ubuntu 26.04 (chroot `debootstrap resolute`) riuscita al primo
  colpo (1,7 GB, ~16 min con 2 CPU). **VM BIOS** (QEMU TCG): live avviato, installazione interattiva completa (~10 min),
  sistema installato `running`, nessuna unità fallita, account dell'interfaccia creato dall'installer, HTTPS attivo dopo
  il primo avvio (Caddy con certificato di casa), 21 pagine senza errori JavaScript. Prove: NTFS montato (ntfs3), FAT32
  formattato e montato, SMART da un disco SATA virtuale, standby con `hdparm -y` (anche dal programma settimanale),
  risveglio contato, fascia "sempre accesi"; cartella **SMB** (Samba sull'host) e **NFS** (NFSv4, Ganesha sull'host)
  montate davvero, lette e scritte, **ricollegate dopo il riavvio** prima di Docker; sveglia del PC (RTC) accettata.
  - Errore trovato e corretto: all'avvio systemd aspettava i dischi dei dati solo 10 s (`x-systemd.device-timeout=10s`)
    e, se arrivavano dopo, restavano smontati. Ora 90 s e in più `nido-netmounts` (prima di Docker) monta i dischi
    "a ogni avvio" rimasti indietro e aggiorna le righe vecchie di fstab.
  - Installer: messaggi aggiornati (l'account web è creato dall'installer con password ≥ 8 caratteri), descrizione del
    disco senza spazio vuoto quando manca il modello.
  - Interfaccia: formato del disco di sistema (mostrava FAT32 della partizione EFI invece di Btrfs), riga del programma
    settimanale allineata.
- Tappa 3 **finita** (30/10/2026), sempre sulla VM BIOS:
  - **Snapshot prima e dopo un aggiornamento** dall'interfaccia (3 pacchetti di sicurezza installati con il registro in
    diretta). Errore corretto: comparivano anche gli snapshot doppi "apt" dell'hook di Ubuntu (`80snapper`), che non
    conosce `NIDO_NO_APT_SNAPSHOT`; ora l'hook di Ubuntu è messo da parte con `dpkg-divert` (hook della build) e gli
    snapshot di apt li fa solo `snapshot-apt.sh` ("prima di apt"/"dopo apt" quando apt è usato a mano).
  - **Porta di riserva**: Caddy fermo → l'interfaccia apre la porta 80 in 30 s. Errore corretto: quando Caddy ripartiva
    trovava la porta occupata e falliva. Ora `caddy.service.d/10-nido.conf` (ExecStartPre come root,
    `/usr/lib/nido/caddy-prestart.sh`) chiede all'interfaccia (SIGUSR1) di liberarla e Caddy riparte.
  - **mDNS**: errore corretto: `rfd-nas.local` veniva annunciato anche sulla rete di Docker (risolto in 172.17.0.1).
    Ora `nido-mdns` limita avahi alle schede di rete vere (`allow-interfaces`, aggiornato da solo se cambiano).
    `webdemo.rfd-nas.local` (app di prova installata in modalità Compose) pubblicato da nido-mdns e servito in HTTPS.
  - **Catalogo vero**: Big Bear scaricato da GitHub (492 app); CasaOS, LinuxServer e CoolStore e Docker Hub non
    raggiungibili da questo ambiente (vedi SPEC.md §8.4).
  - **Spegnimento programmato vero**: con un backup in corso ha mandato la notifica "in attesa", ha aspettato 2 minuti,
    poi notifica "si spegne adesso… si riaccende da solo domani alle 07:30" (sveglia RTC accettata) e la VM si è spenta.

## Fermato dall'utente il 30/10/2026 alle 11:58 ("fermati") — punto stabile: tappa 3
- **Fatto e provato**: punti 1–3 della richiesta (nome RFD-NAS, standby programmato, spegnimento/accensione programmati),
  build della ISO, prove complete in VM **BIOS** (vedi tappe 2 e 3 e SPEC.md §8.4).
- **Da fare quando si riprende**:
  1. Ricostruire la ISO con le correzioni delle tappe 2–3 (la ricostruzione era in corso: la ISO della prima build non
     contiene queste correzioni ed è stata sostituita; il kit in questo zip è quello aggiornato).
  2. Prova in **UEFI + Secure Boot** con la ISO nuova: avvio del live, installazione, avvio del disco installato, nessuna
     unità fallita, HTTPS, tutte le pagine senza errori JS; ricontrollo veloce delle correzioni (dpkg-divert di
     80snapper, caddy-prestart, allow-interfaces di avahi, rimontaggio dei dischi all'avvio).
  3. Consegna della ISO in parti da 350 MB con SHA256 e istruzioni per unirle, poche schermate della VM UEFI.
  4. Le prove che servono internet vero (Docker Hub, CasaOS/LinuxServer/CoolStore, app vera) restano per il tuo PC:
     SPEC.md §8.5.

- Tappa 4 **finita** (30/10/2026, ripresa alle 14:36): ISO ricostruita con le correzioni delle tappe 2–3
  (SHA256 `f53ac9e8e20e504cd42baffc0bd5d98c622d0dbf28981a21cf6a4f892273cf76`), consegnata in 5 parti da 350 MB.
  Prova **UEFI + Secure Boot**: live, installazione, avvio con Secure Boot attivo, `running`, nessuna unità fallita, account
  dall'installer, HTTPS, 21 pagine senza errori JS, correzioni presenti. **Fase 1B-2 finita.** Restano le prove con
  internet vero sul PC dell'utente (SPEC.md §8.5) e i punti 7–9 di SPEC.md §9.
  Nota build: se una build viene interrotta, prima di rilanciarla smontare `work/rootfs/{dev/pts,dev,proc,sys,run}`
  (con i bind rimasti montati la ricostruzione fallisce con "Is /dev/pts mounted?").

## Fase 1C (dal 30/10/2026, sera) — regola: niente prove in VM, la ISO la prova l'utente

- Tappa 1 **finita** (30/10/2026): errori.
  - **Home sulla rotellina**: `/api/home` aspettava in fila `docker ps` + `docker inspect` + `docker info` (fino a ~65 s con Docker
    in avvio o una macchina lenta) e ricalcolava la dimensione di tutto il cestino a ogni richiesta. Ora app e dischi arrivano da
    una cache aggiornata in un thread (la Home aspetta al massimo 2,5 s e poi si completa da sola), la dimensione del cestino è
    salvata quando si elimina. Nel browser: tempo massimo per ogni richiesta (45 s GET, 3 min il resto) e un errore della pagina
    mostra "Riprova" invece della rotellina infinita.
  - **Store Unraid**: lasciato stare su richiesta dell'utente. Restano due migliorie innocue già fatte: scaricamento compresso
    (gzip, il feed passa da 20 a 3,7 MB) con 3 tentativi e indirizzo di riserva, e una fonte attivata mentre il catalogo si sta
    già aggiornando non viene più ignorata (prima restava "non ancora scaricata").
- Tappa 2 **finita** (30/10/2026): **file manager** (punti 3–15 di DA-FARE), provato nel chroot 26.04 (API con curl, pagina con
  Playwright, nessun errore JavaScript). Dettagli in SPEC.md §4 punto 4.
- Tappa 3 **finita** (30/10/2026): punti 16–19, provati nel chroot dove possibile (Docker, systemd e do-release-upgrade non
  ci sono: quelle parti si provano sulla ISO).
  - **Modifica l'installazione** (Le mie app → ⋯): stessa finestra dell'installazione già compilata (`GET /api/apps/<nome>/edit`),
    `POST /api/apps/<nome>/reconfigure`: controllo delle porte, copia della configurazione in `versions/`, compose controllato
    prima di toccare i contenitori, `docker compose up -d`, controllo della salute e ritorno da solo alla configurazione di prima.
  - **Sposta le app su un altro disco** (Dischi → Dove stanno le app, `appmove.py`): copia con rsync e secondo passaggio di
    controllo, poi bind in fstab sugli stessi percorsi (`/var/lib/docker`, `/DATA/AppData`, e `/var/lib/containerd` se Docker
    tiene lì le immagini); drop-in `RequiresMountsFor` per Docker; ritorno automatico se le app non ripartono; "Riporta sul
    disco di sistema" e "Libera lo spazio". Provata nel chroot la riscrittura di fstab e il ritorno (file identico).
  - **Contatore del tempo di accensione** (`uptime.py`, servizio `nido-uptime` che segna lo spegnimento regolare): Home con
    "Acceso da" dal vivo, ore totali, avvii, ultimo spegnimento regolare/improvviso; in Home Assistant 4 sensori nuovi.
  - **Passa alla versione nuova di Ubuntu** (`release.py`, `rebrand.sh`, servizio `nido-release-verify`): vedi SPEC.md §4 punto 7.
- Tappa 4 **finita** (31/10/2026, 00:02): **build della ISO** con `build.sh` nel chroot Ubuntu 26.04 riuscita al primo colpo
  (nessun errore di build da correggere; soliti avvisi innocui degli attributi ACL di mksquashfs), ~15 minuti con 2 CPU,
  `rfd-nas-0.2-beta1-amd64.iso` 1,7 GB, SHA256 `3e317c224ada301eeeb9220ab77394934a869cfbc6e2cdc76e9d9e671170461c`,
  consegnata in 5 parti da 350 MB con `SHA256SUMS.txt` e `UNIRE-LE-PARTI.txt`. Controlli senza VM: avvio BIOS e UEFI presenti
  (El Torito), file e servizi nuovi dentro il sistema compresso, pacchetti nuovi installati, tutto il codice Python compilato
  e importato con il Python 3.14.4 della ISO. **La prova in VM/PC la fa l'utente** (elenco in DA-FARE.md).
  Nota build: lanciare `build.sh` una sola volta per cartella; due build insieme nella stessa cartella si cancellano a vicenda.

## 31/10/2026 — prove dell'utente e nome nuovo
- L'utente ha provato la ISO del 30/10 sera: Docker Hub, file manager e Unraid CA funzionano. Il controllo della versione di
  Ubuntu dice correttamente che non ci sono versioni nuove (la 26.10 non è ancora nel `meta-release` ufficiale). Corretto
  il difetto "LTS LTS".
- **Nome nuovo RNFADS** (`rnfads.local`), scritta a lettere alternate: R F D in Orbitron, N A S in JetBrains Mono con la
  sfumatura (`NIDO_WORDMARK="R|N|F|A|D|S"`, controllo di build.sh aggiornato a più pezzi). Font OFL dai pacchetti npm
  Fontsource 5.3.0 (GitHub non raggiungibile dall'ambiente), con le licenze in `ui/fonts/`. Foglio del logo rifatto
  (`logo/rnfads-logo.png`), `logo-rfdnas.svg` rinominato `logo-rnfads.svg`. Provato nel chroot: login e barra laterale con i
  tre font caricati, nessun errore JavaScript. ISO non ancora ricostruita.

## Fase 1D (31/10/2026) — punti 1, 2, 3, 4, 6, 7, 9, 11 scelti dall'utente
- Fatto nel kit e provato nel chroot Ubuntu 26.04 (API con curl, pagine con Playwright, nessun errore JavaScript):
  pacchetto `nido-nas` con `make-deb.sh` e firma Ed25519 (creato, firmato con una chiave di prova fuori dal kit, firma valida
  riconosciuta, pacchetto manomesso rifiutato, `postinst` installato davvero con dpkg), scheda "Aggiornamento di RNFADS" con
  caricamento dal browser, frequenza del catalogo e "Aggiorna ora" per fonte, notifiche e pulizia delle immagini di riserva
  delle app, account con ruoli (protezioni: ultimo amministratore, sé stessi; sessioni chiuse cambiando password; menu ridotto
  per gli account Utente), procedura guidata. Versione 0.3-beta1. **ISO non costruita** (la costruisce una sessione nuova con
  il messaggio in `kit/MESSAGGIO-BUILD-ISO.txt`).
- Non provabile nel chroot: installazione vera con `apt-get` + riavvio di `nido-ui` + ritorno automatico, timer systemd del
  catalogo, `hostnamectl`/`timedatectl` della procedura guidata, notifiche delle app con Docker.
- Errori trovati e corretti nelle prove: suggerimento "https://<nome>.local" mostrato senza `<nome>` (era preso per HTML).

## Fase 1D — build della ISO 0.3-beta1 (31/10/2026, mattina)
- **Build** con `build.sh` in un chroot Ubuntu 26.04 (`debootstrap resolute`, Python 3.14.4) su un host Ubuntu 24.04, 2 CPU:
  **riuscita al primo colpo**, nessuna correzione di build necessaria, ~75 minuti (la compressione squashfs xz è la parte lunga).
  84 pacchetti obbligatori e 10 facoltativi, 520 pacchetti installati (361 sorgente). Unici avvisi, innocui: attributi ACL non
  copiati da mksquashfs e `dpkg-divert: warning: diverting file '/usr/lib/os-release' from an Essential package with rename is
  dangerous` (la diversione di os-release dell'hook c'era già nelle build precedenti, che l'utente ha avviato senza problemi).
- **ISO** `rnfads-0.3-beta1-amd64.iso`, 1 729 800 192 byte (1,7 GB),
  SHA256 `49188601dd5d18a02a92fc78ffec7f361f41adc5d536fc515d8a4e965efabddf`; **5 volumi 7-Zip** da 350 MB
  (`.7z.001`…`.7z.005`) con `SHA256SUMS.txt` (provati con `7z t` e `sha256sum -c`: tutto ok).
- **Pacchetto** `rnfads_0.3~beta1+202610310717_all.deb` (370 KB), SHA256
  `1029cc74d320880cb6724df9228e1d5e0ace266e405d910f1ed7029f3921ed3c`, **non firmato**.
- **Chiave per le firme: assente** (`kit/chiavi/` ha solo `LEGGIMI.txt`): nella ISO `/usr/share/nido/update-keys/` è vuota, quindi
  il NAS installa pacchetti solo in **modalità sviluppatore** finché non si aggiunge la chiave pubblica (pacchetto installato in
  modalità sviluppatore o copia in `/etc/nido/update-keys/` via SSH). La pagina lo dice: "Nessuna chiave per le firme installata".
- **Controlli senza VM** (tutti superati):
  - El Torito: immagine 1 **BIOS** (`/boot/grub/i386-pc/eltorito.img`) e immagine 2 **UEFI** (partizione EFI aggiunta), MBR ibrido + GPT;
  - `dpkg -l nido-nas` = `ii 0.3~beta1+202610310717`; pacchetto salvato in `/var/lib/nido/updates/installed/`; `nido.conf` con
    RNFADS / 0.3-beta1 / `R|N|F|A|D|S`; presenti nella squashfs anche `selfupdate.py`, `wizard.py`, `dpkg/info/nido-nas.list`;
  - servizi abilitati: `nido-ui`, `nido-firstboot`, `caddy`, `nido-standby`, `nido-mdns`, `nido-netmounts`, `nido-uptime`,
    `nido-release-verify`, `nido-live-installer`, timer `nido-monitor`, `nido-catalog` (`OnBootSec=3min`, `OnUnitActiveSec=24h`),
    `nido-apps-update`, più docker e ssh;
  - 33 moduli `nidopanel` compilati (`compileall`) e importati con il Python 3.14.4 della ISO, nessun errore;
  - interfaccia avviata da una copia del sistema della ISO (chroot, `NIDO_TEST_LOOP=1`): primo account, **procedura guidata**
    aperta al primo accesso ("Benvenuto, passo 1 di 6"), **19 pagine × tema chiaro e scuro senza errori JavaScript**, telefono a
    390 px senza scorrimento orizzontale, scheda "Aggiornamento di RNFADS" con versione e pacchetto giusti.
- **Non provata in VM** (la prova l'utente, elenco in DA-FARE.md).

## 31/10/2026 pomeriggio — schermo nero in VirtualBox e pacchetto di aggiornamento
- **Segnalato dall'utente**: la ISO 0.3-beta1 si installa, ma il sistema installato resta con lo **schermo nero** dopo GRUB
  (VirtualBox, UEFI senza Secure Boot, scheda VMSVGA 16 MB, stessa VM in cui la 0.2 funzionava).
- Riprodotta l'installazione qui (installer in modalità automatica su un disco finto): il disco installato si avvia fino al login in
  BIOS e in UEFI + Secure Boot (QEMU, scheda video standard). Prove dell'utente sulla sua VM: con `nomodeset` parte, con
  **`modprobe.blacklist=vmwgfx`** parte → il colpevole è il driver video `vmwgfx` (VMSVGA) del kernel 7.0.0-42.
- **Correzione**: `/etc/modprobe.d/nido-vmwgfx.conf` (`blacklist vmwgfx`), anche nel pacchetto `nido-nas`; `postinst` rifà
  l'initramfs quando i file `nido-*.conf` di modprobe.d cambiano (impronta in `/var/lib/nido/modprobe.sum`). Nella ISO nuova
  l'installer rifà già l'initramfs.
- **Aggiunte richieste dall'utente** (nello stesso pacchetto):
  - pulsante di accensione nella barra in alto (solo amministratori): menu "Riavvia il NAS" / "Spegni il NAS" con conferma;
  - App store: pulsante **"Aggiorna tutto"** in cima allo store (anche in Impostazioni → App store, prima "Aggiorna catalogo
    adesso"); "Aggiorna ora" per fonte c'era già;
  - frequenza predefinita delle fonti: **all'avvio e ogni 6 ore** (timer `OnUnitActiveSec=6h`, `catalog.py`); chi l'ha già
    cambiata dall'interfaccia mantiene la sua scelta.
- Pacchetto `rnfads_0.3~beta1+202610311339_all.deb` (non firmato): installato con dpkg sopra il 0717 nel sistema della ISO,
  pagine provate con Playwright (menu di accensione, conferma, "Aggiorna tutto"), nessun errore JavaScript.
- **ISO non ricostruita**: decisione dell'utente, si rifà quando tutto funziona.

## 31/10/2026 sera — pacchetto con lingue, Docker Hub e store senza CasaOS/ZimaOS/Unraid (ISO non rifatta)
- Richiesta dell'utente: tutto tranne 8 (aggiornamento online), 10 (verifica in due passaggi), 12 (accesso da fuori casa),
  14 (lingua nell'installer); togliere le fonti CasaOS, ZimaOS e Unraid; traduzioni e menu della lingua; marchio segnato come fatto;
  solo il pacchetto, la ISO più avanti.
- Fatto (dettagli in SPEC.md §3.8): fonti tolte (con pulizia del catalogo già scaricato), schermata account Docker Hub, lingue
  it/en/es/de con `ui/i18n.js` e dizionari `ui/lang/*.json`, strumenti per le traduzioni in `kit/strumenti/traduzioni/`.
- Prove nel sistema della ISO (pacchetto installato con dpkg, interfaccia nel chroot, Playwright): 19 pagine × 4 lingue senza
  errori JavaScript; in inglese restano in italiano solo i nomi delle cartelle predefinite ("Cartella personale", "Utenti");
  API: fonti = bigbear/lsio/cool, frequenza predefinita 6 ore, fonte non .zip rifiutata, lingua non supportata rifiutata,
  account Docker Hub con nome non valido rifiutato. **Non provato**: login vero a Docker Hub (da questo ambiente auth.docker.io
  non si raggiunge: il NAS mostra "Registro non raggiungibile"), `docker login`.
- Errori trovati e corretti durante le prove: un modello "{0} min" traduceva anche "ogni minuto"; testi negli attributi
  (placeholder/title) e frasi con ";" non estratti; frasi che iniziano con un punto non trovate.

## 1/11/2026 — versione 1.0 (prima versione stabile) e ISO
- Richiesta dell'utente: Tailscale e ZeroTier dalle impostazioni (punto 12), fonte Runtipi nello store, ISO nuova con tutto
  (aggiornamenti e lingue), chiamata versione 1.0 non beta.
- Fatto (dettagli in SPEC.md §3.9): `remote.py` + Impostazioni → Accesso remoto; fonte Runtipi con convertitore (232 app, compose
  tutti validi); note legali; traduzioni dei testi nuovi e di quelli persi dall'estrazione (regex in `app.js`).
- **Build** con `build.sh` nel chroot 26.04: riuscita al primo colpo (avviso solito di dpkg-divert su os-release, innocuo).
  Una prima partenza è stata fermata subito perché i montaggi del chroot esterno (`/dev`, `/proc`…) si erano tolti: rimontati e
  rilanciata. ISO `rnfads-1.0-amd64.iso` 1 729 910 784 byte, SHA256
  `5b9d193b9ec4983ca03c879b5c531eff149afff82b95353ebce75ecacb0f2761`, 5 volumi 7-Zip; pacchetto `rnfads_1.0+202611010648_all.deb`
  (SHA256 `b86ee2362da4cc2df09dce6bf8b758b36e4ec622d854f4ae9676f5a20552aec4`, non firmato).
- **Controlli senza VM**: El Torito BIOS + UEFI; `nido-nas 1.0+202611010648` installato e salvato in `/var/lib/nido/updates/
  installed/`; `nido.conf` RNFADS / 1.0; tutti i servizi e timer abilitati (catalogo ogni 6 ore); `nido-vmwgfx.conf`, `remote.py`,
  dizionari `lang/` presenti nella squashfs; 34 moduli Python importati con Python 3.14.4 della ISO; `7z t` e `sha256sum -c` ok;
  20 pagine senza errori JavaScript (anche Accesso remoto), telefono a 390 px. Prove in 4 lingue sul pacchetto: nessun errore.
- **Non provato** (serve internet vero o la VM): installazione e collegamento di Tailscale/ZeroTier, installazione di un'app
  Runtipi, login a Docker Hub. Nella ISO non c'è ancora la chiave pubblica per le firme.

## 7/11/2026 sera — ISO 1.2.3
- Build al primo colpo: `rnfads-1.2.3-amd64.iso` 1 830 039 552 byte, SHA256 `b617f7b33c996aea1a2cf0680626f40b8cff6ce7c901499e69ca460bd65580b8`, 5 volumi 7-Zip (`7z t` e SHA256 ok),
  pacchetto `rnfads_1.2.3+202611071705_all.deb`. Dentro: scelta della cartella con il mouse (1.2.1), permessi "Sola lettura" /
  "Lettura e scrittura"; NON dentro: breeze.css e la scelta dello stile, stores_extra.py. Controlli: BIOS+UEFI, 38 moduli
  Python importati, 4 fonti nello store.

## 7/11/2026 — per la prossima ISO: tolta la scelta dello stile
- Richiesta dell'utente: nella prossima ISO niente scelta dello stile, solo l'originale. Tolti dal kit `breeze.css` (archiviato
  in `kit/strumenti/archivio/`), la scheda "Aspetto" e il codice Breeze in `shell()`; controllo sintassi ok.

## 7/11/2026 — pacchetto 1.2.2: stile "KDE Breeze" a scelta
- Dopo varie anteprime (schede, desktop, desktop KDE) l'utente ha scelto la Home in stile KDE Breeze "meno desktop, più NAS",
  con le icone nel riquadro App, e ha chiesto di poter scegliere tra il tema originale (predefinito) e questo. Fatto
  (SPEC.md §3.13).
- Nello stesso pacchetto (rifatto): permessi delle condivisioni "Sola lettura" / "Lettura e scrittura" (richiesta dell'utente).

## 1/11/2026 pomeriggio — pacchetto 1.2.1
- Richiesta dell'utente (foto della finestra di installazione di qBittorrent): scegliere la cartella del NAS con il mouse anche
  nella tabella avanzata. Aggiunto il pulsante (`data-vpick` in `store.js`); il selettore, se la cartella non esiste, risale
  alla prima esistente invece di ripartire da "/". Provato con Playwright.

## 1/11/2026 pomeriggio — ISO 1.2
- **ISO 1.2 costruita** al primo colpo: `rnfads-1.2-amd64.iso` 1 829 771 264 byte, SHA256 `c1d9d84ac4b481c6bc91b786e580b43c105ce56843c81a1a7da9f671a9583c59`, 5 volumi 7-Zip (`7z t` e
  SHA256 ok), pacchetto `rnfads_1.2+202611011346_all.deb`. Controlli: BIOS+UEFI; cage, kiosk.py, GTK/WebKit importabili, utente
  nido-kiosk nei gruppi video/render/input, screen.json attivo; 38 moduli Python; 4 fonti store. Installazione automatica di prova
  (inglese) su disco loop: nido-kiosk-boot abilitato, lingua/console in inglese.
- L'utente ha installato il pacchetto 1.2 ma non trovava le pagine nuove (probabile cache del browser o schermo non ancora
  installato) e ha chiesto: impostazioni di rete LAN/Wi-Fi nell'interfaccia (c'erano già: aggiunte le reti nascoste), schermo
  del NAS installato già con la ISO, condivisione di cartelle sul disco di installazione (già possibile in /DATA, ora con
  cartella proposta e creata da sola), e la ISO nuova con tutto.

## 1/11/2026 pomeriggio — pacchetto 1.2 unico: servizi cloud + rete + schermo del NAS
- Richiesta dell'utente: accesso dal PC del NAS per rete e terminale, "pagina in stile del NAS, non in stile installer", in un
  pacchetto unico con i servizi cloud. Fatto (SPEC.md §3.12): Impostazioni → Rete e → Schermo del NAS (kiosk cage + WebKitGTK
  che mostra l'interfaccia web stessa, quindi anche il Terminale).
- Prove: pagine Rete e Schermo con un nmcli finto (DHCP→fisso, banner di conferma, ritorno, Wi-Fi con ":" nel nome, gateway
  fuori rete rifiutato), in italiano e inglese senza testi rimasti, nessun errore JavaScript; kiosk in cage headless.

## 1/11/2026 pomeriggio — pacchetto 1.2: servizi cloud dall'interfaccia
- Richiesta dell'utente: collegarsi ai servizi cloud dall'interfaccia, non dal terminale. Fatto con rclone (SPEC.md §3.12).
- Prove: vedi SPEC.md §3.12. Errori trovati e corretti nelle prove: scritture perse smontando subito (ora write-back 2 s e arresto
  che aspetta), porta 53682 occupata da un accesso lasciato a metà (ora chiuso prima di ricominciare), messaggi di rclone poco
  leggibili (ora frasi semplici).

## 1/11/2026 mezzogiorno — ISO 1.1 costruita
- Build con `build.sh` nel chroot 26.04 al primo colpo (solito avviso di dpkg-divert). Locale generate: de_DE, en_GB, en_US,
  es_ES, it_IT. ISO `rnfads-1.1-amd64.iso` 1 730 140 160 byte, SHA256
  `bbd9e83321b6e6f8ff5750b924085d5668dedf9ad62748ef6529877f1626a24d`, 5 volumi 7-Zip (`7z t` e `sha256sum -c` ok); pacchetto
  `rnfads_1.1+202611011043_all.deb`. Pacchetto a parte `rnfads-extra-store_1.0+202611011041_all.deb` (solo per l'utente).
- Controlli: El Torito BIOS + UEFI; menu GRUB in inglese con nomodeset; nella squashfs chiave pubblica dell'utente, vm-video.sh,
  installer.tsv, issue.sh, online.py, i18n.py, timer nido-selfupdate-check abilitato, NESSUN stores_extra.py; 35 moduli Python
  importati con 3.14.4; 4 fonti nello store.
- **Installazione automatica vera** su disco loop da 24 GB in tedesco (`NIDO_LANG=de`), con la copia di prova dell'installer che
  salta solo il montaggio vfat e il grub-install EFI (il container non monta vfat): riuscita. Sul disco installato:
  `LANG=de_DE.UTF-8`, tastiera de, Europe/Berlin, `ui-language.json` de, nido.conf aggiornato, `/etc/issue` e `/etc/motd` in
  tedesco, grub.cfg con `modprobe.blacklist=vmwgfx` (niente nomodeset: nessuna scheda VMSVGA nel container).
- Da provare dall'utente in VM: schermo con VMSVGA (nomodeset automatico), menu lingua/tastiera/fuso, interfaccia nella lingua
  scelta dopo il riavvio.

## 1/11/2026 — versione 1.1 nel kit (installer in 4 lingue, console/notifiche tradotte, aggiornamento online)
- Richiesta dell'utente: punti 1-2-3-5-8 della lista (lingua e traduzione dell'installer, chiave nella ISO, aggiornamento online,
  console e notifiche), poi guida per GitHub, e **una sola ISO** alla fine. Cloudflare Tunnel lasciato fuori.
- Fatto (SPEC.md §3.11). Prove: installer con `whiptail` finto in de/es (schermi lingua → tastiera → fuso → benvenuto → disco
  tradotti; tutte le 42 chiavi trovate in `installer.tsv`, segnaposto coerenti); `issue.sh` in it/en/de; traduzione delle notifiche
  in en/es/de; aggiornamento online end-to-end con chiave di prova e server locale (manifesto manomesso rifiutato); scheda in
  Impostazioni → Aggiornamenti in it/en con Playwright. Errore trovato e corretto nella prova: `subprocess` non importato nel
  cambio di lingua (ora `run_rc`).
- L'utente non pubblica su GitHub per ora (uso personale). Ha mandato la chiave pubblica (in `kit/chiavi/`) e chiesto di rimettere
  le fonti CasaOS, ZimaOS e Unraid e un pacchetto da provare prima della ISO. Fatto; feed Unraid provato (scaricato e convertito),
  pagina App store senza errori JavaScript in it/en. Pacchetto 1.1 non firmato (la firma la mette l'utente con la sua privata).
- L'utente: "il pacchetto funziona"; console ancora ferma sulla riga di avvio con VMSVGA (foto) → nomodeset automatico solo su
  quella scheda; fonti extra spostate nel pacchetto a parte `nido-extra-store`; installer che parte in inglese. Poi ISO 1.1.

## 1/11/2026 mattina — versione 1.0.1 (correzioni dopo la prova dell'utente)
- Segnalati dall'utente sulla 1.0: **schermo nero** ancora presente in VirtualBox (VMSVGA) e **"Lingua non supportata"** cambiando
  lingua; inoltre l'installer non fa scegliere la lingua (→ primo punto alla ripresa, DA-FARE.md).
- Causa dello schermo nero: l'initramfs di Ubuntu 26.04 copia solo `/usr/lib/modprobe.d/` (hook `kmod`), non `/etc/modprobe.d/`
  dove stava il blocco di `vmwgfx`, e il driver viene caricato già nell'initramfs. Correzione: regola in `/usr/lib/modprobe.d/` +
  `modprobe.blacklist=vmwgfx` nella riga di avvio (`/etc/default/grub.d/15-nido-video.cfg`) e nel menu della ISO. Verificati con
  `lsinitramfs` (regola presente) e lettura dei file di GRUB (opzione aggiunta una volta sola). Non provato in VM.
- Causa della lingua: `act()` riscriveva il contenuto del `<select>` con la rotellina. Corretto e provato con Playwright scegliendo
  dal menu (en → de → it, nessun avviso, nessun errore JavaScript).
- Build 1.0.1: la prima partenza si è fermata a debootstrap ("Couldn't download package gzip", mirror): rilanciata, riuscita.
  ISO `rnfads-1.0.1-amd64.iso`, SHA256 `d25c9e558551996eb2668c045d817ad8157e837f998c6387726e51fb0dd51e68`, 5 volumi 7-Zip;
  pacchetto `rnfads_1.0.1+202611010805_all.deb` (SHA256 `dc6e98535917020e99fb6b79ff4f45469e6dafcfaa891ca303a2b6cf21627f32`).
  Controlli: El Torito BIOS+UEFI, `nido-nas 1.0.1` installato, servizi abilitati, Python compilato e importato con 3.14.4, `7z t` e
  SHA256 ok.
