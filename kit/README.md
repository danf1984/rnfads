# RNFADS — beta 0.3 (fase 1D)

Sistema NAS basato su **Ubuntu 26.04 LTS** (supporto fino al 2031), con un'**interfaccia web propria**
(niente più CasaOS): dalla fase 1B tutte le funzioni sono nell'interfaccia (il vecchio Centro di controllo è stato tolto).
Il nome è un parametro: si cambia in `config.env` (`NIDO_NAME`, `NIDO_HOSTNAME`, `NIDO_WORDMARK`).
I percorsi interni restano `nido` (es. `/usr/lib/nido`, `/etc/nido`).

> **Stato:** fasi 1A–1B provate in VM (BIOS e UEFI + Secure Boot). Le novità della fase 1C (file manager completo,
> modifica dell'installazione delle app, app su un altro disco, contatore del tempo di accensione, passaggio alla versione
> nuova di Ubuntu) sono state provate nel chroot Ubuntu 26.04 e sono nella ISO del 30/10/2026 sera, **da provare** (vedi
> `DA-FARE.md`).

## Cosa c'è

**Installazione**
- ISO per PC x86 a 64 bit: avvio da chiavetta USB o DVD, su PC vecchi (BIOS) e nuovi (UEFI), **anche con Secure Boot attivo**
- Installer guidato in italiano: scegli il disco, il nome del NAS e l'utente, fa tutto da solo.
  Lo stesso utente e la stessa password valgono per SSH, per le condivisioni e per l'interfaccia web
  (se la password ha almeno 8 caratteri; altrimenti l'account dell'interfaccia si crea al primo accesso)
- Disco di sistema in Btrfs con sottovolumi separati:
  `@` sistema · `@data` /DATA · `@docker` Docker · `@appdata` dati delle app · `@log` log · `@snapshots` snapshot

**Interfaccia web** (`https://rnfads.local`, anche `http://` finché non attivi il reindirizzamento)
- **Accesso** con account propri: password con scrypt, sessione in un cookie protetto, blocco dopo 5 tentativi sbagliati
- **Home**: CPU, RAM, rete in download e upload con grafico in tempo reale, temperatura, spazio dei dischi, app con stato
  (un clic apre l'app), **tempo di accensione** (acceso da, ore totali, avvii, ultimo spegnimento regolare o improvviso)
- **App store**: Big Bear, LinuxServer e CoolStore in un unico catalogo senza doppioni, filtri per categoria
  e fonte (CasaOS, ZimaOS e Unraid tolte il 31/10/2026 per evitare problemi con i marchi); fonti personalizzate; **ricerca su Docker Hub** con porte, cartelle e variabili
  lette dal registro
- **Installazione** in tre modalità (semplice, avanzata, Compose): porte libere, cartelle, PUID/PGID, fuso orario e limiti
  di CPU/RAM impostati da soli
- **Le mie app**: avvio, arresto, riavvio, log, limiti, **modifica dell'installazione** (stessa finestra, con ritorno
  indietro se l'app non riparte), disinstallazione; controllo delle versioni, **aggiornamento** della
  singola app o di tutte, aggiornamento automatico notturno (solo correzioni); copia della configurazione prima di
  aggiornare e **ritorno automatico alla versione precedente** se l'app non riparte
- **File**: tutti i dischi e le cartelle, tutto anche dal **tasto destro**; taglia/copia/incolla (Ctrl+X/C/V, anche tra
  dischi e cartelle di rete), selezione con Ctrl, Shift e **rettangolo**, **trascinamento** su cartelle e percorso (Ctrl =
  copia), **conflitti di nome** (sostituisci/unisci, salta, tieni entrambi, "per tutti"), **coda delle operazioni** in
  background con velocità e annulla, **miniature** di foto e video, griglia o elenco con ordinamento, **zip/7z/tar.gz**
  (estrae anche rar), **editor di testo**, **preferiti**, dimensione delle cartelle, **permessi**, caricamento a blocchi
  che **riprende** se cade la connessione, download (cartelle in zip), cestino, anteprime, dettagli (anche EXIF), ricerca,
  link di condivisione con scadenza
- **Cartelle di rete**: SMB, NFS e WebDAV, scoperta dei computer in rete, password salvate cifrate, ricollegamento
  all'avvio (prima di Docker, così le app le vedono)
- **Dischi**: salute SMART (vita residua, temperatura, ore, settori difettosi, test breve e completo), formattazione
  in ext4, Btrfs, exFAT, NTFS, FAT32 o XFS con conferma scritta, montaggio dei dischi già formattati in `/media/<nome>`
  (sola lettura, a ogni avvio, condivisione in rete; ntfsfix per i dischi chiusi male da Windows), **standby per disco**
  (Mai, 5 min … 4 ore o personalizzato, orario dei backup in cui resta acceso, APM, "spegni adesso", accensioni del
  giorno), spazio delle app (Docker), **sposta le app (Docker e AppData) su un altro disco** con copia controllata e ritorno
  indietro. Il disco di sistema non si tocca.
- **Condivisioni**: Samba (per utente o per tutti, ospiti, cestino di rete), NFS, cartelle personali (il DLNA si installa come app Docker, es. minidlna)
- **Utenti**: crea, password, amministratore, elimina · **Backup** (restic, su disco o cloud con rclone): pianificati,
  registro in diretta, versioni e ripristino in una cartella nuova
- **Terminale** nel browser (xterm.js incluso): più schede, come utente o root, **dentro le app** (docker exec);
  **accesso SSH**: acceso/spento, password sì/no, solo dalla rete di casa, porta, chiavi autorizzate
- **Impostazioni**: Generale (riavvia, spegni), **Accesso sicuro (HTTPS)** con Caddy (certificato di casa scaricabile,
  Let's Encrypt, certificato caricato, reindirizzamento da HTTP, sottodomini delle app come `jellyfin.rnfads.local`),
  Notifiche (ntfy, Telegram, email, webhook), **Aggiornamenti di sistema** ("Cerca aggiornamenti", "Aggiorna ora",
  snapshot prima e dopo, registro in diretta, automatico, avviso di riavvio, **passaggio alla versione nuova di Ubuntu**
  anche non LTS, con snapshot, controlli dopo il riavvio e ritorno indietro), Home Assistant e API
- Tema chiaro e scuro, telefono con barra in basso, ricerca globale **Ctrl+K**, pagina **Sostieni il progetto**

## Installare

1. Scrivi la ISO su una chiavetta con [balenaEtcher](https://etcher.balena.io/) o [Rufus](https://rufus.ie/) (in Rufus scegli "Scrivi in modalità immagine DD").
2. Avvia il PC dalla chiavetta: l'installer parte da solo.
3. Scegli il disco di sistema (**viene cancellato**: consigliato un SSD da almeno 64 GB), il nome del NAS e l'utente.
4. A fine installazione togli la chiavetta e riavvia.

Per provarla prima in VirtualBox: 2 CPU, 4 GB di RAM, disco da 64 GB, rete in modalità **bridge**.

## Primo accesso

Dal browser di un altro dispositivo apri `http://rnfads.local` (o il nome scelto) oppure l'indirizzo IP
che compare sullo schermo del NAS, e accedi con l'utente creato nell'installer. Poi in *Impostazioni → Accesso
sicuro* scarica il **certificato di casa**, installalo sui tuoi dispositivi e usa `https://rnfads.local`.
Password dell'interfaccia dimenticata: via SSH `sudo nido-ui-user <nome>`.

## Aggiornare senza rifare la ISO

Tutto il codice del NAS sta nel pacchetto `nido-nas`. Per consegnare una modifica basta il pacchetto:

1. (una volta sola) crea la chiave per firmare: `strumenti/crea-chiave.ps1` (Windows) o `strumenti/crea-chiave.sh` (Linux) e
   copia **solo** `aggiornamenti-pubblica.pem` in `chiavi/` prima di costruire la ISO;
2. `./make-deb.sh` (Ubuntu/Debian o WSL) → `out/rnfads_<versione>_all.deb`;
3. firma: `strumenti/firma-pacchetto.ps1 <file.deb>` (o `NIDO_SIGN_KEY=<privata.pem> ./make-deb.sh`) → `<file.deb>.sig`;
4. sul NAS: Impostazioni → Aggiornamenti di sistema → **Carica aggiornamento…** (scegli insieme `.deb` e `.sig`) → Installa.
   Snapshot prima e dopo; se l'interfaccia non riparte torna da sola alla versione di prima.

Cosa c'è di nuovo in ogni versione: `NOVITA.md` (la prima sezione finisce nel pacchetto e si vede prima di installare).

## Rigenerare la ISO

Modifica `config.env` (nome, versione, link per le donazioni, versione di Ubuntu) e poi:

- da **Ubuntu o Debian**: `sudo ./build.sh`
- da **Windows** con Docker Desktop: tasto destro su `build-windows.ps1` → Esegui con PowerShell
- da altri Linux con Docker: `./build-docker.sh`

La ISO esce in `out/` insieme al pacchetto `.deb`, ai **volumi 7-Zip da 350 MB** (`<iso>.7z.001`, `.002`… : su Windows tasto
destro sul `.001` → 7-Zip → Estrai qui) e a `SHA256SUMS.txt`. La prima build scarica circa 1,5 GB e richiede 20–40 minuti.

## Licenze e marchi

- **Il codice di RNFADS** (installer, interfaccia, script) è software libero con licenza
  **GNU GPL versione 3** (file `LICENSE`).
- Il sistema è **basato su Ubuntu** ma non è Ubuntu: niente loghi Ubuntu (rimossi in build),
  `lsb-release` e `os-release` riportano il nome del progetto con "basato su Ubuntu".
- **Codice sorgente (GPL)**: ogni build produce in `out/` l'elenco dei pacchetti (`*-packages.txt`), dei pacchetti
  sorgente (`*-sources.txt`) e lo script `*-fetch-sources.sh` che li scarica tutti. **Chi pubblica la ISO deve
  pubblicare anche i sorgenti** (es. `./*-fetch-sources.sh sorgenti/ *-sources.txt` su Ubuntu 26.04 con `deb-src`
  attivo, poi caricarli accanto alla ISO nella release). Gli stessi file sono nella ISO in `licenze/` e nel sistema in
  `/usr/share/doc/nido/`.
- **Note legali** (`THIRD_PARTY_NOTICES.txt`): componenti inclusi e licenze (anche xterm.js, MIT, e Caddy, Apache-2.0),
  store di terzi, nota sul marchio Docker. xterm.js è copiato in `ui/vendor/xterm/` dai pacchetti npm
  `@xterm/xterm@5.5.0` e `@xterm/addon-fit@0.10.0` (sorgenti su https://github.com/xtermjs/xterm.js), con le licenze.
  Si leggono anche nell'interfaccia → *Informazioni e licenze*.
- **Store di terzi**: nella ISO non c'è nessun catalogo né icona di app; vengono scaricati dai siti degli autori.
  Le fonti CasaOS, ZimaOS e Unraid sono state tolte il 31/10/2026.
- Non usare il logo di Docker (balena) né quelli di Ubuntu, CasaOS, ZimaOS o Unraid nella grafica del progetto.
  "Docker Hub" si scrive solo per indicare la compatibilità.

## Comandi utili (via SSH)

| Cosa | Comando |
|---|---|
| Password dell'interfaccia | `sudo nido-ui-user <nome>` |
| Registro dell'interfaccia | `journalctl -u nido-ui` |
| Registro di Caddy (HTTPS) | `journalctl -u caddy` |
| Standby dei dischi | `journalctl -u nido-standby` · stato in `/run/nido/standby.json` |
| Aggiornare subito il catalogo delle app | `sudo systemctl start nido-catalog` |
| Aggiornamento notturno delle app (prova) | `sudo systemctl start nido-apps-update` |
| Elenco snapshot | `sudo snapper list` |
| Configurare un cloud per i backup | `sudo rclone config` |

## Struttura del progetto

```
config.env                         impostazioni della build
build.sh                           genera la ISO (debootstrap + squashfs + GRUB/shim)
build-windows.ps1, build-docker.sh la stessa cosa dentro Docker
LICENSE                            GPL-3.0 (il nostro codice)
live/package-lists/                pacchetti inclusi
live/hooks/9000-nido.hook.chroot   configurazione del sistema durante la build
live/includes/                     file copiati nel sistema
  usr/local/sbin/nido-install        installer su disco
  usr/local/sbin/nido-ui-user        crea un account dell'interfaccia o cambia la password
  etc/systemd/system/                nido-ui, nido-standby, nido-mdns, nido-netmounts, nido-catalog(.timer), ...
  usr/lib/nido/panel/
    nidopanel/server.py                server web (login, API JSON, file in streaming, link pubblici)
    nidopanel/auth.py                  account, password scrypt, sessioni
    nidopanel/metrics.py               CPU, RAM, rete, temperatura in tempo reale
    nidopanel/catalog.py               catalogo unico delle app (tutte le fonti)
    nidopanel/registry.py              registri delle immagini e ricerca su Docker Hub
    nidopanel/apps.py                  installazione, aggiornamento, ritorno indietro, limiti
    nidopanel/files.py                 file manager, cestino, ricerca, link di condivisione
    nidopanel/netmounts.py             cartelle di rete SMB/NFS/WebDAV
    nidopanel/secretbox.py             cifratura delle password salvate
    nidopanel/jobs.py                  operazioni lunghe con avanzamento
    nidopanel/disks.py                 dischi: SMART, formattazione, montaggio (fstab)
    nidopanel/standby.py               standby dei dischi (servizio nido-standby)
    nidopanel/terminal.py, sshd.py     terminale (WebSocket + pseudo-terminale) e server SSH
    nidopanel/https.py                 certificato di casa e configurazione di Caddy; server_fallback.py porta 80 di riserva
    nidopanel/{shares,users,backup,updates,notify,system,monitor,stores}.py   condivisioni, utenti, backup, ...
    ui/                                interfaccia (HTML, CSS, JavaScript, font Inter; xterm.js in ui/vendor/xterm)
```

## Note tecniche

- Caddy ascolta sulle porte 80 e 443 e passa le richieste all'interfaccia su `127.0.0.1:8090` (`NIDO_LISTEN` in
  `nido-ui.service`). Il Caddyfile è generato dall'interfaccia (`/etc/caddy/Caddyfile`), i certificati stanno in
  `/etc/nido/tls/` (la chiave della CA di casa solo per root). Se Caddy non parte, l'interfaccia apre da sola la porta 80
  (`NIDO_FALLBACK_LISTEN`) per poter sistemare l'HTTPS.
- Il terminale usa un WebSocket su `/api/term/ws`: solo amministratori, solo dalla stessa origine (controllo di Origin).
- I dischi montati dall'interfaccia sono in `/etc/fstab` con il segno `# nido`; l'impostazione dello standby è in
  `/etc/nido/standby.json`. Per provare senza dischi veri: `NIDO_TEST_LOOP=1` mostra solo i dispositivi loop.
- Le richieste che modificano qualcosa richiedono l'intestazione `X-Nido: 1` (protezione CSRF insieme al cookie
  `SameSite=Strict`). Le pagine hanno una Content-Security-Policy senza script esterni.
- Ogni app è un progetto Docker Compose in `/var/lib/nido/apps/<nome>/` (`docker-compose.yml`, `nido.override.yml`
  con limiti e versione, `.env` con PUID/PGID/TZ, `app.json`, `versions/` con le copie della configurazione).
  I dati stanno in `/DATA/AppData/<nome>/`. L'immagine precedente resta come `nido-rollback/<app>-<servizio>:prev`.
- Docker Hub: i risultati delle ricerche restano in memoria un'ora. Il codice supporta già un account Docker
  personale facoltativo (`/etc/nido/registry.json`: `hub_user`, `hub_token` cifrato); la schermata per impostarlo
  arriva nella fase 1B.
- Gli snapshot riguardano solo il sistema (`@`): dati, app e Docker non tornano indietro.
