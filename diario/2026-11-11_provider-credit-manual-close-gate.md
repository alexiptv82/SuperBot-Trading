# 11 novembre 2026 — CRITICITÀ CLAUDE HTTP 401, DEEPSEEK SALDO OK; gate Chiudi ora identificato

**Ultima richiesta utente:** «vai avanti» per verificare AI e preparare riattivazione di singola chiusura PAPER senza avviare bot.

## Verifica concreta dei provider eseguita e conclusa in precedenza
[GitHub Actions #42995334600](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42995334600) SUCCESS, letti log:
- `RC84_CLAUDE_FALCO_MODELS_HTTP=401` e `RC84_CLAUDE_TORO_MODELS_HTTP=401`: le credenziali **ANTHROPIC_API_KEY** dei nuovi Falco/Toro sono effettivamente caricate nel processo ma l'API Claude le **rifiuta per autenticazione**. Non scambiare questo risultato con un problema di saldo; non togliere le pause a questi bot, altrimenti il codice classico può ricadere in regole senza Claude.
- `RC84_DEEPSEEK_BALANCE_HTTP=200`, `RC84_DEEPSEEK_BALANCE_AVAILABLE=True`: il Brain può autenticarsi all'API bilancio e il saldo risulta disponibile. Non dimostra la qualità delle decisioni Brain e non è una generazione di testo AI.
- Zero model calls, zero trading, nessuna credenziale stampata o spostata in questa ispezione.
- Fonte ufficiale Anthropic: 401 significa problema con chiave API, ad esempio malformata, disattivata, revocata o scaduta; si risolve verificando o rigenerando chiave in Claude Console.

## Attività preparate ma NON eseguite su VPS
- Ramo dedicato `work/rc84-provider-credit-and-manual-close-20261111` da web RC84/UI ultima versione.
- Script interattivo `deploy/scripts/rc84-replace-claude-key-interactive-paused.py`: per il solo amministratore VPS con terminale SSH e accesso Claude Console, inserimento nascosto del nuovo token, verifica `GET /v1/models` 200 senza inferenza, scrittura atomica in `/etc/superbot-v3-paper/falco-ai.env` e `toro-ai.env`, riavvio SOLO dei due motori classici PAUSED, verifica `/proc/PID/environ` a confronti booleani e rollback dei vecchi file in memoria in caso di errore. Non è stato eseguito né testato direttamente su VPS; non aggiungere valori sensibili in chat, repo, shell history, script o Actions.
- Runbook tecnico `docs/v3/RC84-AI-KEY-AND-MANUAL-CLOSE-GATES-20261111.md` con audit di API/runner/app.

## Audit Chiudi ora
- La web pubblica è ancora `V3_CUTOVER_READONLY=1` con `V3_ALLOW_CLASSIC_SINGLE_CLOSE=0`, `V3_ALLOW_BRAIN_SINGLE_CLOSE=0`. I mount web dei 3 wallet nuovi sono `:ro`. **Non basta cambiare un flag**: i backend non potrebbero creare file-richiesta.
- Backend classici `backend/desk_api.py` + `backend/desk_view.py` + worker `backend/desk/cli.py` hanno protocollo singola chiusura PAPER, anche in pausa, con heartbeat e conferma; Brain `backend/v3_api.py` usa heartbeat/lease dell'**exit-sidecar** della run e accetta `position_id` singolo (bulk in modalità cutover da impedire).
- Frontend `BrainPortfolioSection.js`, `OverviewCloseControls.js` e `Dashboard.js` includono i controlli ma li disabilitano finché i server gate sono chiusi. Evitare una correzione puramente estetica.
- Per il futuro rilascio occorre un passaggio isolato che consenta la scrittura dei SOLI comandi sulle 3 run PAPER nuove, dopo audit dei mount e writer unico; mantenere `V3_CUTOVER_READONLY=1` e sbloccare solo le due allowlist di POST singola chiusura con autentificazione. START/RESUME/RESET/CLOSE_ALL sempre 423.
- La prima prova con posizione reale avverrà soltanto quando ci saranno **trades PAPER** e dopo autorizzazione, verificando saldo/storico/learning; nessuna chiusura fittizia.

**Stato:** dashboard SuperBot accessibile (403 precedentemente risolto e confermato dall'utente), Falco/Toro 1000 USDT PAPER e Brain 2000 USDT PAPER, tutti in pausa, Brain mandato non approvato; nessuna pubblicazione, reset, merge, riavvio o ordine con questa attività. PR #81 Draft (già distribuita web ma non mergiata). Precondizione principale ora: ottenere nuova API key Anthropic valida dall'utente tramite Claude Console con inserimento nascosto sul VPS, non con chat.
