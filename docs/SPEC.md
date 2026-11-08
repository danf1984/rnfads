# RFD-NAS — specifiche di progetto

Documento di consegna: raccoglie tutto quello che è stato deciso e fatto fino al **1 novembre 2026** (**versione 1.0.1**, ISO costruita, non provata in VM; prima: fase 1D, ISO 0.3-beta1);
prima, fino al **30 ottobre 2026, sera**
(**fase 1C** e nome nuovo **RNFADS** del 31/10; fase 1C: errori segnalati, file manager completo, modifica dell'installazione delle app, app su un altro disco,
contatore del tempo di accensione, passaggio alla versione nuova di Ubuntu; ISO ricostruita ma **non provata in VM**:
la prova l'utente). Chi riprende il lavoro deve partire da qui e da `DA-FARE.md`.

## 1. Cos'è

RFD-NAS è un sistema operativo per NAS su PC x86-64, basato su **Ubuntu 26.04 LTS** ("resolute"),
facile da usare e tutto a portata di clic. L'interfaccia web è **completamente nostra** e dalla fase 1A
**sostituisce CasaOS**, che è stato tolto dal kit.

- **Nome: RNFADS** (dal 31/10/2026), indirizzo `rnfads.local`, scritta del marchio a lettere alternate: **R, F, D** scure in
  **Orbitron**, **N, A, S** con la sfumatura in **JetBrains Mono** (`NIDO_NAME="RNFADS"`, `NIDO_HOSTNAME="rnfads"`,
  `NIDO_WORDMARK="R|N|F|A|D|S"`: pezzi dispari in Orbitron, pari in JetBrains Mono). Il logo resta quello della caverna.
  Il nome è un parametro (`NIDO_NAME`, `NIDO_HOSTNAME`, `NIDO_WORDMARK` in `config.env`): il codice non lo scrive a
  mano da nessuna parte. I percorsi interni restano `nido` (`/usr/lib/nido`, `/etc/nido`, servizi `nido-*`).
- Storia del nome: "Nido" (provvisorio) → "Kubix" (scartato: KUBIX è un marchio di Lectra SA, USPTO 79259119,
  anche per il software) → "Kubion" (scartato: due aziende software Kubion in Olanda e Germania)
  → "KuboraNas" (usato nella fase 1A) → "CaveNAS" (28/10/2026, usato nella fase 1B-1) → "RFD-NAS" (29/10/2026, fasi
  1B-2 e 1C) → **RNFADS** (scelto dall'utente il 31/10/2026). L'integrazione Home Assistant mantiene il nome tecnico
  `rfd_nas` (cambiarlo obbligherebbe a reinstallarla); i nomi mostrati sono RNFADS.
- **Verifica del nome RNFADS** (31/10/2026, fatta dall'utente): **TMview**, ricerca "Nome del marchio contiene RNFADS" →
  nessun risultato. **WIPO Global Brand Database** (31/10/2026, controllata dall'assistente dal browser dell'utente: 89 fonti,
  77 milioni di marchi, compresi USPTO, EUIPO e uffici nazionali), "contiene la parola RNFADS" → nessun risultato. Prima di
  pubblicare conviene una ricerca "fonetica"/"simile" nella stessa banca dati (nomi che suonano uguale) e, se si vuole la
  certezza legale, il parere di un consulente in marchi.
- **Verifica del nome RFD-NAS (29/10/2026, solo ricerca web, fatta dall'utente)**: l'unico marchio "RFD" attivo trovato è di
  Survitec (zattere di salvataggio e attrezzature di sicurezza in mare): settore diverso, rischio basso. La verifica sui registri
  ufficiali (EUIPO/TMview, WIPO, USPTO, classi 9 e 42) la fa l'utente.
- Verifica del vecchio nome CaveNAS (28/10/2026, solo ricerca web): nessun NAS o sistema operativo chiamato CaveNAS,
  Cave NAS o CaveOS. "CAVE™" è un marchio di un sistema di realtà virtuale (Electronic Visualization Laboratory,
  University of Illinois): settore diverso, rischio basso. Scartati prima: StorioNAS (VTech Storio, tablet per
  bambini venduti in Europa), PupNAS e PuppoNAS (confusione con Puppy Linux; "PUP" = programma indesiderato
  per gli antivirus), HomeCloudOS (marchio HOMECLOUD, progetti con lo stesso nome), HomeNasOS (troppo generico).
  I registri ufficiali (EUIPO/TMview, WIPO Global Brand Database, USPTO) **vanno controllati prima di pubblicare**,
  classi 9 e 42.

## 2. Cosa c'è nel pacchetto

| Cartella / file | Contenuto |
|---|---|
| `RIPRENDERE.md` | **Da leggere per primo**: dove siamo, cosa provare, cosa resta da fare, messaggio per la prossima sessione. |
| `pacchetti/` | Ultimo pacchetto di aggiornamento `rnfads_1.0.1+202611010805_all.deb` (non firmato) con SHA256. |
| `kit/` | Kit di build: ISO + interfaccia nuova. Vedi `kit/README.md`. Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). |
| `kit/live/includes/usr/lib/nido/panel/ui/` Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). | **Interfaccia** (fasi 1A e 1B-1): HTML, CSS, JS, font Inter; unica libreria di terzi xterm.js in `ui/vendor/xterm/`. |
| `kit/live/includes/usr/lib/nido/panel/nidopanel/` Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). | Backend Python dell'interfaccia (il Centro di controllo e `www/` sono stati tolti nella 1B-1). |
| `LICENSE`, `kit/LICENSE` Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). | **GPL-3.0**, licenza del nostro codice (scelta dall'utente il 28/10/2026). |
| `prototipo-ui/` Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). | Prototipo dell'interfaccia con dati di esempio: il riferimento visivo approvato. Aggiornato al nome RFD-NAS (30/10/2026). |
| `schermate/` Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). | Schermate del prototipo (`k*`, ancora con il nome Kubion), in `schermate/1A/` quelle della 1A (con il vecchio nome KuboraNas) e in **`schermate/1B/` quelle dell'interfaccia funzionante con il nome e il logo CaveNAS** (29/10/2026, ambiente di prova: dischi finti "di prova", nome host `vm`). |
| `STATO-FASE1B.md` Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). | Diario delle tappe delle fasi 1B-1 e 1B-2. |
| `schermate/1B-2/` Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). | Schermate della VM con la ISO vera (30/10/2026). |
| ISO (a parte) | `rnfads-1.0.1-amd64.iso` in 5 volumi 7-Zip da 350 MB (`.7z.001`…), con `SHA256SUMS.txt` e `ESTRARRE-LA-ISO.txt`, più `rnfads_1.0.1+202611010805_all.deb`. Build del 1/11/2026 (versione 1.0.1), SHA256 `d25c9e55…b0dd51e68`, **non provata in VM** (la prova l'utente). Senza chiave pubblica per le firme. |
| `logo/` Anche `kit/make-deb.sh` (solo il pacchetto di aggiornamento), `kit/strumenti/` (chiave e firma), `kit/chiavi/` (chiavi pubbliche), `kit/NOVITA.md`, `kit/MESSAGGIO-BUILD-ISO.txt` (messaggio per la sessione che costruisce la ISO). | Logo (arco della caverna con tre dischi, `logo-rnfads.svg`), icone app chiara e scura, foglio del logo `rnfads-logo.png` (rifatto con la scritta "rfd|nas" il 30/10/2026), colori. |

Prototipo: `prototipo-ui/index.html#home`, poi `#store`, `#hub`, `#install`, `#files`, `#smb`, `#diskpage`, `#disks`,
`#mount`, `#standby`, `#myapps`, `#updates`, `#term`, `#settings`, `#about`, `#login`; con `/dark` (es. `#home/dark`)
il tema scuro.

## 3. Stato del kit

### 3.1 Già funzionante e provato in VM (prima della fase 1A, con CasaOS)
- Build: `sudo ./build.sh` su Ubuntu/Debian amd64. Usa debootstrap di resolute, squashfs xz e
  avvio ibrido BIOS + UEFI + Secure Boot (shim firmato Microsoft e GRUB firmato Canonical).
- Installer whiptail in italiano (`/usr/local/sbin/nido-install`). Il disco di sistema è Btrfs con i
  sottovolumi `@ @data @docker @appdata @log @snapshots`, più snapper per gli snapshot.
- Centro di controllo in Python (dischi, condivisioni Samba/NFS/DLNA, utenti, backup restic + rclone,
  aggiornamenti, notifiche ntfy/Telegram/email/webhook, convertitori ZimaOS v2 e Unraid CA, monitor SMART).
- **Correzioni già fatte e verificate in VM** (non vanno perse):
  1. `build.sh`: `shimx64.efi.signed` è un link assoluto (alternatives) e va risolto dentro il chroot.
  2. `nido-install`: il GRUB firmato copiato da grub-install è la versione per CD (gcdx64) e cerca
     `grub.cfg` in `/boot/grub` della ESP. Per questo il rimando va scritto in `EFI/BOOT`, `EFI/ubuntu`,
     `boot/grub` ed `EFI/<slug>`. Senza, in UEFI (VirtualBox compreso) l'avvio si ferma al prompt `grub>`.
  3. (Solo CasaOS, non serve più: `casaos-local-storage-first` dopo gateway e message-bus.)
  4. In 26.04 il servizio WS-Discovery sta nel pacchetto `wsdd-server` (unità `wsdd-server.service`).
  5. Pulsanti whiptail in italiano (Sì/No/OK/Annulla) e testo motd "basato su Ubuntu".
- Test superati in QEMU (TCG): avvio della ISO in BIOS e in UEFI con Secure Boot, installazione, avvio del
  disco installato in BIOS e UEFI+SB, `systemctl is-system-running` = running, HTTP 200, SSH funzionante.

### 3.2 Modifiche della fase 1A al kit (**provate con la build del 30/10/2026**, vedi §8.4)
- **CasaOS tolto**: niente download in `build.sh`, niente `casaos-install.sh`, `branding-apply.sh`, `nido-theme`,
  unità `nido-branding*`, `nido-panel`, `nido-stores*`, niente `DOCKER_MIN_API_VERSION`, niente udevil/devmon.
  `config.env` non ha più `CASAOS_PACKAGES` né `APPSTORES` (le fonti sono in `nidopanel/catalog.py`).
- Servizi nuovi: `nido-ui` (interfaccia, porta 80), `nido-netmounts` (cartelle di rete, prima di Docker),
  `nido-catalog.timer` (catalogo settimanale), `nido-apps-update.timer` (app di notte alle 03:30, orario
  cambiabile dall'interfaccia). Tutti spenti nel sistema live.
- Pacchetti aggiunti: `python3-yaml`, `docker-compose-v2` (ora obbligatorio), `smbclient`, `avahi-utils`,
  `nfs-common`, `davfs2`.
- `config.env`: `NIDO_NAME="CaveNAS"`, `NIDO_HOSTNAME="cavenas"`, `NIDO_WORDMARK="cave|nas"` (dal 29/10 RFD-NAS, vedi §1),
  `NIDO_VERSION="0.2-beta1"`, link per le donazioni `NIDO_DONATE_*`, `NIDO_PROJECT_URL`.
- Installer: crea anche l'account dell'interfaccia con lo stesso utente e la stessa password (se ≥ 8 caratteri).
- Hook: copia GPL-3.0 e note legali nell'interfaccia, licenza del font Inter accanto alla copia inclusa,
  cartelle `/var/lib/nido/apps` e `/var/lib/nido/catalog`.
- Comando `sudo nido-ui-user <nome>` per creare un account o reimpostare la password.
- `build.sh`: corretto anche il `chmod` di `usr/local/bin/*` (la cartella ora è vuota e con `set -e` la build
  si sarebbe fermata).

### 3.3 Modifiche della fase 1B-1 al kit (**provate con la build del 30/10/2026**, vedi §8.4)
- Pacchetti obbligatori aggiunti: `hdparm`, `xfsprogs`, `caddy` (Ubuntu 2.6.2).
- Servizi nuovi: `nido-standby` (standby dei dischi), `nido-mdns` (nomi .local delle app); abilitati anche
  `caddy`, tutti spenti nel sistema live. `nido-ui` ora ascolta su `127.0.0.1:8090` (`NIDO_FALLBACK_LISTEN=0.0.0.0:80`).
- Hook: Caddyfile iniziale in HTTP verso 127.0.0.1:8090, cartella `/etc/nido/tls` (0750 root:caddy), testo della
  console con l'indirizzo HTTPS. Primo avvio (`firstboot.sh`): `nidopanel.cli https-apply` crea il certificato di casa
  e attiva l'HTTPS (modo "home", reindirizzamento spento finché l'utente non installa il certificato).
- `snapshot-apt.sh`: niente doppioni quando l'aggiornamento parte dall'interfaccia (`NIDO_NO_APT_SNAPSHOT`).
- Tolti: cartella `www/`, rotte `/nido/`, `theme.py`. Il nome nelle intestazioni HTTP e negli User-Agent ora viene da
  `NIDO_NAME` (prima c'era scritto "NidoNAS").

### 3.4 Modifiche della fase 1B-2 al kit (30/10/2026, provate in VM)
- Nome **RFD-NAS** (§1). Pacchetti invariati.
- **Standby con programma settimanale** (`standby.py`, Dischi → Programma settimanale): fasce "Standby" e "Sempre
  accesi" per giorni e orari (anche oltre la mezzanotte), minuti senza attività nelle fasce di standby, per ogni disco
  "Segue il programma settimanale". API `POST /api/disks/standby-schedule`.
- **Spegnimento e accensione programmati** (`powersched.py`, Impostazioni → Generale): servizio `nido-poweroff`, timer
  `nido-poweroff.timer` scritto dall'interfaccia (`Persistent=false`), accensione con `rtcwake` impostata a ogni
  spegnimento (anche da "Spegni"), prova della sveglia del PC, attesa di backup/aggiornamenti/operazioni lunghe fino a
  un massimo e poi spegnimento saltato, notifiche (evento nuovo "Spegnimento programmato"). API `/api/system/power-schedule`.
- Correzioni trovate in VM: dischi dei dati montati a ogni avvio (attesa 90 s + rimontaggio di riserva in
  `nido-netmounts`), snapshot doppi di apt (`dpkg-divert` di `80snapper`), Caddy che non ripartiva sopra la porta di
  riserva (`caddy.service.d/10-nido.conf` + `caddy-prestart.sh`), mDNS annunciato sulla rete di Docker
  (`allow-interfaces` gestito da `nido-mdns`), messaggi dell'installer, piccoli difetti grafici della pagina Dischi.

### 3.7 Fase 1D (31/10/2026) — aggiornamento senza ISO e rifiniture (**ISO 0.3-beta1 costruita il 31/10/2026, da provare**)
- **Versione 0.3-beta1** (`NIDO_VERSION`), nome RNFADS (§1).
- **Pacchetto del sistema `nido-nas`** (`kit/make-deb.sh`, chiamato anche da `build.sh`): contiene `/usr/lib/nido` (interfaccia,
  script), i servizi `nido-*` e il drop-in di Caddy, `/usr/local/sbin/nido-*`, note legali, `/usr/share/nido` e le **chiavi
  pubbliche** di `kit/chiavi/*.pem` (in `/usr/share/nido/update-keys/`). Non contiene le impostazioni cambiate dall'interfaccia
  (`20auto-upgrades`, `daemon.json`, Caddyfile, timer scritti dall'interfaccia): un aggiornamento non le tocca. File
  `out/<nome>_<versione>_all.deb`, versione Debian `0.3~beta1+AAAAMMGGhhmm` (ogni build è più nuova). `postinst`: riscrive
  nome/versione/scritta in `/etc/nido/nido.conf` da `/usr/lib/nido/identity.conf` (il nome host non cambia), abilita i servizi,
  `rebrand.sh`, riavvia `nido-ui` (niente di tutto questo dentro il chroot della build). Nella ISO il pacchetto è installato con
  `dpkg -i` e salvato in `/var/lib/nido/updates/installed/`. `make-deb.sh` si ferma se in `kit/chiavi/` c'è una chiave privata.
- **Aggiornamento con pacchetto locale** (`selfupdate.py`, Impostazioni → Aggiornamenti di sistema → "Aggiornamento di RNFADS"):
  carica `.deb` + `.deb.sig` (a blocchi), controllo di nome, versione e **firma Ed25519** (`openssl pkeyutl -sign -rawin`;
  verifica con `cryptography`), novità lette dal pacchetto (prima sezione di `kit/NOVITA.md`), installazione come unità
  `nido-job-selfupdate` con snapshot prima e dopo e `apt-get install ./pacchetto.deb` (installa anche le dipendenze nuove), poi
  l'interfaccia deve rispondere entro 3 minuti, se no si reinstalla da soli il pacchetto precedente. "Torna alla versione
  precedente" (ultimi 3 pacchetti tenuti). **Modalità sviluppatore** (spenta di base) per installare pacchetti non firmati.
  Strumenti per l'utente: `kit/strumenti/crea-chiave.sh|.ps1` e `firma-pacchetto.sh|.ps1`; `NIDO_SIGN_KEY=<privata.pem>
  ./make-deb.sh` firma da solo. Provato nel chroot: pacchetto creato, firma valida riconosciuta, pacchetto manomesso rifiutato
  (anche all'installazione), `postinst` (nome e versione aggiornati, nome host invariato), caricamento dal browser.
- **Catalogo delle app automatico** (punto 20): `nido-catalog.timer` all'avvio (3 min) e ogni 24 ore; Impostazioni → App store:
  "All'accensione" e "Poi ogni" 6/12/24 ore, settimana, mai (drop-in `nido-catalog.timer.d/10-frequenza.conf`, configurazione in
  `/etc/nido/catalog-schedule.json`); pulsante "Aggiorna ora" per ogni fonte (`POST /api/store/refresh/<fonte>`: le altre
  fonti restano come all'ultimo aggiornamento); ultimo aggiornamento per fonte; se una fonte non risponde resta l'ultima buona.
- **Notifiche delle app** (evento nuovo "App aggiornate, tornate indietro o spostate"): app aggiornata, aggiornamento non
  riuscito con ritorno alla versione di prima.
- **Pulizia delle immagini di riserva** `nido-rollback/...:prev` dopo 7 giorni (ogni notte, prima dell'aggiornamento delle app).
- **Account dell'interfaccia con ruoli** (Impostazioni → Account, solo amministratori): nuovo account, ruolo Amministratore/Utente,
  nuova password (chiude le sessioni di quell'account), elimina; mai senza amministratori, non si elimina/declassa sé stessi.
  Gli account **Utente** vedono solo Home, App store (consultazione) e il proprio account (il server lo controllava già per
  ogni rotta). Ultimo accesso per account.
- **Procedura guidata al primo avvio** (`wizard.py`, stato in `/etc/nido/wizard.json`): si apre dopo l'accesso di un
  amministratore finché non è finita o saltata; passi: benvenuto, nome del NAS e fuso orario (hostnamectl, /etc/hosts, avahi,
  certificato di casa e Caddy rifatti), dischi dei dati (elenco + link a Dischi), cartella "Condivisa" per tutti gli utenti,
  aggiornamenti di sicurezza automatici e certificato di casa, fine. Si riapre da Impostazioni → Generale.
- **Correzioni e aggiunte del 31/10 pomeriggio** (pacchetto `0.3~beta1+202610311339`, ISO non ancora rifatta): schermo nero dopo
  GRUB con la scheda VMSVGA di VirtualBox (`blacklist vmwgfx`; nella 1.0.1 spostato in `/usr/lib/modprobe.d/` + riga di avvio, §3.10),
  pulsante Riavvia/Spegni nella barra in alto, "Aggiorna tutto" nello store, fonti all'avvio e ogni 6 ore di base.
- **Consegna**: `build.sh` crea anche i **volumi 7-Zip da 350 MB** (`<iso>.7z.001…`) e `SHA256SUMS.txt` (ISO, volumi, .deb).
- **Build del 31/10/2026 08:28** (`build.sh` nel chroot 26.04): riuscita al primo colpo, nessuna correzione; ISO 1,7 GB, SHA256
  `49188601dd5d18a02a92fc78ffec7f361f41adc5d536fc515d8a4e965efabddf`, 5 volumi 7-Zip. **Senza chiave pubblica** (`kit/chiavi/` vuota):
  aggiornamenti solo in modalità sviluppatore finché non si aggiunge. Controlli senza VM superati (El Torito BIOS+UEFI, `nido-nas`
  installato e salvato, servizi abilitati, Python compilato con il 3.14.4 della ISO, 38 pagine senza errori JS): `STATO-FASE1B.md`.

### 3.13 Versione 1.2.2 (7/11/2026) — secondo stile dell'interfaccia (TOLTO dal kit il 7/11/2026 per la prossima ISO)
- `ui/breeze.css` (caricato sempre dopo `style.css`, regole solo sotto `:root[data-look="breeze"]`, chiaro e scuro con le
  stesse regole di `data-theme`). `applyTheme()` mette `data-look` da `localStorage` (`look`: `originale` predefinito o
  `breeze`). Con Breeze `shell()` divide la barra laterale nei gruppi Sistema / Dati / App e utenti (`BREEZE_GROUPS`), mette la
  ricerca nella barra laterale (`#bsearch`, apre la stessa palette di Ctrl K) e aggiunge la barra di stato `.bstatus`.
  Scelta in Impostazioni → Generale → Aspetto (stile + chiaro/scuro/automatico). Provato con Playwright: Home, App store, File,
  impostazioni, chiaro e scuro, telefono; nessun errore JavaScript; il tema originale resta identico.

### 3.12 Versione 1.2 (1/11/2026) — servizi cloud, rete e schermo del NAS dall'interfaccia (pacchetto, ISO non rifatta)
- `nidopanel/cloud.py` + Impostazioni → **Servizi cloud** (`settingsCloud`, `cloudDialog`, `cloudForm` in `pages.js`), API
  `/api/cloud`, `/cloud/remotes` (POST crea, DELETE `/<nome>`), `/<nome>/test`, `/<nome>/mount`, `/<nome>/autoboot`,
  `/cloud/oauth/start|finish`. Tutto con rclone (già nella ISO; ora anche in Depends con fuse3), file di configurazione di root
  (lo stesso dei backup e del terminale), scritto direttamente con configparser (600); password con `rclone obscure -` da stdin,
  mai sulla riga di comando.
- **OAuth** (Google Drive, OneDrive, Dropbox, Box): `rclone authorize <tipo> --auth-no-open-browser` sul NAS; il NAS legge il
  redirect 307 della pagina locale di rclone e dà all'utente la pagina di accesso vera; alla fine l'utente incolla l'indirizzo
  `http://127.0.0.1:53682/?state=…&code=…` (o localhost) e il NAS lo apre in locale: rclone scambia il codice e stampa il token
  (tra `--->` e `<---`). OneDrive: `drive_id`/`drive_type` letti da Microsoft Graph. Accessi lasciati a metà chiusi prima di
  ricominciare (porta 53682).
- Con utente/chiavi: MEGA, WebDAV/Nextcloud, S3 (provider a scelta), B2, SFTP, FTP; prova con `rclone lsf` e `rclone about`;
  se la prova non riesce il servizio non viene salvato; errori di rclone tradotti in frasi semplici (credenziali, server non
  trovato/irraggiungibile, tempo scaduto, certificato, bucket).
- **Cartella nei File**: unità `nido-cloud@<nome>.service` (Type=notify, `rclone mount` in `/media/cloud/<nome>`, utente e
  gruppo del NAS da `/etc/nido/cloud/<nome>.env`, `--vfs-cache-mode writes --vfs-write-back 2s`, arresto che aspetta i
  caricamenti, prima di Docker); abilitata = ricollegata all'avvio. In File appare nella sezione Rete (menu Apri/Scollega/
  Servizi cloud…); esclusa dall'elenco dei dischi e dallo spostamento delle app. Backup: testo che rimanda alla pagina nuova.
- Provato qui: WebDAV locale (`rclone serve webdav`) collegato dall'interfaccia, prova e spazio, password sbagliata rifiutata con
  messaggio chiaro, mount con permessi dell'utente del NAS e scrittura arrivata sul server; OAuth Google e Dropbox fino alla
  pagina di accesso vera e (Google) fino allo scambio del codice, che qui fallisce solo perché manca internet; pagina e
  finestre in inglese senza testi italiani rimasti, nessun errore JavaScript. Non provato: un account cloud vero.

- **Rete** (`nidopanel/network.py`, Impostazioni → Rete, API `/api/network`, `/network/apply|confirm|rollback`,
  `/network/wifi` GET/POST, DELETE `/network/wifi/<uuid>`): NetworkManager con `nmcli -t -e yes`. Per ogni scheda indirizzo,
  gateway, DNS attuali; DHCP o fisso (prefisso, gateway nella stessa rete, DNS facoltativi). Prima di applicare salva le
  impostazioni in `/var/lib/nido/net-rollback.json` e avvia il timer transitorio `nido-net-rollback` (180 s →
  `cli network-rollback`); la scheda si riattiva 2 s dopo la risposta (`systemd-run`), "Conferma" ferma il timer. Wi-Fi: ricerca
  e collegamento scrivendo il file keyfile di NetworkManager (600, SSID come byte, password mai sulla riga di comando).
- **Schermo del NAS** (`nidopanel/screen.py`, Impostazioni → Schermo del NAS, API `/api/screen`, `/screen/install`,
  `/screen/enabled`): componenti facoltativi installati con un job (`cli screen-install`: cage, python3-gi, gir1.2-gtk-4.0,
  gir1.2-webkit-6.0, fonts-dejavu-core, libgl1-mesa-dri; utente di sistema `nido-kiosk` nei gruppi video, render, input).
  `nido-kiosk.service` (User=nido-kiosk, PAMName=login, tty1, Conflicts e OnFailure getty@tty1) avvia `kiosk-start.sh` →
  `cage -d -s` + `kiosk.py` (GTK4 + WebKit 6.0, renderer software, sandbox di WebKit spento perché bwrap non parte ovunque:
  si aprono solo `http://127.0.0.1:<porta>` e `localhost`, `window.open`/`_blank` nella stessa finestra, riprova se
  l'interfaccia non risponde). `nido-kiosk-boot.service` all'avvio lo parte solo se attivo e se c'è `/dev/dri/card*` (con
  nomodeset, es. VMSVGA, resta la console di testo; in VirtualBox serve VBoxSVGA). Pagina di accesso: se la richiesta arriva
  diretta da 127.0.0.1 (non da Caddy) `/auth/state` aggiunge `local_screen` e gli indirizzi IPv4 del NAS.
  Provato con cage in modalità headless: interfaccia vera a tutto schermo, sito esterno bloccato, `window.open` interno
  aperto. Bug di cage 0.2 trovato: `fullscreen()` prima di mostrare la finestra lo fa abortire (tolto: cage dà già tutto
  lo schermo). Non provato: monitor vero, tastiera, avvio da tty1 con systemd.
- Icone nuove: `lan`, `monitor`, `cloud`.
- **ISO 1.2**: componenti dello schermo nella lista dei pacchetti (`nido.list`), utente `nido-kiosk` e `/etc/nido/screen.json`
  `{"enabled": true}` creati dall'hook; l'installer abilita `nido-kiosk-boot.service` sul sistema installato (non sulla
  chiavetta). Reti Wi-Fi nascoste (`hidden=true` nel keyfile). **Condivisioni**: un percorso nuovo dentro `/DATA` viene creato
  (`2775`, gruppo `users`) e il nome propone `/DATA/<nome>` nella finestra "Nuova condivisione".

### 3.11 Versione 1.1 (1/11/2026) — installer tradotto e aggiornamento online (nel kit, ISO da fare)
- **Installer** (`nido-install`): tutti i testi passano da `M '<testo italiano con %s>' valori…`, che cerca la traduzione in
  `/usr/lib/nido/installer.tsv` (4 colonne it/en/es/de, segnaposto `%s`). Primo schermo: lingua (scritto in 4 lingue); poi
  tastiera (it, us, gb, es, de, fr, ch; `loadkeys` subito, così password e nomi si scrivono giusti) e fuso orario (elenco +
  "Altro…" controllato in `/usr/share/zoneinfo`). Proposte di base secondo la lingua. Riepilogo con lingua/tastiera/fuso.
  Sul disco: `/etc/default/keyboard`, `/etc/localtime` + `/etc/timezone`, `/etc/default/locale` (it_IT, en_US/en_GB con tastiera
  UK, es_ES, de_DE), `/etc/nido/ui-language.json`, valori in `nido.conf`. L'hook genera tutte queste locale. Modo automatico:
  `nido.lang=` nel menu di avvio (`NIDO_LANG`). La console live dice come riaprire l'installer nella lingua scelta.
- **Console**: `/usr/lib/nido/issue.sh [lingua]` scrive `/etc/issue` e `/etc/motd`; chiamato dall'hook, dall'installer,
  da `rebrand.sh` (sempre) e dal cambio di lingua in Impostazioni.
- **Notifiche**: `nidopanel/i18n.py` traduce titolo e testo in `notify.send()` con gli stessi dizionari dell'interfaccia
  (`ui/lang/*.json`, stesse regole di `i18n.js`, pezzi variabili tradotti anche con i modelli). Testi in `tr/extra5.tsv`.
- **Aggiornamento online** (`nidopanel/online.py`): sul sito (GitHub Pages) `<canale>.json` + `.json.sig` (manifesto firmato:
  versione, `package_version`, nome del .deb, sha256, dimensione, note) e `pool/<pacchetto>.deb` + `.sig`. Il NAS controlla la
  firma del manifesto (stesse chiavi dei pacchetti: impedisce di spingere un pacchetto vecchio), scarica, controlla sha256 e
  installa con il procedimento di sempre (`selfupdate.run_install`: firma, snapshot, ritorno automatico). Impostazioni in
  `/etc/nido/selfupdate.json` (`channel` stable/beta, `mode` notify/nightly/off, `url` facoltativo); indirizzo di base
  `NIDO_UPDATE_URL` (config.env → nido.conf, anche via identity.conf del pacchetto). Timer `nido-selfupdate-check` ogni notte
  (04:15 ± 45 min, e 15 min dopo l'avvio): avvisa una volta per versione o installa. API `/api/selfupdate/online[/check|/install]`,
  `/api/v1/system/update`; `system_update` in `/api/v1/status`; entità `update` "Sistema" nell'integrazione HA (0.3.0).
  Pubblicazione: `kit/strumenti/pubblica-aggiornamento.{sh,ps1}` (copia il .deb in `pool/`, firma, scrive e firma il manifesto).
  Provato qui con chiave di prova e server locale: controllo, scaricamento, sha256, firma; manifesto manomesso rifiutato.

- **Fonti CasaOS, ZimaOS e Unraid in un pacchetto a parte** (richiesta dell'utente: solo per lui, NON nella ISO né in nido-nas):
  `kit/make-extra-deb.sh` → `rnfads-extra-store_<ver>_all.deb` (Package `nido-extra-store`, Depends `nido-nas (>= 1.1~)`), che
  aggiunge `nidopanel/stores_extra.py` (convertitori v2/Unraid della 0.3 + `SOURCES_FIRST/LAST`, `KINDS`, `build()`) e una
  nota legale. `catalog.py` lo importa se c'è (fonti, priorità, fonti personalizzate v2), `about.stores_extra` mostra le note sui
  marchi solo in quel caso. `selfupdate` accetta anche i pacchetti `nido-extra-*` (senza ritorno automatico: se l'interfaccia
  non riparte il pacchetto viene tolto). Provato: catalogo con e senza il modulo; feed Unraid convertito.
- **Installer in inglese all'avvio** (prima voce e predefinita del menu lingua; menu GRUB della chiavetta in inglese).
- **VMSVGA, seconda correzione**: con il solo blocco di vmwgfx la console restava ferma sulla riga di avvio (foto dell'utente).
  `/usr/lib/nido/vm-video.sh` cerca la scheda PCI 15ad:0405 e solo lì scrive `/etc/default/grub.d/16-nido-vmsvga.cfg` con
  `nomodeset` (provato dall'utente a mano); lo chiamano l'installer (prima di update-grub) e il postinst del pacchetto. Sui PC
  veri niente nomodeset (servirebbe a Jellyfin/Plex per la transcodifica). Nella chiavetta nomodeset in tutte le voci.
- **Chiave pubblica** dell'utente in `kit/chiavi/aggiornamenti-pubblica.pem` (Ed25519): finisce nel pacchetto
  (`/usr/share/nido/update-keys/`) e quindi nella ISO.

### 3.10 Versione 1.0.1 (1/11/2026) — correzioni dopo la prova dell'utente, ISO ricostruita
- **Schermo nero VMSVGA, correzione vera**: nella 1.0 il blocco di `vmwgfx` stava in `/etc/modprobe.d/`, ma l'initramfs di
  Ubuntu 26.04 copia solo `/usr/lib/modprobe.d/` (hook `kmod`) e `vmwgfx` viene caricato già dall'initramfs, quindi la regola
  non agiva. Ora: `/usr/lib/modprobe.d/nido-vmwgfx.conf` (finisce nell'initramfs, verificato con `lsinitramfs`) **e**
  `modprobe.blacklist=vmwgfx` nella riga di avvio (`/etc/default/grub.d/15-nido-video.cfg`, verificato: aggiunto una volta sola),
  la stessa opzione che l'utente ha provato a mano; anche nelle voci del menu della ISO. Il pacchetto toglie il file vecchio e
  rifà initramfs e GRUB quando questi file cambiano (`/var/lib/nido/boot.sum`).
- **"Lingua non supportata"** cambiando lingua: `act()` metteva la rotellina dentro il `<select>` e cancellava le voci, quindi
  partiva una lingua vuota. Ora il valore si legge prima.

### 3.9 Versione 1.0 (1/11/2026) — prima versione stabile, **ISO ricostruita**
- `NIDO_VERSION="1.0"` (versione del pacchetto `1.0+AAAAMMGGhhmm`, più nuova di tutte le 0.3~beta1).
- **Accesso remoto** (Impostazioni → Accesso remoto, `nidopanel/remote.py`, API `/api/remote/...`):
  - **Tailscale**: "Installa" aggiunge l'archivio ufficiale `pkgs.tailscale.com` (chiave in `/usr/share/keyrings`, se non c'è la
    versione di Ubuntu installata usa i pacchetti di `noble`) e installa `tailscale` come operazione lunga (`cli remote-install`,
    registro `/var/log/nido/remote.log`); "Collega" lancia `tailscale up --accept-dns=false --hostname=<nome>` e mostra il link
    di accesso; IP 100.x, nome MagicDNS, dispositivi online; interruttore "Rendi raggiungibile la rete di casa" (subnet router:
    `tailscale set --advertise-routes=<LAN>` + `ip_forward` in `/etc/sysctl.d/99-nido-remote.conf`); Scollega, Disinstalla.
  - **ZeroTier**: archivio ufficiale `download.zerotier.com` (chiave da GitHub), solo l'agente MPL-2.0 (il controller "nonfree" non
    si usa); entra/esci da una rete con l'ID di 16 caratteri, stato (da autorizzare / collegato), IP assegnati.
  - Niente nella ISO: si scarica solo quando l'utente preme "Installa". SSH "solo rete di casa" accetta già 100.64.0.0/10 e le reti
    private; mDNS esclude già `tailscale*` e `zt*`. Note legali (licenze BSD-3/MPL-2.0, marchi, WireGuard).
- **Fonte Runtipi** nello store (`catalog._ingest_runtipi`, catalogo GPL-3.0 scaricato da GitHub): le app con
  `docker-compose.json` (formato dinamico v2, 232 su 270) diventano compose normali con `x-casaos`: `${APP_DATA_DIR}` →
  `/DATA/AppData/$AppID`, `${ROOT_FOLDER_HOST}` → `/DATA`, `${APP_PORT}` → porta dell'app, password e chiavi dei campi
  "random"/"password" create da sole (scritte nei suggerimenti), etichette Traefik tolte. Provato: 232 compose validi per
  `docker compose config`, 232 letti dalla finestra d'installazione. Non provata un'installazione vera (serve internet).
- Traduzioni: aggiunti i testi nuovi e quelli che l'estrazione aveva perso (espressione regolare in `app.js`); circa 1.830 testi.

### 3.8 Aggiornamento del 31/10/2026 sera (pacchetto, **ISO non rifatta**: si rifà quando tutto funziona)
- **Fonti dello store**: tolte CasaOS ufficiale, ZimaOS e Unraid CA (`catalog.py`; `stores.py` ridotto alle funzioni di
  scaricamento, tolti i convertitori v2/Unraid e il comando `stores-build`). Il catalogo già scaricato perde da solo le app di
  quelle fonti (`catalog._prune`); fonti personalizzate solo `.zip`. Note legali e pagine aggiornate.
- **Account Docker Hub** (Impostazioni → App store): nome utente + token di accesso, controllati con auth.docker.io prima di
  salvarli (token cifrato in `/etc/nido/registry.json`), `docker login` così anche i download delle immagini usano l'account,
  "Controlla" mostra i download rimasti (intestazioni ratelimit), "Esci" (`docker logout`). API `/api/registry/account`.
- **Lingue** (Impostazioni → Generale → Lingua): italiano, inglese, spagnolo, tedesco, per tutti gli account e la pagina di accesso
  (`/etc/nido/ui-language.json`, `POST /api/system/language`, `about.lang`). Motore `ui/i18n.js`: traduce i testi mentre
  compaiono (MutationObserver) con i dizionari `ui/lang/{en,es,de}.json` (circa 1.450 testi esatti + 235 modelli con segnaposto
  `{0}`, anche i messaggi d'errore del server); non tocca nomi di file e cartelle, campi, terminale, registri e testi `.mono`.
  Date e numeri con il formato della lingua (`LOCALE`). Per aggiungere testi: scriverli in italiano nel codice e aggiungere la
  riga ai dizionari (strumenti di estrazione nella sessione del 31/10, non nel kit). Provato: 19 pagine × 4 lingue senza errori
  JavaScript; in inglese restano in italiano solo i nomi delle cartelle predefinite.
- Marchio RNFADS: verifica considerata chiusa (§7.2).

### 3.6 Modifiche della fase 1C al kit (30/10/2026, sera — **da provare sulla ISO**)
- Regola della fase: **niente prove in VM**. La ISO si costruisce e si consegna; la prova l'utente e riporta gli errori.
  Prove fatte: API con curl e pagine con Playwright nel chroot Ubuntu 26.04 (senza systemd, Docker e dischi veri).
- Pacchetti aggiunti: `python3-pil` e `ffmpegthumbnailer` (miniature), `7zip` e `zip` (archivi; 7zip apre anche i RAR),
  `ubuntu-release-upgrader-core` (passaggio di versione).
- Servizi nuovi (abilitati dall'hook): `nido-uptime` (segna lo spegnimento regolare), `nido-release-verify` (controlli
  dopo il passaggio di versione, parte solo se c'è `/var/lib/nido/release-verify-pending.json`).
- File nuovi: `nidopanel/uptime.py`, `nidopanel/appmove.py`, `nidopanel/release.py`, `/usr/lib/nido/rebrand.sh`.
- Home: app e dischi letti in un thread (la pagina non aspetta Docker più di 2,5 s), tempo massimo per le richieste nel
  browser, errori di pagina con "Riprova" (era la Home "sulla rotellina").
- Store: Unraid scaricato compresso con 3 tentativi e indirizzo di riserva; fonte attivata durante un aggiornamento del
  catalogo non più ignorata. L'errore di Unraid segnalato dall'utente **non è stato analizzato** (lasciato stare su sua
  richiesta, senza messaggio d'errore).
- Integrazione Home Assistant 0.2.0: sensori "Ore totali di accensione", "Avvii", "Spegnimenti improvvisi", "Ultimo spegnimento".
- Build del 31/10/2026 00:02 con `build.sh` nel chroot 26.04: riuscita al primo colpo, nessuna correzione di build necessaria
  (SHA256 completo in `STATO-FASE1B.md`).

### 3.5 Integrazione Home Assistant (30/10/2026)
- Cartella `home-assistant/`: integrazione nativa `custom_components/rfd_nas` (config flow, chiave API, HACS) con sensori,
  sensori sì/no, un interruttore per app e pulsanti (riavvia, spegni, cerca aggiornamenti, standby dei dischi, riavvia e
  aggiorna le app). Vedi `home-assistant/README.md`.
- Sul NAS: `/api/v1/status` arricchito (app, standby dei dischi, spegnimento programmato) e comandi `POST /api/v1/...`
  con la chiave API (`server.py`, `ha_api`). Provate le API nel chroot; l'integrazione **non è ancora provata in Home
  Assistant** e le nuove API non sono nella ISO del 30/10 (vanno nella prossima build).

## 4. Cosa costruire: l'interfaccia

Un servizio nostro, evoluzione del Centro di controllo (Python, libreria standard + `cryptography` + `PyYAML`),
con login proprio, sessioni sicure e API JSON. Frontend HTML/CSS/JS **senza CDN**, tutto incluso nella ISO.
Stile del prototipo `k*`: colorato, ogni sezione con il suo colore e la sfumatura del marchio (§6), tema chiaro e
scuro, responsive con barra in basso sul telefono. Lingua italiana.

Legenda: ✅ fatto nella fase 1A · 🟡 in parte · ⬜ fase 1B

1. ✅ **Home**: CPU, RAM, velocità di rete in download e upload con grafico in tempo reale (ultima ora,
   campionamento ogni 3 s), temperatura (CPU e dischi se ci sono i sensori), spazio dei dischi, app installate con
   stato (un clic le apre). **1C**: striscia del **tempo di accensione** (acceso da, aggiornato dal vivo; ore totali contate
   dal NAS ogni minuto in `/var/lib/nido/uptime.json`; avvii; ultimo spegnimento regolare o improvviso, riconosciuto dal
   segno che `nido-uptime` scrive allo spegnimento). App e dischi arrivano da una cache: la Home non resta più sulla rotellina.
2. ✅ **App store** con tutte le fonti in un unico catalogo con filtri per fonte e categoria: Big Bear, LinuxServer,
   CoolStore e **ricerca su Docker Hub** (dal 31/10/2026 sera **tolte CasaOS ufficiale, ZimaOS e Unraid CA**, scelta
   dell'utente per evitare problemi con i marchi; restano solo zip di app in formato compose, anche come fonti personalizzate).
   Un'app presente in più fonti è mostrata una volta sola, con la scelta della fonte nei dettagli.
   - ✅ **Installazione** in tre modalità: semplice, avanzata e Compose. Porte libere (anche la stessa porta in TCP
     e UDP), cartelle, PUID/PGID e fuso orario impostati da soli. Per le immagini di Docker Hub porte, cartelle e
     variabili sono lette dal registro (manifest + config) senza scaricare l'immagine.
   - ✅ Fonti personalizzate (zip CasaOS o store ZimaOS v2).
3. ✅ **Le mie app**: avvio, arresto e riavvio, log (in diretta), aggiornamento della singola app e "aggiorna tutte",
   controllo delle nuove versioni (stesso tag con contenuto nuovo, oppure versione di correzione più alta),
   aggiornamento automatico notturno (solo patch). Copia della configurazione prima di aggiornare; se l'app non
   riparte si torna alla versione precedente da soli e quella versione non viene più riproposta.
   Limiti di CPU e RAM per app. Anche i contenitori avviati fuori dal NAS (avvio/arresto/log).
   **1C — Modifica l'installazione** (menu ⋯): la finestra dell'installazione (semplice, avanzata, Compose) riaperta e già
   compilata con porte, cartelle, variabili, immagine e tag, limiti, avvio con il NAS; controllo dei conflitti di porta;
   copia della configurazione in `versions/`; `docker compose config` prima di toccare i contenitori; `up -d`; controllo
   della salute e ritorno da solo alla configurazione di prima se l'app non riparte. I dati in AppData restano.
4. ✅ **File manager**: tutti i dischi e le cartelle; caricamento a blocchi da 8 MB con barra (anche cartelle e
   trascinamento), download (cartelle e selezioni multiple in zip), copia, sposta, rinomina, cestino (per disco, con
   ripristino), anteprime (foto con navigazione, video e audio con Range, PDF, testo), pannello dei dettagli (anche
   EXIF: data e fotocamera), ricerca, link di condivisione con scadenza e pagina dei link.
   **Fase 1C** (tutto anche dal **tasto destro**: menu su file, selezione, spazio vuoto, preferiti, cestino):
   - **Appunti**: Ctrl+X/C/V, barra "da copiare/da spostare · Incolla qui" (resta cambiando cartella o disco, anche verso
     le cartelle di rete), "Incolla nella cartella"; incollare nella stessa cartella crea "nome - copia".
   - **Selezione**: clic, Ctrl, Shift, **rettangolo col mouse** (con scorrimento), Ctrl+A, frecce, Esc; Canc (Maiusc+Canc
     elimina per sempre), F2, Invio, Backspace.
   - **Trascinamento** su cartelle, briciole del percorso, dischi e preferiti della barra laterale: sposta, con Ctrl copia;
     file del PC trascinati su una cartella vengono caricati lì; cartella trascinata su "Preferiti" = preferito.
   - **Conflitti di nome** (copia, spostamento, caricamento): Sostituisci (per due cartelle: **Unisci**), Salta, Tieni
     entrambi ("nome (2)"), con "Fai così per tutti" e confronto di dimensioni e date.
   - **Coda delle operazioni** (`jobs.py`, coda "files"): una alla volta, in background sul NAS (proseguono chiudendo la
     pagina), pannello con avanzamento, velocità, tempo che manca, byte copiati, **Annulla** (il file a metà viene tolto:
     la copia passa da un nome provvisorio nascosto e poi `os.replace`). Copie tra dischi diversi con copia+cancellazione.
   - **Miniature** generate dal NAS (Pillow; video con ffmpegthumbnailer) in `/var/lib/nido/thumbs` (max 2 GB, le più
     vecchie se ne vanno), 256 px nella griglia e 512 px nei dettagli, con l'orientamento EXIF.
   - **Vista a griglia o a elenco**, ordinamento per nome (numerico, "foto 2" prima di "foto 10"), data, dimensione e tipo
     (cartelle sempre prima), crescente/decrescente, anche dalle intestazioni dell'elenco.
   - **Archivi**: Comprimi in ZIP, 7z, TAR.GZ; Estrai qui da zip, 7z, rar, tar, tar.gz/xz/bz2 (in una cartella provvisoria
     nascosta; se dentro c'è una sola cartella esce quella, altrimenti una cartella con il nome dell'archivio; percorsi che
     escono dalla cartella ignorati; archivi con password: messaggio chiaro).
   - **Editor di testo** (`.env`, compose, configurazioni, fino a 4 MB): numeri di riga, Tab, Ctrl+S, "a capo", riga e
     colonna, file CRLF e latin-1 conservati, permessi e proprietario conservati, **controllo che il file non sia cambiato**
     nel frattempo (409 → "Sovrascrivi comunque?"); "Nuovo file di testo".
   - **Preferiti** nella barra laterale (dischi in alto, poi preferiti): aggiungi/togli dal tasto destro o trascinando.
   - **Dimensione delle cartelle** su richiesta (tasto destro o pannello dei dettagli, massimo 25 s, poi "almeno …").
   - **Permessi**: proprietario e gruppo, Nessuno / Lettura / Lettura e scrittura per proprietario, gruppo e altri (le
     cartelle leggibili restano attraversabili), anche su tutto il contenuto (in coda).
   - **Caricamento che riprende**: se cade la connessione il browser riprova (fino a 40 volte, attesa crescente) e chiede al
     NAS da dove ripartire; ricaricando lo stesso file (stesso nome e dimensione) anche dopo aver chiuso la pagina riparte
     dal punto arrivato (file provvisorio `.<nome>.<dimensione>.nidopart`, tolto dopo 3 giorni).
   - 🟡 **Cartelle di rete**: SMB, NFS e WebDAV, scoperta dei PC in rete (mDNS + NetBIOS), elenco delle cartelle
     condivise, credenziali salvate cifrate (Fernet, chiave generata sul NAS), ricollegamento all'avvio.
     Il montaggio SMB/NFS vero non è stato possibile nell'ambiente di prova (kernel senza moduli cifs/nfs):
     ⬜ da provare in VM.
5. ✅ **Dischi** (1B-1): salute SMART (vita residua degli SSD, temperatura, ore, accensioni, settori difettosi,
   ultimo test, attributi, test breve e completo; non sveglia i dischi in standby); formattazione (ext4, Btrfs, exFAT,
   NTFS, FAT32, XFS) con conferma scrivendo il nome (controllata anche dal server) e avanzamento; montaggio di dischi
   già formattati in `/media/<nome>` (sola lettura, a ogni avvio, condivisione; ntfsfix e poi l'altro driver per NTFS
   chiusi male; messaggio chiaro per l'ibernazione di Windows); standby per disco (Mai, 5, 10, 20, 30 min, 1, 2, 4 h,
   personalizzato), APM, eccezione oraria per i backup, **programma settimanale** (1B-2: fasce di standby e fasce
   "sempre accesi"), "spegni adesso", accensioni del giorno; disco di sistema escluso;
   spazio delle app (Docker) con pulizia delle immagini. **1C — Dove stanno le app** (`appmove.py`): "Sposta su un altro
   disco" (ext4/XFS/Btrfs, montato a ogni avvio, spazio sufficiente; conferma scrivendo SPOSTA): app e Docker fermati,
   copia con `rsync -aHAX --numeric-ids` e secondo passaggio di controllo (nessuna differenza, se no si ferma senza
   cambiare niente), poi le cartelle copiate vengono **montate (bind) sugli stessi percorsi** `/var/lib/docker`,
   `/DATA/AppData` (e `/var/lib/containerd` se Docker tiene lì le immagini) da fstab (righe vecchie commentate con
   `#nido-spostato#`, copia in `/etc/fstab.nido-prima-dello-spostamento`), drop-in `RequiresMountsFor` per Docker; le app
   ripartono e se non ripartono si torna da soli alla situazione di prima. "Riporta sul disco di sistema" (RIPORTA) e
   "Libera lo spazio sul disco di sistema". Con il driver Docker "btrfs" verso un disco non Btrfs le immagini vengono
   esportate e ricaricate (`docker save`/`load`). Lo standby **non usa `hdparm -S` né hd-idle**: lo fa il servizio
   `nido-standby` leggendo `/proc/diskstats` e mandando `hdparm -y` (così funzionano anche l'orario dei backup, il
   conteggio delle accensioni e i dischi USB dove `-S` non va).
6. ✅ **Condivisioni, utenti, backup e notifiche** con la nuova grafica (1B-1). Condivisioni anche "per tutti gli utenti".
7. ✅ **Aggiornamenti di sistema** (Impostazioni, 1B-1): "Cerca aggiornamenti" e "Aggiorna ora", elenco diviso in
   sicurezza, RFD-NAS (pacchetti che iniziano con il nome del sistema, per il futuro archivio apt) e sistema, snapshot
   prima e dopo, registro in diretta, impostazioni automatiche (ricerca, sicurezza da sole, riavvio di notte), avviso di
   riavvio, elenco degli snapshot con ripristino. Anche **Generale** (informazioni, riavvia, spegni, **spegnimento e
   accensione programmati** — 1B-2) e **Home Assistant e
   API** (package per `/config/packages/` con `!secret`).
   **1C — Versione di Ubuntu** (`release.py`): "Controlla" legge `changelogs.ubuntu.com/meta-release` e propone **sempre la
   versione successiva, anche non LTS**, con l'avviso LTS (5 anni) / non LTS (9 mesi); decide l'operatore (conferma
   scrivendo la versione). Il passaggio (unità `nido-job-release-upgrade`, registro in diretta, prosegue chiudendo la pagina):
   almeno 6 GB liberi → sistema attuale aggiornato → **snapshot "prima del passaggio"** → `do-release-upgrade -f
   DistUpgradeViewNonInteractive` (Prompt impostato a "normal") → `rebrand.sh` rimette nome, versione, issue, motd, loghi
   tolti, dpkg-divert di 80snapper e GRUB → servizi `nido-*` riabilitati → snapshot "dopo". Dopo il riavvio
   `nido-release-verify` controlla versione, nome, 80snapper, interfaccia, Caddy, Docker, standby, mDNS, Samba, SSH, servizi
   falliti e contenitori; il risultato compare nella pagina e come notifica. "Torna alla versione di prima" = ripristino
   dello snapshot (snapper undochange) + riavvio. **Va provato sulla build prima di pubblicarlo.**
8. ✅ **Terminale** (1B-1): xterm.js 5.5.0 + addon-fit 0.10.0 (MIT) inclusi, più schede (come l'amministratore con lo
   stesso nome dell'account, come root, dentro ogni app con `docker exec`), schede che restano aperte cambiando pagina,
   tasti speciali sul telefono. WebSocket scritto nel server (`terminal.py`), solo amministratori e solo dalla stessa
   origine. **SSH**: acceso/spento, password, solo rete di casa (`Match Address` + `DenyUsers *`), porta, chiavi.
9. ✅ **HTTPS** con Caddy (1B-1): certificato "di casa" scaricabile (anche in HTTP da `/certificato-casa.crt`, con le
   istruzioni per Windows, Mac, iPhone e Android), Let's Encrypt, certificato caricato, reindirizzamento HTTP→HTTPS,
   sottodomini per le app (`jellyfin.rfd-nas.local`, pubblicati con mDNS). Porta 80 di riserva se Caddy non parte.
10. 🟡 Suggerimenti graditi: ✅ ricerca globale Ctrl+K (pagine, app installate, store, Docker Hub);
    ✅ account creato dall'installer o al primo accesso; ⬜ verifica in due passaggi; ✅ accesso da fuori casa con
    Tailscale e ZeroTier (1.0; ⬜ Cloudflare Tunnel); ✅ procedura guidata al primo avvio (1D).
11. ✅ **Pagina "Sostieni il progetto"** (richiesta il 28/10/2026): link configurabili in `config.env`
    (PayPal, Ko-fi, GitHub Sponsors, Liberapay); se mancano lo dice. Collegata dalla barra laterale.

## 5. Vincoli dell'utente

- Lingua dell'interfaccia: italiano.
- Credenziali e chiavi mai nel codice: vanno in file di configurazione separati o generate
  all'installazione (rispettato: chiave di cifratura, chiave API e account sono creati sul NAS).
- L'utente vuole che sia l'assistente a fare tutto: costruire la ISO, provarla in VM e consegnarla.
- Lavoro a tappe: a ogni tappa che funziona si salva uno zip aggiornato e si comunica la percentuale.
  Quando l'utente scrive "fermati" si chiude al primo punto stabile e si consegna lo zip con una nota.
- La ISO pesa circa 1,7 GB e l'invio in chat ha un limite di 400 MB. Va consegnata in parti
  (`split -b 350M`) con le istruzioni per unirle e lo SHA256, oppure tramite Release GitHub se il
  repository è collegato.

## 6. Identità grafica

- Logo (variante "C" scelta dall'utente): **arco di una caverna** disegnato con la sfumatura del marchio
  (dal basso a sinistra ciano → indaco → rosa → arancio), con dentro **tre dischi** orizzontali
  (ciano→indaco, rosa→viola, arancio→giallo), ognuno con spia e fessura bianche. `logo/logo-rnfads.svg`, icone
  app chiara e scura, foglio `rnfads-logo.png`. Il codice JS che lo disegna è `cube()` in `ui/app.js` (nome
  della funzione rimasto quello del vecchio logo) e nel prototipo. Favicon: `ui/img/favicon.svg`.
- Scritta (dal 31/10/2026): **RNFADS** a lettere alternate, R F D scure in Orbitron 800, N A S con la sfumatura
  `linear-gradient(120deg,#06b6d4,#6366f1 38%,#ec4899 72%,#f97316)` in JetBrains Mono 800 (`NIDO_WORDMARK="R|N|F|A|D|S"`,
  funzione `word()` in `ui/app.js`, classi `.wm-a` e `.wm-b`). Foglio del logo `logo/rnfads-logo.png` rifatto.
- Font: Inter per l'interfaccia; Orbitron e JetBrains Mono per la scritta del marchio (tutti SIL OFL 1.1, inclusi
  localmente in `ui/fonts/` con le licenze, presi dai pacchetti Fontsource 5.3.0).
- Colori delle sezioni: Home #3b82f6, App store #ec4899, File #f59e0b, Dischi #14b8a6,
  Condivisioni #8b5cf6, Utenti #22c55e, Backup #f97316, Terminale #64748b, Impostazioni #6366f1.

## 7. Licenze e marchi

### 7.1 Già fatto nei file
- `LICENSE` (GPL-3.0) nel progetto e nel kit; nel sistema `/usr/share/doc/nido/licenses/GPL-3.0.txt` e nella
  ISO in `licenze/`. La pagina "Informazioni e licenze" dell'interfaccia mostra licenza, note legali e marchi.
- `THIRD_PARTY_NOTICES.txt`: CasaOS tolto; l'interfaccia è scritta da zero e legge solo il formato pubblico dei
  cataloghi; aggiunti PyYAML, Avahi, nfs-common, davfs2; copia del font Inter con la sua licenza; frase di non
  affiliazione con Canonical, Docker, IceWhale e Lime Technology; nota sul marchio Docker; offerta scritta per i
  sorgenti GPL. Segnaposto `@NAME@` e `@VERSION@` sostituiti dall'hook.
- `fetch-sources.sh` e `build.sh` producono `packages.txt` e `sources.txt` (parte `apt-get source` provata,
  parte Launchpad no).
- Hook: `DISTRIB_DESCRIPTION` "<Nome> <versione> (basato su Ubuntu …)", `DISTRIB_ID` invariato, loghi Ubuntu
  rimossi ed esclusi con `dpkg path-exclude`, messaggi di benvenuto di Ubuntu disattivati, motd corretto.
- Interfaccia: nessun logo Docker (icona generica a container), "Docker Hub" scritto solo per compatibilità,
  fonti ZimaOS e Unraid facoltative e con nota di non affiliazione, nota di attribuzione in fondo allo store,
  nomi e icone delle app scaricati dagli store (nessuna icona nella ISO).

### 7.2 Ancora da fare
1. ✅ **Verifica del nome RNFADS** (31/10/2026, fatta e confermata dall'utente): TMview, WIPO Global Brand Database e USPTO,
   nessun marchio RNFADS. Considerata chiusa (facoltativo un parere di un consulente prima di pubblicare).
2. ✅ (1B-1) xterm.js (MIT, con il testo della licenza in `ui/vendor/xterm/`) e Caddy (Apache-2.0) sono nelle note
   legali e nella pagina "Informazioni e licenze", con le frasi di non affiliazione; aggiunti anche OpenSSH,
   smartmontools, hdparm e gli strumenti dei file system.
3. Pubblicazione: per ogni versione caricare accanto alla ISO i sorgenti scaricati con `fetch-sources.sh`,
   l'elenco dei pacchetti e le note legali.
4. ✅ (31/10 sera) Docker Hub: schermata dell'account in Impostazioni → App store (token cifrato, `docker login`,
   download rimasti).
5. Link per le donazioni: l'utente deve dare gli indirizzi (PayPal, Ko-fi, …) da mettere in `config.env`.

## 8. Fase 1A: com'è fatta e come è stata provata

### 8.1 Architettura
- Un solo servizio (`nido-ui`, `python3 -m nidopanel.server`, root), dalla 1B-1 su `127.0.0.1:8090` dietro Caddy
  (porte 80 e 443). Risponde con l'interfaccia su `/`, le API su `/api/`, il terminale su `/api/term/ws` (WebSocket),
  i link pubblici su `/s/<token>`, la CA di casa su `/certificato-casa.crt`, lo stato per Home Assistant su
  `/api/v1/status` (chiave API). Il Centro di controllo su `/nido/` è stato tolto nella 1B-1.
- Accesso: account in `/etc/nido/ui-users.json` (0600, scrypt N=2^15), sessioni in `/var/lib/nido/ui-sessions.json`
  (solo l'impronta SHA-256 del token), cookie `HttpOnly; SameSite=Strict` (+`Secure` dietro HTTPS), 12 ore o
  30 giorni con "Ricordami"; 5 errori → blocco crescente da 30 s; CSRF con `X-Nido: 1`; CSP senza script esterni.
- App: progetti Docker Compose in `/var/lib/nido/apps/<nome>/` (vedi `kit/README.md`). Il controllo delle
  versioni usa il protocollo dei registri (token anonimo, `HEAD` del manifest, elenco dei tag). Per la
  "salute" dopo un aggiornamento: tutti i contenitori accesi da 10 s, nessun riavvio, healthcheck ok e
  interfaccia web che risponde; un contenitore che si riavvia di continuo fa scattare subito il ritorno indietro.
- Catalogo: zip delle fonti → `/var/lib/nido/catalog/` (indice + compose per fonte); se una fonte non risponde
  resta l'ultima versione buona. Categorie in italiano assegnate per parole chiave (le fonti ne usano poche
  e generiche).

### 8.2 Ambiente di prova (28/10/2026)
- Chroot **Ubuntu 26.04 LTS** (debootstrap resolute) con **Docker 29.1.3**, Docker Compose 2.40, Python 3.14,
  Samba 4.23; interfaccia avviata con `NIDO_LISTEN=127.0.0.1:8080`; browser Chromium con Playwright.
- Limiti dell'ambiente, da coprire in VM nella fase 1B:
  - Docker Hub e i siti degli store **non erano raggiungibili**. Gli store sono stati clonati da GitHub
    (cataloghi reali: CasaOS 181, Big Bear 491, LinuxServer 249, CoolStore 45 app) e serviti in locale; le immagini
    erano piccole immagini di prova (busybox) **con gli stessi nomi delle app vere**, pubblicate in un registro
    locale (`docker-registry`, stesso protocollo di Docker Hub, ma senza token: il giro del token anonimo di
    Docker Hub non è stato provato); la ricerca su Docker Hub usava un finto servizio con lo stesso formato JSON.
  - Il kernel non aveva i moduli **cifs** e **nfs**: il montaggio SMB/NFS vero non è stato provato (il NAS
    risponde con un messaggio chiaro). WebDAV invece è stato montato davvero (FUSE).
- Risultati:
  - accesso: creazione del primo account, password corta rifiutata, blocco dopo 5 errori, richiesta senza
    `X-Nido` rifiutata, percorsi fuori da /DATA, /media, /mnt, /srv rifiutati (anche con `..`);
  - catalogo: 966 app dalle 4 fonti → **632 app senza doppioni** (293 presenti in più fonti);
  - installati da store e da Docker Hub: Uptime Kuma (CasaOS), Syncthing (LinuxServer: porte 22000 in TCP e UDP),
    Heimdall (Docker Hub: porta 80 occupata → 8081 scelta da sola, 443 → 8444, PUID/PGID/TZ impostati);
  - aggiornamenti: 2.4.0 → 2.4.1 (correzione; la 2.5.0 resta manuale), "stesso tag con contenuto nuovo",
    "Aggiorna tutte", aggiornamento notturno (Heimdall con tag `latest` correttamente non toccata di notte);
  - **ritorno automatico**: versione 2.4.2 rotta pubblicata apposta → riconosciuta in 24 s con il motivo preso dai
    log, ritorno alla 2.4.1, la 2.4.2 non viene più proposta;
  - file: caricamento a blocchi di 20 MB verificato con SHA-256, Range (206) per i video, zip delle cartelle,
    cestino e ripristino, ricerca, EXIF, link pubblico senza accesso (200) e link falso (404);
  - cartelle di rete: elenco delle cartelle di un Samba vero (ospite e con password, password errata
    riconosciuta), scoperta di computer annunciati in rete, WebDAV montato/smontato/ricollegato all'avvio,
    password cifrata nel file (0600) e assente in chiaro da log e configurazioni;
  - interfaccia: tutte le pagine senza errori JavaScript, tema chiaro e scuro, telefono a 390 px senza
    scorrimento orizzontale, Centro di controllo raggiungibile con il nuovo accesso.
- Bug trovati e corretti durante le prove: stesso corpo della richiesta riusato sulle connessioni HTTP persistenti
  (il browser riceveva risposte sbagliate), porta UDP spostata inutilmente quando la stessa porta serve anche in
  TCP, rilevamento lento dei contenitori che si riavviano di continuo.
- Schermate: `schermate/1A/`.

### 8.3 Fase 1B-1: come è stata provata (29/10/2026)
- Stesso chroot Ubuntu 26.04 della §8.2 (Docker 29.1.3, Caddy 2.6.2, OpenSSH 10.2, Python 3.14); interfaccia su
  `127.0.0.1:8090` con `NIDO_TEST_LOOP=1`, Caddy davanti su 80/443; 4 dischi finti da 2 GB (file collegati con
  `losetup -P`). Nota: se la macchina monta i cgroup alla vecchia maniera, Docker 29 va in panic all'avvio: nel
  chroot serve `mount -t cgroup2 none <chroot>/sys/fs/cgroup`.
- Risultati: montati e smontati NTFS (ntfs-3g), exFAT, Btrfs ed ext4 in sola lettura, con fstab giusto; formattati
  dal browser e da Python ext4, XFS, Btrfs, NTFS ed exFAT; conferma sbagliata e disco di sistema rifiutati; standby:
  spegnimento dopo il tempo scelto, riaccensione rilevata e contata, "spegni adesso"; il file manager vede i dischi in
  `/media`. Creato un utente, condivisa una cartella (smb.conf giusto), backup eseguito e ripristinato con il registro
  in diretta, notifica webhook ricevuta, 22 aggiornamenti cercati e installati con il registro in diretta. Terminale:
  comandi, Ctrl+C, shell dentro un contenitore, anche via `wss://` attraverso Caddy; SSH vero con la chiave, password
  rifiutata, `sshd -t` valido; WebSocket da un'altra origine rifiutato (403) e senza accesso (401). HTTPS: CA di casa
  riconosciuta da curl, 308 da HTTP, cookie `Secure`, sottodominio di un'app (200), configurazioni Let's Encrypt,
  caricato e "solo HTTP" validate da Caddy, chiave che non corrisponde rifiutata, porta di riserva aperta e chiusa.
  Tutte le pagine senza errori JavaScript, tema chiaro e scuro, telefono a 390 px senza scorrimento orizzontale.
- Errori trovati e corretti: dischi montati in `/DATA/<nome>` invisibili al file manager (ora `/media/<nome>`); la
  lettura dell'elenco dei dischi con blkid faceva attività sui dischi e impediva lo standby (ora una lettura sola, in
  cache); etichette con spazi lette male da blkid; `smartctl -n standby` non riconosciuto (codice di uscita 2).
- Limiti dell'ambiente, da coprire in VM: niente systemd nel chroot (le operazioni lunghe partono come processi
  staccati, `start_job` lo fa da solo), quindi non provati `systemctl` di Caddy/SSH, il riavvio automatico della porta
  di riserva e il servizio `nido-mdns`; FAT32 non montabile con questo kernel (il formato viene creato); `hdparm -y`
  e SMART solo con dischi veri o virtuali (i loop sono simulati); snapshot (serve il sistema su Btrfs); Let's Encrypt
  vero (serve un dominio con le porte aperte).

### 8.4 Fase 1B-2: build della ISO e prove in VM (30/10/2026)
- **Build**: `build.sh` in un chroot Ubuntu 26.04 (`debootstrap resolute`) su un host Ubuntu 24.04, 2 CPU: riuscita al primo
  colpo, ~16 minuti, ISO da 1,7 GB (`rfd-nas-0.2-beta1-amd64.iso`). Unici avvisi: attributi ACL non copiati da mksquashfs
  (innocui).
- **VM**: QEMU 8.2 senza KVM (TCG), 2 CPU, 3 GB, disco di sistema virtio da 64 GB, due dischi SATA (AHCI) da 4 GB per i
  dati (uno con una partizione NTFS fatta "da Windows", uno vuoto). Rete `user` con 8080→80, 8443→443, 2222→22.
  Samba e NFSv4 (nfs-ganesha) sull'host, raggiunti dalla VM su 10.0.2.2. Webhook di prova sull'host per le notifiche.
- **BIOS**: live avviato (menu GRUB, installer whiptail in ~5 min), installazione interattiva completa (~10 min), avvio
  dal disco: `systemctl is-system-running` = running, nessuna unità fallita, account dell'interfaccia creato
  dall'installer (admin), HTTPS attivo dopo il primo avvio, 21 pagine senza errori JavaScript (Playwright).
- **UEFI + Secure Boot** (OVMF secboot con chiavi Microsoft, ISO ricostruita con tutte le correzioni): live avviato,
  installazione interattiva completa (~10 min), avvio del disco installato con Secure Boot attivo, `running`, nessuna unità
  fallita, account creato dall'installer, HTTPS attivo, 21 pagine senza errori JavaScript; presenti `dpkg-divert` di
  80snapper, `caddy.service.d/10-nido.conf`, `allow-interfaces` di avahi (`rfd-nas.local` → IP giusto).
- **Prove funzionali** (tutte sulla VM, dall'interfaccia/API): NTFS montato con ntfs3 e letto; FAT32 formattato e montato;
  SMART di un disco SATA virtuale (salute, temperatura, attributi); standby con `hdparm -y` per disco, da "spegni adesso" e
  dal programma settimanale (dischi con tempo "Mai" spenti nella fascia di standby), risveglio rilevato e contato, fascia
  "sempre accesi" rispettata (nota: i dischi emulati da QEMU rispondono sempre "active/idle" a `hdparm -C`, quindi lo stato
  è quello tenuto dal servizio); cartella SMB e cartella NFS montate (cifs e nfs4), lette e scritte, **ricollegate dopo il
  riavvio prima di Docker**; dischi NTFS e FAT32 rimontati dopo il riavvio; aggiornamento di sistema con **snapshot prima
  e dopo** (e niente doppioni); porta 80 di riserva con Caddy fermo e Caddy che riparte; `rfd-nas.local` e
  `<app>.rfd-nas.local` pubblicati con mDNS e serviti in HTTPS con il certificato di casa (app di prova installata in
  modalità Compose da un'immagine locale); catalogo vero di **Big Bear** (492 app) scaricato da GitHub; sveglia del PC
  (RTC) accettata; **spegnimento programmato** vero: notifica "in attesa", attesa di un backup in corso, notifica
  "si spegne… si riaccende domani alle 07:30", VM spenta.
- **Non provabile da questo ambiente** (rete di lavoro filtrata): Docker Hub (registro e ricerca bloccati), siti
  `casaos.app` e `casaos-appstore.paodayag.dev` (non risolti), quindi niente installazione/aggiornamento di un'app vera
  scaricata da Docker Hub. GitHub passava da un'ispezione TLS: per scaricare Big Bear nella VM è stato fidato
  temporaneamente il certificato di quell'ispezione (poi tolto). La riaccensione vera con la sveglia RTC non si può
  provare in QEMU (la VM spenta termina).

### 8.6 Fase 1C: come è stata provata (30/10/2026, sera)
- Ambiente: chroot Ubuntu 26.04 (debootstrap resolute, Python 3.14) **senza** systemd, Docker, dischi veri e VM.
- File manager: API con curl (conflitti, copia/sposta/unisci/tieni entrambi, copia nella stessa cartella, coda con due
  operazioni e annullamento di una copia da 1,5 GB senza file a metà, ZIP/7z/TAR.GZ creati ed estratti, editor con
  conflitto 409, permessi ricorsivi, dimensione, miniature 256 px, preferiti, caricamento interrotto e ripreso con SHA-256
  identico) e pagina con Playwright (menu del tasto destro, rettangolo, Ctrl+C/Ctrl+V, finestra dei conflitti, editor con
  Ctrl+S, trascinamento sulla barra del percorso, ordinamento, miniature, permessi): **nessun errore JavaScript**.
- Punti 16–19: API e pagine nel chroot; riscrittura di fstab dello spostamento e ritorno (file identico all'originale);
  lettura dell'elenco delle versioni Ubuntu (26.10 proposta come non LTS, versioni con data futura escluse). Tutte le 17
  pagine senza errori JavaScript, Home senza rotellina anche con Docker spento.
- **Non provato** (serve la ISO): spostamento vero delle app con Docker, `do-release-upgrade`, servizi systemd nuovi,
  miniature dei video, ritorno indietro con snapper.
- Errori trovati e corretti durante le prove: data del file per l'editor in nanosecondi oltre la precisione di JavaScript
  (ogni salvataggio risultava "file cambiato"; ora è una stringa).

### 8.5 Da provare sul tuo PC (VM con internet o PC vero)
1. **Catalogo**: Impostazioni → App store → "Aggiorna": devono comparire CasaOS, Big Bear, LinuxServer e CoolStore con
   il numero di app (attese ~600 dopo i doppioni). Poi attiva ZimaOS e Unraid CA e aggiorna di nuovo.
2. **Docker Hub**: App store → "Cerca su Docker Hub", per esempio `uptime-kuma`: risultati, scheda con porte e cartelle
   lette dal registro.
3. **App vera**: installa Uptime Kuma dallo store (fonte CasaOS) scegliendo un tag vecchio (es. `louislam/uptime-kuma:1.23.15`
   in modalità avanzata), poi Le mie app → "Controlla aggiornamenti" → aggiorna; l'app deve ripartire e conservare i dati.
4. **Accensione programmata** su un PC vero: Impostazioni → Generale → "Prova la sveglia del PC", poi programma
   spegnimento tra 5 minuti e accensione tra 10; se non si riaccende, nel BIOS/UEFI attiva "Wake on RTC"/"Power on by RTC"
   (su alcuni PC funziona solo con l'ErP/EuP disattivato).
5. **Standby con un HDD vero**: imposta 5 minuti; `sudo hdparm -C /dev/sdX` deve dire "standby" (in VM non si vede).
6. **Let's Encrypt**: serve un dominio che punti al NAS e le porte 80/443 aperte sul router.

## 9. Fase 1B: cosa manca

In ordine consigliato:
1. ✅ ~~Build della ISO e prove in VM~~ — fatto nella 1B-2 (§8.4).
2. 🟡 In VM con internet: ✅ catalogo Big Bear vero; ⬜ CasaOS, LinuxServer, CoolStore, ZimaOS, Unraid, ricerca su
   Docker Hub vera, installazione e aggiornamento di un'app vera → **da provare sul tuo PC (§8.5)**.
3. ✅ ~~Cartelle di rete con il kernel di Ubuntu~~ — SMB e NFS montati e ricollegati dopo il riavvio (1B-2).
4. ✅ ~~Pagine nuove al posto del Centro di controllo~~ — fatto nella 1B-1 (§4 punti 5–7).
5. ✅ ~~Terminale e SSH~~ — fatto nella 1B-1 (§4 punto 8).
6. ✅ ~~HTTPS con Caddy~~ — fatto nella 1B-1; provato in VM nella 1B-2 con porta di riserva, `nido-mdns`, standby
   (anche programmato) con un disco virtuale SATA, SMART, FAT32, snapshot prima e dopo un aggiornamento.
7. ✅ (da provare sulla ISO) **Fase 1C — File manager** (richiesta dell'utente il 30/10/2026, dopo le prime prove della ISO sul suo PC).
   **Regola: niente prove in VM, la ISO la prova l'utente.** Si fa la build, si consegna, l'utente riporta gli errori.
   Tutte le azioni anche dal **tasto destro** (menu contestuale su file, selezione e spazio vuoto).
   a. **Taglia, copia e incolla**: Ctrl+X, Ctrl+C, Ctrl+V, tasto destro e barra in alto quando ci sono appunti;
      funziona anche tra dischi diversi e cartelle di rete.
   b. **Selezione multipla**: Ctrl e Shift, rettangolo col mouse, "seleziona tutto" (Ctrl+A).
   c. **Trascinamento** di file sulle cartelle e sulla barra del percorso per spostarli; con Ctrl premuto li copia.
   d. **Conflitti di nome**: sovrascrivi, salta o rinomina, con "fai così per tutti".
   e. **Coda delle operazioni lunghe**: copie e spostamenti in background (es. 50 GB) con avanzamento, velocità e annulla,
      che proseguono anche chiudendo la pagina.
   f. **Miniature delle foto** generate dal NAS (oggi le foto arrivano intere).
   g. **Vista a griglia o a elenco**, ordinamento per nome, data, dimensione e tipo.
   h. **Comprimi ed estrai** zip, 7z, tar.gz sul NAS.
   i. **Editor di testo** integrato (configurazioni, `.env`, `docker-compose`).
   j. **Preferiti** nella barra laterale (cartelle usate spesso, dischi in alto).
   k. **Dimensione delle cartelle** calcolata su richiesta.
   l. **Permessi**: proprietario e lettura/scrittura.
   m. **Caricamento che riprende** se cade la connessione.
8. **Errori segnalati dall'utente** (30/10/2026): ✅ Home sulla rotellina (corretta, §3.6). ⬜ La fonte **Unraid CA** dello
   store non funziona sul suo PC: lasciato stare su richiesta dell'utente (servirebbe il messaggio di errore di
   Impostazioni → App store); fatte solo due migliorie innocue (§3.6).
9. ✅ (da provare sulla ISO) **"Sposta le app su un altro disco"** (confermato dall'utente il 30/10/2026): Docker (`/var/lib/docker`) e AppData
   (`/DATA/AppData`) oggi sono sul disco di sistema; scelta del disco dati, app fermate, copia con controllo, riavvio,
   possibilità di tornare indietro.
9b. ✅ **DLNA di sistema tolto** (decisione dell'utente il 30/10/2026): niente pacchetto `minidlna`, niente scheda DLNA in
   Condivisioni né codice in `shares.py`; il DLNA si fa con un'app Docker (es. minidlna). Nella prossima ISO.
9c. ✅ **Docker Hub: "Il registro chiede un accesso non supportato"** (segnalato dall'utente il 30/10/2026): Docker Hub manda
   le intestazioni HTTP in minuscolo (`www-authenticate`) e `registry.py` le cercava con le maiuscole. Corretto: intestazioni
   lette senza distinzione tra maiuscole e minuscole (anche `Location` e `Docker-Content-Digest`). Nella prossima ISO.
9d. ✅ (da provare sulla ISO) **"Modifica l'installazione" nelle app installate** (richiesta dell'utente il 30/10/2026), nel menu dei tre puntini di
   Le mie app. Oggi ci sono solo "Impostazioni e limiti" (nome, CPU/RAM, aggiornamento automatico) e "Mostra il compose"
   (sola lettura). Da fare: riaprire la stessa finestra dell'installazione (semplice, avanzata, Compose) già compilata con
   porte, cartelle, variabili, rete, immagine e tag; controllo dei conflitti di porta; copia della configurazione prima
   di salvare, ricreazione dei contenitori con `docker compose up -d` e ritorno alla versione precedente se l'app non
   riparte (stesso meccanismo degli aggiornamenti). I dati in AppData restano.
9e. ✅ (da provare sulla ISO) **Contatore del tempo di accensione** (richiesta dell'utente il 30/10/2026). Oggi c'è solo "Acceso da" (dall'ultimo
   avvio) in Impostazioni → Generale e nel sensore di Home Assistant. Da fare: tempo dall'ultimo avvio ben visibile nella
   Home (aggiornato dal vivo); **ore totali di accensione** dall'installazione (contate dal NAS ogni minuto in
   `/var/lib/nido/uptime.json`, così restano anche dopo spegnimenti e riavvii); numero di avvii, ultimo spegnimento e se
   è stato regolare o improvviso (mancanza di corrente); in Home Assistant sensori "Ore totali di accensione" e "Avvii".
9f. ✅ (da provare sulla ISO) **"Passa alla versione nuova" di Ubuntu** (richiesta dell'utente il 30/10/2026), in Impostazioni → Aggiornamenti di
   sistema. Il NAS controlla se esiste una versione nuova e la **propone sempre, anche se non è LTS**, dicendo chiaramente
   se è LTS (supporto 5 anni) o no (9 mesi di supporto, poi va aggiornata di nuovo): **decide l'operatore** se installarla.
   Prima: snapshot del sistema e controllo dello spazio; durante: registro in diretta; dopo: verifica delle parti di
   RFD-NAS (nome e logo, `dpkg-divert` di 80snapper, Caddy, servizi `nido-*`); **tornare indietro** con lo snapshot se
   qualcosa non va. Va provato sulla build prima di pubblicarlo.

9g. **Fonti dello store aggiornate in automatico** (richiesta dell'utente il 30/10/2026): all'accensione (con
   `OnBootSec` nel timer `nido-catalog.timer`, dopo che la rete è pronta) e ogni 24 ore al posto di una volta a settimana;
   frequenza scelta in Impostazioni → App store; ultimo aggiornamento per fonte e "Aggiorna ora".
### Più avanti (quando il sistema è stabile, non subito)
- ✅ (31/10 sera) **Traduzioni dell'interfaccia**: inglese, spagnolo, tedesco (vedi §3.8). ⬜ Restano installer, testi della
  console e notifiche (in italiano).
- **Scelta della lingua nell'installer** (primo schermo), che imposta anche la lingua dell'interfaccia, la tastiera e il
  fuso orario proposti; lingua cambiabile poi da Impostazioni → Generale.
10. Verifica in due passaggi, procedura guidata al primo avvio, accesso da fuori casa.
11. Rifiniture: schermata per l'account Docker Hub, gestione account dell'interfaccia
   (più utenti, ruoli), notifiche per aggiornamenti delle app e ritorni indietro, pulizia delle immagini
   `nido-rollback` più vecchie di 7 giorni.
12. Prima di pubblicare: verifica ufficiale del marchio (§7.2), link per le donazioni.

## 10. Come provarlo (procedura già collaudata)

- **Solo il pacchetto di aggiornamento** (niente ISO, un minuto): `./make-deb.sh` su Ubuntu/Debian (o WSL) →
  `out/rnfads_<versione>_all.deb`; firmarlo con `strumenti/firma-pacchetto.sh` (o `NIDO_SIGN_KEY=... ./make-deb.sh`) e caricarlo
  dal NAS. Così si consegnano le modifiche senza rifare la ISO.
- **Consegna della ISO**: volumi 7-Zip da 350 MB fatti da `build.sh` (`.7z.001`, `.7z.002`…) + `SHA256SUMS.txt`; su Windows tasto
  destro sul `.001` → 7-Zip → Estrai qui; su Linux `7z x <iso>.7z.001`.

- Ambiente di build Ubuntu 26.04: se la macchina non è una 26.04, creare un chroot con
  `debootstrap resolute` (con universe abilitato), montare dev, dev/pts, proc e sys, ed eseguire lì
  `build.sh`. Per HTTPS usare `HTTPS_PROXY` e `CURL_CA_BUNDLE` se c'è un proxy. Se il mirror risponde 503 basta
  rilanciare. Con debootstrap conviene il sistema minimo e poi `apt-get install` (con molti `--include` può
  bloccarsi su python3-cryptography).
- Prova veloce dell'interfaccia senza ISO (come nella fase 1A): chroot 26.04 con `python3 python3-yaml
  python3-cryptography docker.io docker-compose-v2 samba smbclient avahi-utils nfs-common davfs2`; il chroot deve
  essere un punto di montaggio (`mount --bind` su se stesso) perché Docker funzioni; copiare `usr/lib/nido/panel`
  e lanciare `NIDO_LISTEN=0.0.0.0:8080 PYTHONPATH=/usr/lib/nido/panel python3 -m nidopanel.server`.
- VM: `qemu-system-x86_64 -accel tcg -cpu max -smp 2 -m 4096`, disco virtio da 64 GB e
  `-nic user,hostfwd=tcp::8080-:80,hostfwd=tcp::8443-:443,hostfwd=tcp::2222-:22`.
  Per UEFI+SB: `-machine q35,smm=on -global driver=cfi.pflash01,property=secure,value=on` e OVMF secboot + vars ms.
  Si guida con `-monitor unix:...` (`sendkey`, `screendump`). Il live impiega circa 5 minuti ad avviarsi in TCG,
  l'installazione circa 10.
- Controlli minimi: avvio in BIOS e UEFI+SB, installazione, nessuna unità fallita, login web,
  ogni pagina senza errori JS (Playwright), un'app installata dallo store e poi aggiornata,
  un disco extra (un secondo qcow2 formattato NTFS) montato, standby impostato,
  formattazione di un disco di prova, cartella SMB collegata (Samba sull'host o in un container), HTTPS attivo
  (porta 8443 inoltrata: certificato di casa scaricato e riconosciuto), terminale funzionante (anche dentro un'app),
  SSH con chiave, standby di un disco virtuale (`hdparm -y` può non essere accettato dai dischi virtio: provare con
  un disco SATA/AHCI emulato), aggiornamento di sistema eseguito con gli snapshot prima e dopo.
- Note della 1B-2: con dischi SATA in più in BIOS serve `bootindex=0` sul disco di sistema
  (`-drive if=none,id=sys,... -device virtio-blk-pci,drive=sys,bootindex=0`), altrimenti SeaBIOS prova ad avviare dal disco
  dati; dischi dati come `-device ahci,id=ahci -device ide-hd,bus=ahci.0,serial=...,model=...` (SMART e `hdparm -y`
  funzionano). In 26.04 `dd` è quello di rust-coreutils: `iflag=direct` non è accettato (usare `head -c` per leggere).
  L'installer si guida con `sendkey` dal monitor (lettere, numeri, Invio, frecce: con la tastiera italiana i simboli
  cambiano); dopo l'installazione conviene usare SSH (porta 2222).
- Le schermate della versione funzionante vanno mandate all'utente per conferma.
