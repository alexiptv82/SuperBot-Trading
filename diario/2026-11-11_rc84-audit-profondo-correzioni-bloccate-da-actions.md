# 11/11/2026 — Audit profondo richiesto e correzioni staged, NON in produzione

## Richiesta utente
L'utente autorizza esplicitamente **correzioni immediate** di Falco/Toro/Brain **soltanto PAPER**, e accetta anche eventuale reset dei portafogli perché il capitale è simulato. Ha priorità qualità/stabilità ed eliminazione dei bug, non conservare le posizioni in sé. Non confondere questa intenzione con un'autorizzazione a inviare ordini LIVE o a fare merge arbitrari. Non si può garantire assenza assoluta di bug: occorrono prove verificabili.

## Diagnosi certificata su Singapore (prima delle modifiche)
- [Audit classici/Brain #43094045869](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43094045869): Falco BCH+BNB LONG 15x 100 USDT ciascuna, Toro BCH+BNB LONG 15x 350 USDT ciascuna, stessi SL/TP, entrati a circa 2 secondi di distanza alle 16:29:42/44 UTC; **source=rules_long_s25**. Tutte le 3 aperture per portafoglio registrate in 8h sono LONG S25, senza aperture dirette Claude; `DESK_LONG_S25=1` entrambi. Prompt e capitali diversi ma overlay strategico S25 identico. SHORT **non cancellati dal codice**; non presumere che siano stati correttamente testati in questa run.
- Claude ultime 8h: Falco 5 calls, 4 parse validi, 1 `json_troncato`; Toro 5 calls, 3 validi, 2 `json_troncato`. Possibile criticità di `max_tokens=1100` per JSON; solo osservato, non ancora riparato.
- Strategia S25 da `backend/desk/long_s25.py`: **STOP_ATR=1.5 / TARGET_ATR=1.5**, cioè **rapporto rischio/rendimento iniziale 1:1 prima di commissioni**; anche operazioni LONG tradizionali condivise e identiche, senza consulenza Claude per questa specifica apertura. S25 ha time exit 12h e `protect` evita uscite Claude/rules su posizioni S25. **Spegnere del tutto S25 prima della chiusura dei trade potrebbe compromettere quelle uscite**.
- [Brain audit #43094445732](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43094445732): processo RUNNING, 6 cicli, nessuna decisione nel journal tranne run_prepared, 0 eventi spend DeepSeek; motivi per simbolo `no_market_rules` e `data_unavailable` prima della chiamata AI. È un difetto tecnico del percorso feed/contract gate, NON un NO_TRADE decisionale del modello. `last_error` transitorio torna subito a None tra cicli.
- Codice attivo dei servizi confrontato con codice `f3becb3bb4b3869e28967536ccf277624d5a1a4b`: blob identici per `backend/desk/{cli,long_s25,brain}`, `backend/v3/runner/{feed,contracts,wiring}`, `brain_market/market_view_params.json`. Brain base 15m `pct_window=2880`, minimo **2893 barre 15m consecutive**, 1h 733, 4h 193, conservando freschezza e no-bar-fabrication.
- Bitget official docs confermano `GET /api/v2/mix/market/contracts` e `GET /api/v2/mix/market/history-candles` pubblico con limite 200 barre per chiamata. Parser attuale rifiutava maxLever >125; questo *potrebbe* spiegare BTC/ETH `no_market_rules`, ma non è ancora provato con payload vivo.

## Sicurezza e blocchi reali
- Avviata da GitHub l'azione di pausa **SOLO nuove aperture** (nessun force-close) [#43095712678](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43095712678), ma rimasta **QUEUED**, senza prova che `pause.flag` siano stati creati.
- Avviata la verifica publica Bitget da VPS [#43096514061](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43096514061), anch'essa **QUEUED**, causa accodamento non accertata (possibile disponibilità GitHub/limiti account; non asserire senza dati).
- Utente ha ricevuto comando Termius **idempotente**:
```sh
for d in classic-hawk-paper20261111 classic-bull-paper20261111 brain-v3-paper20261111; do
  touch "/opt/superbot-v3-paper-runs/$d/pause.flag"
done
echo "Nuovi ingressi PAPER messi in pausa"
```
Questo conserva gli exit owner. **Non dichiarare eseguito** senza conferma Termius o VPS.
- Script diagnostico **sola lettura** pubblicato su main commit `796b1b9e1bdd8531cb2511afbf80726ed321ba9a`: `deploy/scripts/rc84-public-feed-diagnostic-readonly.py`, Git blob **`184e5cd54410924c3ce433feb57fb93ebe7e8c9e`**. Può essere usato via Termius con curl + verifica hash, NON accede a wallet, né credenziali, chiavi o endpoint di trading. Interroga contratti e 15m/1H/4H di BTC/SOL, misura gap e min bars.

## Modifiche STAGED, non operative
- Branch `work/rc84-fix-classic-divergence-brain-market-20261111`, PR **Draft #85** `https://github.com/alexiptv82/SuperBot-Trading/pull/85`, **NON mergiata**, base `work/rc84-repair-baseline-20261111` su f3bec.
- `backend/desk/long_s25.py`: parametro `allow_new_entries` separato dai TIME EXIT S25. Le posizioni S25 pregresse continuano ad avere gli exit previsti anche quando non aprono nuove S25.
- `backend/desk/cli.py`: **NO nuove S25 in entrambi per default**, pur mantenendo `DESK_LONG_S25=1` per proteggere e chiudere posizioni pregresse. Opt-in SOLO Toro `DESK_S25_TORO_ENTRY_APPROVED=1` ma **mai attivarlo ora senza collaudo e consenso**. I LONG/SHORT originali (Claude e fallback rules) non sono disabilitati; resta una logica fallback comune ai due portafogli, quindi NON promettere impossibilità assoluta di operazioni contemporanee indipendenti.
- `backend/v3/runner/contracts.py` candidato: validazione metadata `maxLever<=200` al posto di <=125, senza aumentare limite Brain 50x; deve ancora superare prova payload vivo Bitget.
- `backend/v3/runner/runner.py`: heartbeat `last_cycle` sticky tra poll con at_ms, decisions, opened, error codes. Non altera il risk gate o le scelte AI.
- Test aggiornati: `test_long_s25.py`, `test_v3_runner_contracts.py`, `test_v3_runner_runner.py`; **non testati**, perché nuove Actions in coda e tool Python/container non utilizzabili durante questa sessione. Non chiamarli PASS.
- **Brain data_unavailable NON ancora corretto**, in attesa di prova reale delle candele; non abbassare soglia o fingere barre. E neppure i `json_troncato` Claude sono stati corretti.

## STOP-GO per ripartenza pulita PAPER
1. Verificare effettivamente pause di nuovi ingressi, tutela uscite e proprietà exit; se l'utente vuole chiudere in app, eseguire le singole chiusure, poi **backup esterno verificato prima di reset** come da direttiva SuperBot.
2. Eseguire script pubblico diagnostico da VPS/Termius se Actions non ripartono. Determinare `maxLever` dei simboli e sequenza candele, codici `insufficient_history/stale/data_unavailable`; correggere feed in branch **senza forzare opportunità o consumi AI**.
3. Test offline specifici (S25, backtest SHORT preservati, contracts, feed, market, runner, exit sidecar) e suite regression, verifica che nessun altro processo scriva journal degli altri.
4. Backup account/journal/Telegram/dati AI prima del reset; cambiare SOLO PAPER, avviare progressivamente e verificare un giro DeepSeek con decisione `NO_TRADE` motivata o `OPEN` autorizzata e contabilizzata, più LONG/SHORT differenziati.
5. Solo dopo prove positive, deploy/merge concordati, niente nuovi investimenti, Fable OFF e LIVE impossibile.

**Checkpoint rigoroso:** abbiamo individuato criticità importanti e preparato codice, ma non siamo al rilascio e non siamo in grado di promettere zero bug.
