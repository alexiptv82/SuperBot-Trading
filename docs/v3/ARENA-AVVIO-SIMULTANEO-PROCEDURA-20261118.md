# AI Arena — preparazione in pausa e avvio simultaneo (procedura, NON eseguita)

Ramo: `work/arena-prepare-paused-runs-20261118` (PR in bozza). Ogni fase richiede l'OK esplicito dell'utente.
**Fase A** è la sola che può essere autorizzata ora: non avvia servizi, non assegna T0, non spende.
`<SHA>` = commit della PR revisionato da ChatGPT e dall'utente (40 caratteri), mai la testa mobile del ramo.

## Fase A — tre run preparate in pausa (nessun servizio, nessun T0, nessuna spesa)

```
S=/tmp/arena-prep.sh
curl -fsSL https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/<SHA>/deploy/scripts/arena-prepare-paused-runs-20261118.sh -o $S
bash $S --inspect --sha <SHA>                                   # sola lettura
sudo bash $S --update-stage --sha <SHA>                         # stage nuovo + venv senza pacchetti; stage 48dc0749 conservato
sudo bash $S --prepare-paused --sha <SHA> --day 2026-11-18      # tre run in pausa, mandato NON approvato, T0 assente
```

Atteso: `ARENA_PREP_RESULT=THREE_RUNS_PREPARED_PAUSED_NO_T0`, `stage: PREPARED_PAUSED_NO_T0`, `BRAIN_HISTORICAL=ACTIVE`,
`ARENA_UNITS=ALL_INACTIVE`. Rifiuti previsti: Brain storico non attivo, unità Arena attive, stage a SHA diverso, run
già esistenti (mai sovrascritte), `trial.env` di un altro giorno. Se qualcosa fallisce a metà, nella posizione
finale non resta nulla (preparazione in staging, spostamento solo con tre run valide).

Correzione inclusa: i template installati avviano `/opt/superbot-arena-stage/.venv/bin/python3`, ma lo stage #106
non aveva creato la venv, quindi ogni servizio sarebbe fallito all'avvio. `--update-stage` la crea con la sola libreria
standard: runner, uscite, bridge e `trial_setup` non richiedono pacchetti (verificato in una venv vuota).

## Fase B — verifiche senza AI (servizi uscite e bridge, autorizzazione separata)

1. `sudo install -d -m 0700 -o root -g root /run/superbot-arena-close` (o `0710 root:<GID>` con il web non-root,
   vedi matrice §3).
2. `sudo systemctl start superbot-arena-exit@deepseek superbot-arena-exit@qwen superbot-arena-exit@minimax`
3. `sudo systemctl start superbot-arena-close-bridge`
4. `bash $S --inspect --sha <SHA> --day 2026-11-18`: `exit_service_healthy: true` per tutte e tre.
5. Backup a caldo e verifica:
   `sudo /opt/superbot-arena-stage/.venv/bin/python3 -s -m backend.v3.arena.backup snapshot --day 2026-11-18 --dest /opt/superbot-v3-backups/arena-<data>`
   (con `PYTHONPATH=/opt/superbot-arena-stage:/opt/superbot-arena-stage/backend`), poi `... backup verify --dest ...`.
6. Web → socket dal container reale (matrice §6). I runner restano **fermi**.

## Fase C — dashboard Samsung (sola lettura)

Mount in sola lettura di `/opt/superbot-ai-arena-paper` nel container web, `V3_ARENA_READONLY_ENABLED=1`,
`V3_ARENA_TRIAL_DAY=2026-11-18`, build con `REACT_APP_BRAIN_ARENA_SHADOW_API=1`. Atteso nell'app: tre card
**"Preparato · in pausa"**, PnL "—", intestazione "in attesa di attivazione comune". Provato: la lettura non crea né
modifica file (`test_prepared_api.py`). Chiusure manuali (`V3_ARENA_ALLOW_MANUAL_CLOSE`, `REACT_APP_ARENA_MANUAL_CLOSE`)
solo dopo la Fase B.

## Fase D — decisioni economiche (prima di qualunque spesa)

`activate` rifiuta finché `budget_gate` segnala blocchi. Con le config di oggi i blocchi sono:
`PRICE_ESTIMATE_DISTORTS_COMPARISON:qwen|minimax` (2/8 USD contro listino 0,32/1,28 e 0,15/0,60),
`KEY_LIMIT_BELOW_TRIAL_BUDGET` (0,75 × 14 = 10,50 USD oltre il limite chiave di 2 USD) e
`TOTAL_BUDGET_NOT_APPROVED`. Serve una decisione dell'utente su:

* prezzi in config al listino di picco (proposta: DeepSeek 0,30/1,20; Qwen 0,32/1,28; MiniMax 0,15/0,60);
* tetto giornaliero uguale per le tre AI, per esempio 3,50 USD (massimo teorico 147 USD in 14 giorni), oppure uno più
  basso dopo il pilota;
* `KEY_LIMIT` del trasporto OpenRouter ≥ tetto × 14 (modifica di codice) e limite della chiave sul sito OpenRouter
  uguale;
* budget totale approvato, passato come `--approved-total-budget-usd`;
* pilota consigliato da ChatGPT: alcune ore a spesa ridotta per misurare token e ragionamento (`inference_trace.jsonl`)
  **senza** dichiarare iniziati i 14 giorni. Il pilota usa giorno e cartelle propri, non le run della gara.

## Fase E — avvio simultaneo (solo con OK esplicito, budget approvato)

```
P=/opt/superbot-arena-stage/.venv/bin/python3; export PYTHONPATH=/opt/superbot-arena-stage:/opt/superbot-arena-stage/backend
sudo -E $P -s -m backend.v3.arena.universe_cli --out /opt/superbot-ai-arena-paper/universe_T0.json   # deve dare gli stessi 27 simboli
T0=$(date +%s%3N)
sudo -E DESK_MODE=paper $P -s -m backend.v3.arena.trial_setup activate --day 2026-11-18 --t0-ms $T0 \
   --confirm AVVIA-GARA-PAPER-T0-$T0 --approved-by <nome> --universe-snapshot /opt/superbot-ai-arena-paper/universe_T0.json \
   --approved-total-budget-usd <importo approvato>
# inferenza: V3_ARENA_ALLOW_INFERENCE=1 in /etc/superbot-arena/{qwen,minimax}.env, DEEPSEEK_API_KEY in deepseek.env (0600)
sudo systemctl start superbot-arena-runner@deepseek superbot-arena-runner@qwen superbot-arena-runner@minimax
```

`activate` controlla nell'ordine: frase con il T0, T0 = adesso (±5 min), tre run in pausa e "fresche" (solo
`run_prepared` nel journal), tre servizi uscite sani, istantanea dell'universo con gli stessi simboli e meno di 6 ore,
cancello economico. Poi scrive T0 comune → mandati approvati → rimozione delle tre pause. Se fallisce a metà riporta
tutto allo stato preparato. Provato in `test_trial_setup.py`: guasto al terzo mandato, rifiuti e attivazione con
apertura nello stesso minuto per le tre AI.

## Emergenza

Vedi matrice §7: pausa alle tre run (stop delle nuove aperture), runner fermati, **servizi uscite sempre attivi finché
ci sono posizioni aperte**.
