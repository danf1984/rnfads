# RNFADS per Home Assistant (integrazione `rfd_nas`)

Integrazione nativa: si configura dall'interfaccia di Home Assistant, niente YAML e niente `configuration.yaml`.

## Installazione
1. Copia la cartella `custom_components/rfd_nas` in `/config/custom_components/` di Home Assistant
   (oppure aggiungi questo repository in HACS come "repository personalizzato", tipo Integrazione).
2. Riavvia Home Assistant.
3. Impostazioni → Dispositivi e servizi → Aggiungi integrazione → **RNFADS**.
4. Indirizzo (`rnfads.local` o l'IP) e **chiave API** (RNFADS → Impostazioni → Home Assistant e API).
   "Usa HTTPS" acceso; "Controlla il certificato" spento finché non usi Let's Encrypt.

## Cosa crea (un dispositivo "rnfads")
- **Sensori**: CPU, memoria, temperatura, carico, aggiornamenti di sistema e di sicurezza, acceso dal, **ore totali di accensione**, **avvii**, **spegnimenti improvvisi**, **ultimo spegnimento** (attributo "regolare"/"improvviso"), app accese;
  per ogni disco spazio usato (con lo stato di standby negli attributi), temperatura, salute; ultimo backup per ogni
  lavoro di backup; prossimo spegnimento e prossima accensione programmati.
- **Aggiornamento "Sistema"** (dalla 1.1 del NAS): mostra se c'è una versione nuova di RNFADS sul canale online e la
  installa con "Installa" (stesso procedimento di Impostazioni → Aggiornamenti di sistema: firma, snapshot, ritorno automatico).
- **Sensori sì/no**: riavvio necessario, aggiornamenti disponibili, disco acceso/in standby, disco con problemi.
- **Interruttori**: uno per ogni app (acceso = avviata). Il tocco agisce subito, senza conferma. Le app installate dopo
  compaiono da sole.
- **Pulsanti**: riavvia, spegni, cerca aggiornamenti di sistema e delle app, metti un disco in standby, riavvia e
  aggiorna ogni app.

Aggiornamento ogni 30 secondi. Se cambi la chiave API sul NAS, Home Assistant chiede la nuova.

## Requisiti sul NAS
Serve il pannello con l'API `/api/v1` completa (kit del 30/10/2026 dopo la fase 1B-2). Sulla ISO consegnata il
30/10 alle 15:06 c'è solo `/api/v1/status` (sensori ok, pulsanti e interruttori no): per aggiornarla copia sul NAS
`kit/live/includes/usr/lib/nido/panel/nidopanel/server.py` in `/usr/lib/nido/panel/nidopanel/` e lancia
`sudo systemctl restart nido-ui`. Dalla prossima ISO è già dentro.

Nota: l'integrazione non è ancora stata provata dentro Home Assistant (solo le API del NAS sono state provate).
