# RC84 PAPER — AI provider gate + riattivazione Chiudi ora: decisione 11/11/2026

## Dato verificato: API esterne

[GitHub Actions #42995334600](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42995334600), SUCCESS, ma il controllo HTTP contiene risultati **non tutti positivi**:

- `RC84_CLAUDE_FALCO_MODELS_HTTP=401`, `RC84_CLAUDE_TORO_MODELS_HTTP=401`: entrambe le credenziali Claude caricate nell'ambiente dei nuovi Falco/Toro sono rifiutate dall'endpoint `GET https://api.anthropic.com/v1/models?limit=1`. Non è stata inviata alcuna richiesta `/v1/messages`. Un 401 segnala problema di autenticazione/credenziale, **non un esaurimento credito certificato**. Credenziali precedentemente presenti in Docker, ma la presenza non garantiva validità.
- `RC84_DEEPSEEK_BALANCE_HTTP=200`, `RC84_DEEPSEEK_BALANCE_AVAILABLE=True`: l'endpoint bilancio DeepSeek conferma API accessibile e saldo disponibile. **Non è stato stampato un importo e non è stata eseguita inferenza**.
- I 3 bot restano `pause.flag`, Brain `mandate.approved=false`, nessun nuovo trade autorizzato.
- I successivi run F0/backup sono diagnostiche separate, **non** una certificazione dello stato corrente delle singole nuove run (F0 vede alcuni dati inaccessibili).

## Risolvere Claude SENZA esporre chiavi

1. L'operatore apre la **Claude Console → API Keys**, verifica che le vecchie chiavi non siano revocate/scadute e genera una nuova credenziale **solo se necessaria e consentita dal proprio account**. Una subscription Claude / Claude Code non sostituisce automaticamente una API key con fatturazione propria.
2. NON scrivere il nuovo valore in ChatGPT, nei commit, nel diario, in GitHub Actions, in screenshot né in un comando shell che resta nella history.
3. Script interattivo predisposto e **NON eseguito**: `deploy/scripts/rc84-replace-claude-key-interactive-paused.py` sul ramo `work/rc84-provider-credit-and-manual-close-20261111`. Va eseguito sulla VPS Singapore via SSH/Termius da un terminale reale con privilegi root. Richiede la nuova chiave tramite input nascosto `getpass`; tenta `GET /v1/models?limit=1`, non procedendo se non riceve 200; quindi sostituisce atomically i due envfile root 0600 e riavvia **solo** `superbot-v3-paper-falco.service` e `superbot-v3-paper-toro.service`, che devono essere già in pausa. Brain, vecchio storico e dashboard NON vengono toccati; rollback file se fallisce. Nessuna chiamata di inferenza.
4. Il nuovo valore viene inserito **solo dall'utente nella propria sessione SSH**, mai dalla chat. Dopo 200 verificare anche che il `DESK_MODEL` configurato sia fra i modelli disponibili usando endpoint metadata; questa è una verifica distinta dalla validità chiave e dal saldo disponibile.

## Chiudi ora: audit concreto del codice e delle modalità attuali

- Backend classic: `backend/desk_api.py` e `backend/desk_view.py` hanno già `POST /api/desk/close-position` / `/api/desk/bull/close-position` (session auth, validazione simbolo, 1 posizione, dedup/richiesta atomica) e il motore `backend/desk/cli.py` consuma `close_position.flag` anche quando è in pausa. L'heartbeat del runner include `close_position=true` solo se PAPER; la risposta di stato espone `can_close_position`.
- Brain: `POST /api/v3/brain/close` con `position_id`, validato contro il journal della run; gate `_brain_single_close_ready` controlla l'**exit-sidecar** che possiede realmente quella run, non basta heartbeat AI; `all:true` è bloccato nel cutover PAPER.
- Frontend `Dashboard.js`, `BrainPortfolioSection.js`, `OverviewCloseControls.js` includono i tasti, conferma, stato richiesta, messaggi di esito. Non creare un nuovo tasto scollegato dal backend.
- **BLOCCO reale:** la web pubblica usa `V3_CUTOVER_READONLY=1`, `V3_ALLOW_CLASSIC_SINGLE_CLOSE=0`, `V3_ALLOW_BRAIN_SINGLE_CLOSE=0`; i **tre mount delle nuove directory PAPER sono `:ro`**. Non basta impostare i due `ALLOW` a 1: la web deve poter scrivere esclusivamente i comandi previsti. È necessaria una revisione della superficie di scrittura con un bridge di comando dedicato oppure, per un collaudo esclusivamente PAPER, un rilascio protetto con soli mount dei tre conti correnti scrivibili, controlli di identità e rollback. Non esporre i dati legacy o chiavi a mount rw.
- **Non** togliere `V3_CUTOVER_READONLY=1`: mantenere START/RESUME/RESET/CLOSE_ALL/UPDATE/ADMIN bloccati (HTTP 423), consentire esclusivamente i singoli POST allowlisted quando servizio competente è healthy e c'è una posizione PAPER attiva.
- Non inviare chiusure fittizie: quando ci sono 0 posizioni, provare solamente che una richiesta con ID inesistente sia rifiutata (404/409), senza scrivere file. La prima chiusura vera dovrà essere testata dall'utente **su una posizione PAPER realmente aperta**, verificando allineamento registro/equity/learning.
- Rollback web precedente RC84 `superbot-rc84-before-brain-ui` e precedente RC73 `superbot-rc84-previous` sono conservati; per la nuova modifica generare una terza snapshot, senza distruggere le prime due.

## Gate prima dell'avvio dei trade (consenso separato)

1. Claude Falco/Toro risponde con HTTP 200 all'API metadata senza generazione; saldo Claude da Console fatturazione. Brain DeepSeek HTTP 200 e `is_available=true` è già provato.
2. `Chiudi ora` singolo PAPER raggiunge una sola autorità di esecuzione per ciascun portafoglio; stop/exit non dipendono dalla disponibilità AI. Dashboard non può inviare LIVE.
3. Leva Brain 20–50x, massimo rischio e floor da `runner_config.json`, capitale Falco/Toro 1000 Brain 2000; 3 pause presenti fino ad autorizzazione, mandato Brain `approved=false`. No forzature slot o chiusure mezzanotte.
4. Nessun merge, deploy, riavvio strategia, modifica mount web o apertura ordini eseguiti nella presente analisi. **Un successivo rilascio della chiusura manuale richiede conferma e prove autonome**, non confondere questo documento con un'attivazione.

## Evidenza sorgente

Ramo `work/rc84-provider-credit-and-manual-close-20261111`, derivato dalla RC84 UI più recente `790dcb01431fd8469f50d113fe56d9e67a83e902`. Workflow provider check #42995334600. Codice dei gate HTTP e sidecar letto tramite GitHub senza modificare la produzione.
