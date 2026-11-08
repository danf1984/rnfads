# RNFADS — come riprendere il lavoro (aggiornato il 1/11/2026, versione 1.2)

**ISO 1.2.3 fatta** (SHA256 `b617f7b33c996aea1a2cf0680626f40b8cff6ce7c901499e69ca460bd65580b8`): solo stile originale, senza store extra. **ISO 1.2** (SHA256 `c1d9d84ac4b481c6bc91b786e580b43c105ce56843c81a1a7da9f671a9583c59`): servizi cloud, Rete, Schermo del NAS già installato, condivisioni su /DATA più semplici. Da provare.

**ISO 1.1 costruita** (SHA256 `bbd9e83321b6e6f8ff5750b924085d5668dedf9ad62748ef6529877f1626a24d`), da provare dall'utente.
Pacchetto solo per l'utente: `pacchetti/rnfads-extra-store_*.deb` (fonti CasaOS/ZimaOS/Unraid).

## PER PRIMA COSA alla ripresa
- **Versione 1.1 nel kit** (installer in 4 lingue, console e notifiche tradotte, aggiornamento online): manca la ISO, che si fa
  **una volta sola**: la chiave pubblica c'è (`kit/chiavi/aggiornamenti-pubblica.pem`, 1/11/2026), le fonti CasaOS/ZimaOS/Unraid
  sono in un pacchetto a parte solo per l'utente (`make-extra-deb.sh`, non nella ISO). Il pacchetto 1.1 provato dall'utente
  funziona (1/11/2026).
- **Niente pubblicazione su GitHub per ora** (decisione dell'utente, 1/11/2026): il sistema resta per uso personale. Il canale
  degli aggiornamenti online può stare in casa (anche http://, es. una cartella del PC servita in rete) e si imposta dopo da
  Impostazioni → Aggiornamenti di sistema; i pacchetti si preparano con `kit/strumenti/pubblica-aggiornamento.ps1`.

## Dove siamo
- **RNFADS 1.0.1**: ISO `rnfads-1.0.1-amd64.iso` (SHA256 `d25c9e558551996eb2668c045d817ad8157e837f998c6387726e51fb0dd51e68`),
  5 volumi 7-Zip. Corregge due errori trovati dall'utente sulla 1.0: schermo nero con la scheda VMSVGA (ora corretto anche nella
  riga di avvio e nell'initramfs) e "Lingua non supportata" cambiando lingua. **Non ancora provata dall'utente.**
- Pacchetto `pacchetti/rnfads_1.0.1+202611010805_all.deb` (lo stesso che è dentro la ISO; non firmato). Su una VM già installata
  si può caricare questo (modalità sviluppatore) invece di reinstallare: rifà da solo initramfs e GRUB.
- Cosa c'è nella 1.0, oltre a tutto il resto (dettagli in SPEC.md §3.7–§3.9):
  - correzione dello schermo nero con la scheda VMSVGA di VirtualBox;
  - pulsante Riavvia / Spegni nella barra in alto;
  - lingue italiano / inglese / spagnolo / tedesco (Impostazioni → Generale → Lingua);
  - App store: Big Bear, LinuxServer, CoolStore, **Runtipi** e Docker Hub (CasaOS, ZimaOS e Unraid tolte), "Aggiorna tutto",
    fonti all'avvio e ogni 6 ore, account Docker Hub;
  - **Accesso remoto** con Tailscale e ZeroTier (Impostazioni → Accesso remoto).
- **Chiave per le firme: non c'è ancora** in `kit/chiavi/` (i pacchetti si installano solo in modalità sviluppatore).

## Prima di ripartire (tu)
1. Installa la ISO 1.0.1 (anche nella stessa VM VirtualBox con VMSVGA: lo schermo nero deve essere sparito).
2. Prova l'elenco qui sotto e annota gli errori (foto dello schermo o testo del messaggio).
3. (Consigliato) Crea la chiave: `kit/strumenti/crea-chiave.ps1` (Windows) o `crea-chiave.sh`, copia SOLO
   `aggiornamenti-pubblica.pem` in `kit/chiavi/`. La privata resta a te.

## Cosa provare sulla 1.0.1
1. Avvio dopo l'installazione: compare "rnfads login:" (niente schermo nero) e l'interfaccia si apre.
2. Procedura guidata al primo accesso; Impostazioni → Generale → **Lingua** (prova le 4 lingue).
3. App store: fonti Big Bear, LinuxServer, CoolStore, **Runtipi**; installa un'app di Runtipi (es. Uptime Kuma o Vaultwarden) e
   aprila; "Aggiorna tutto".
4. Impostazioni → App store → **Account Docker Hub** (nome utente + token), "Controlla".
5. Impostazioni → **Accesso remoto**: installa Tailscale, "Collega", accedi dal link, apri il NAS dal telefono con Tailscale;
   prova "Rendi raggiungibile la rete di casa". ZeroTier: installa, entra in una rete creata su my.zerotier.com, autorizza il NAS.
6. Pulsante di accensione in alto: Riavvia.
7. Account con ruoli, aggiornamento con un pacchetto `.deb`, notifiche delle app (prove della 0.3 ancora aperte).
8. Dalla 0.2: modifica dell'installazione di un'app, spostamento delle app su un altro disco, spegnimento brusco con il contatore
   di accensione, sensori nuovi in Home Assistant.

## Cosa resta da fare (numeri di DA-FARE.md)
- ✅ 5 Docker Hub · ✅ 12 Tailscale/ZeroTier · ✅ 13 traduzioni dell'interfaccia · ✅ marchio · ✅ fonti tolte · ✅ Runtipi
- **8.** **Aggiornamento online** (archivio apt firmato, canali stabile/beta, avviso e sensore in Home Assistant).
- **10.** **Verifica in due passaggi** per l'accesso all'interfaccia.
- **12 (resto).** Cloudflare Tunnel.
- **13 (resto).** Traduzioni dell'installer, della console e delle notifiche.
- **14.** **Scelta della lingua nell'installer** (serve una ISO nuova).
- **Link per le donazioni** (PayPal, Ko-fi, GitHub Sponsors, Liberapay): li dai tu, vanno in `kit/config.env`.
- Alla pubblicazione: sorgenti, elenco dei pacchetti e note legali accanto alla ISO (`fetch-sources.sh`).
- Traduzioni: testi nuovi da aggiungere in `kit/strumenti/traduzioni/tr/extra*.tsv` (vedi LEGGIMI lì).

## Messaggio da incollare nella prossima sessione (con questo zip allegato)
```
Ti allego rnfads-kit-<data>.zip: è il mio sistema NAS RNFADS (versione 1.0.1) basato su Ubuntu 26.04.
Leggi prima RIPRENDERE.md, poi SPEC.md, STATO-FASE1B.md e DA-FARE.md.

Situazione: ISO 1.0.1 provata sulla mia VM/PC: <scrivi qui com'è andata>.
Per prima cosa voglio la scelta della lingua nell'installer (punto 14).
Errori trovati: <elenco o foto>.

Cosa voglio fare adesso: <es. correggere gli errori, poi i punti 8 e 10 di RIPRENDERE.md>.
Per le correzioni consegnami un pacchetto .deb nuovo (make-deb.sh); la ISO la rifacciamo quando serve.

Regole:
- Lavora a tappe e, a ogni tappa che funziona, salva il lavoro in uno zip aggiornato e mandamelo.
- Quando ti scrivo "fermati", chiudi al primo punto stabile e consegnami subito lo zip con quello che funziona e una nota.
- Lavora in autonomia e usa poche schermate di controllo per risparmiare utilizzo.
- NON provare la ISO in VM: la provo io e ti riporto gli errori.
```
