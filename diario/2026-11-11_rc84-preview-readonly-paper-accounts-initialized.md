# 11 novembre 2026 — RC84: anteprima funzionante su Singapore + conti PAPER inizializzati

**Stato operativo verificato:** il backend + frontend RC84 sono attivi come **anteprima isolata loopback**, tutti i nuovi wallet PAPER hanno capitale configurato (Falco 1000, Toro 1000, Brain 2000), i due conti classici hanno file di stato RC84 creati da schema canonico e 0 posizioni aperte; **nessun motore strategico avviato, nessun mandato Brain approvato, nessuna rimozione di pause.flag, nessun ordine a Bitget, nessun deploy della web pubblica e nessun merge PR**.

## Evidenze dirette GitHub Actions/VPS

1. [Run 42971204095](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42971204095) **FAILURE nella verifica finale** ma compilazione frontend RC84 riuscita, image Docker preview costruita e container di prova creato. Causa accertata nel codice: si era montato frontend/build direttamente nella FastAPI che registra il catch-all statico prima del router /api/v3, facendo intercettare GET /api/v3/overview. Il workflow ha rifiutato dichiarazione di successo (`RC84_PREVIEW_REFUSED_PREVIEW_AUTH_FAILED`), senza toccare produzione.
2. [Run 42971823320](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42971823320) **SUCCESS**, SHA trigger `01112b1e1bcd027a294f377a1a05393ed1e4e664`. Lo script `deploy/scripts/v3-rc84-repair-preview-routing.sh` (ramo `work/paper-restart-prep-20261110`, commit `0a1843b0203bf89e44d1ff62704a7c9717f389cf`) ha ricreato SOLO il container di prova escludendo frontend/build dal backend; istanza Nginx separata su loopback serve il frontend RC84 e inoltra `/api` a FastAPI.
   - Frontend: `127.0.0.1:18081`, backend: `127.0.0.1:18004` (porte interne VPS, **non accessibili direttamente dal telefono**).
   - `/api/health` PASS, `/` 200, `GET /api/v3/overview` senza autenticazione 401, `POST /api/v3/brain/close` 423 (bloccato).
   - Montaggi dei soli nuovi wallet in sola lettura verificati da Docker, filesystem immagine in sola lettura, `DESK_MODE=paper`, `TRADING_MODE=paper`, `V3_CUTOVER_READONLY=1`, chiusura Brain opt-in spenta. Nessuna chiave provider/exchange nel container. `RC84_PREVIEW_AUTH_UI_API_HEALTH=PASS`, `RC84_PREVIEW_MUTATIONS_BLOCKED=True`, `RC84_PREVIEW_PRODUCTION_UNCHANGED=True`.
   - Nota: nei log un 502 provvisorio durante l'avvio del backend; la verifica finale ha riprovato ed è passata. Non interpretare come disponibilità 24h certificata.
3. [Run 42972191753](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42972191753) **SUCCESS**, trigger commit `eff094a238751562fb165ecd7250589426b18435`. Codice `deploy/scripts/v3-rc84-init-paused-classic-accounts.sh` (ramo di lavoro, commit `0a6e2c0cc72295a3859dd77a16ed1429af816ce7`). Inizializzazione canonica `PaperAccount` da RC84 in cartelle nuove, **con pause.flag presente**. Output VPS: `RC84_HAWK_INITIAL_EQUITY_PAPER=1000`, `RC84_HAWK_OPEN_POSITIONS=0`, `RC84_BULL_INITIAL_EQUITY_PAPER=1000`, `RC84_BULL_OPEN_POSITIONS=0`, `RC84_CLASSIC_ACCOUNTS_INITIALIZED_PAUSED=True`, `RC84_LEGACY_DATA_UNTOUCHED=True`, `RC84_NO_SERVICES_STARTED=True`, `RC84_NO_PAPER_ORDERS=True`.
   - Brain: `python -m backend.v3.runner.exit_worker --validate-only` ha restituito `validated_existing_brain_run`, `RC84_BRAIN_EXIT_VALIDATE_ONLY=PASS`. **Non** equivale a exit-worker effettivamente avviato e monitor sano.

## Nuove directory PAPER collegate alla preview

- Falco: `/opt/superbot-v3-paper-runs/classic-hawk-paper20261111`; `state_v2.json` presente, capitale iniziale 1000, zero posizioni, in PAUSA.
- Toro: `/opt/superbot-v3-paper-runs/classic-bull-paper20261111`; `state_v2.json` presente, capitale iniziale 1000, zero posizioni, in PAUSA.
- Brain V3: `/opt/superbot-v3-paper-runs/brain-v3-paper20261111`; profile da 2000, cap rischio 12%, leva 20–50, mandato `approved=false`, journal e ledger presenti, `pause.flag` presente. Exit-worker validato in lettura ma non avviato.
- Codice sorgente esatto nello staging isolato `/opt/superbot-v3-rc84-stage` SHA `0e29a73a36f668643da4088178bacb8616a45ac0`. Web pubblico `superbot` RESTA RC73; PR #80 ancora DRAFT, non mergiata.

## Prossimi due passi, senza audit aggiuntivi inutili

1. **Predisporre/avviare in PAUSA i servizi strategici** con le nuove directory e senza possibili ordini LIVE, mantenendo i vecchi exit-only Falco/Toro su directory legacy; Brain deve acquisire il lease di uscita tramite un solo `exit_worker`, poi si può avviare runner in `--exit-mode sidecar` con `pause.flag` e mandato disapprovato. Heartbeat fresco e controllo singolo writer PRIMA di ogni sblocco, costi modello zero mentre in pausa. Non presentare al pubblico la preview finché i servizi e la web sono collaudati.
2. Autorizzazione ulteriore e separata dell'utente per migrazione della dashboard pubblica e sblocco PAPER. **Nessun LIVE**. Solo allora prima osservazione 48 h e diario dei trade, perdite, costi, scelte NO_TRADE/long/short. Conservare storici legacy e snapshot RC77.

**Limite importante:** test HTTP dell'overview senza sessione prova correttamente il 401 ma **non** verifica ancora una risposta autenticata completa della pagina dei tre portafogli. Non inventare un collaudo visivo da telefono. L'app prod resta RC73. Non attivare tasto Brain Chiudi ora finché exit-owner non sia effettivamente sano.
