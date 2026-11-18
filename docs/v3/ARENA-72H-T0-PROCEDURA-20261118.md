# AI Arena 72 ore / 18 USD: procedura verso il T0 (NON eseguita)

Ramo PR #110 `work/arena-72h-18usd-budget-20261118`. `<SHA>` = commit revisionato (40 caratteri). Ogni fase richiede
l'OK dell'utente. Il Brain storico non viene mai fermato, riavviato o modificato. Nessuna modalità LIVE.

## Cosa è stato corretto e provato in questo giro (locale)

| P0 | Stato |
|---|---|
| Scadenza T0+72h: nessuna nuova decisione né apertura, anche con AI in volo | test ChatGPT superati; **in più**: con 27 simboli in sequenza le chiamate AI proseguivano oltre la scadenza a metà ciclo → ora il cancello di spesa nega ogni chiamata dopo la scadenza (test che fallisce senza la correzione) |
| Tetto 2 USD/giorno e 6 USD cumulativi per AI | registro persistente (ChatGPT) + **prenotazione**: una chiamata parte solo se speso + costo MASSIMO stimato (caratteri/2 + 6.000 token) resta sotto entrambi i tetti, sotto lock di file (un secondo processo è rifiutato). Simulazione 72 h su 4 date UTC al costo massimo: totale ≤ 6 USD |
| Run già preparate sul VPS con config vecchia | `trial_setup supersede-prepared` + script `--replace-prepared`: archivio verificabile (mai modifica, mai cancellazione), solo con 0 posizioni via `can-stop-exit`, uscite fermate e riavviate, Brain/bridge/runner non toccati |
| Prova di un ciclo senza crediti | `python -m backend.v3.arena.smoke`: copia delle tre run, T0/mandati solo nella copia, feed Bitget reale, modello finto NO_TRADE, run vere intatte |
| **Nuovo P0 trovato dallo smoke reale** | `history-candles` di Bitget non restituisce l'ultima candela chiusa (misurato per 13+ minuti dopo la chiusura): ogni ciclo risultava `stale` → `data_unavailable` su tutti i 27 simboli, cioè **nessuna decisione per 72 ore**. Corretto: la coda si completa dall'endpoint `candles`, solo barre chiuse. Vale anche per il monitor delle uscite (minuti) |

Limite onesto del tetto: la prenotazione usa i prezzi della config (= listino di picco). La fatturazione reale può
differire: per Qwen/MiniMax il tetto vero resta il limite di 6 USD sulla chiave OpenRouter (verificato dal trasporto,
`limit` esattamente 6); per **DeepSeek** (API diretta) non esiste un tetto lato fornitore: caricare sul conto DeepSeek
un credito non superiore a quanto si accetta di perdere (es. 6 USD) è l'unico limite indipendente dal nostro codice.

## Fase 1 — sostituzione delle tre run preparate (uscite fermate solo con 0 posizioni)

```
S=/tmp/arena-prep.sh
curl -fsSL https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/<SHA>/deploy/scripts/arena-prepare-paused-runs-20261118.sh -o $S
sudo bash $S --inspect --sha <SHA> --day <ARENA_DAY>
sudo bash $S --replace-prepared --sha <SHA>
```

Atteso: `ZERO_POSITIONS_VERIFIED=TRUE`, `OLD_RUNS_ARCHIVED=...`, `NEW_RUNS_PREPARED_PAUSED_NO_T0=TRUE`,
`RESULT=PREPARED_RUNS_REPLACED_EXITS_HEALTHY`. Rifiuti previsti: runner Arena attivo, Brain storico non attivo,
`can-stop-exit` negato, archivio su altro disco. Se l'archivio fallisce: run vecchie al loro posto e uscite riavviate.
Il bridge resta acceso con il codice precedente in memoria fino a un riavvio separato.

## Fase 2 — prova a secco sul VPS (nessun credito)

```
P=/opt/superbot-arena-stage/.venv/bin/python3; export PYTHONPATH=/opt/superbot-arena-stage:/opt/superbot-arena-stage/backend
sudo -E DESK_MODE=paper $P -s -m backend.v3.arena.smoke --day <ARENA_DAY>
```

Atteso: per ogni AI `state: running`, `opened: 0`, `model_calls` vicino a 27 (meno i simboli senza dati, elencati),
`real_runs_untouched: true`. Durata misurata in locale: vedi PR. Le run vere restano `PREPARED_PAUSED_NO_T0`.

## Fase 3 — web/Samsung in sola lettura e chiusure

`GET /api/v3/arena` autenticato deve mostrare tre card "Preparato · in pausa". Prova web → socket dal container reale
(UID effettivo) prima di dichiarare la chiusura manuale operativa (matrice §6). Se non certificata, la chiusura dal
Samsung resta **non dichiarata**; l'arresto delle nuove aperture resta disponibile da Termius (`pause.flag`).

## Fase 4 — T0 (solo con OK esplicito)

1. Credenziali censite senza stamparle: `/etc/superbot-arena/deepseek.env` (DEEPSEEK_API_KEY, 0600), chiavi
   OpenRouter con limite 6 USD ciascuna, credito DeepSeek limitato. `V3_ARENA_ALLOW_INFERENCE=1` per qwen/minimax.
2. Istantanea dell'universo entro 6 h: `sudo -E $P -s -m backend.v3.arena.universe_cli --out /opt/superbot-ai-arena-paper/universe_T0.json` (stessi 27 simboli).
3. `T0=$(date +%s%3N)` e `sudo -E DESK_MODE=paper $P -s -m backend.v3.arena.trial_setup activate --day <ARENA_DAY> --t0-ms $T0 --confirm AVVIA-GARA-PAPER-T0-$T0 --approved-by <nome> --universe-snapshot /opt/superbot-ai-arena-paper/universe_T0.json --approved-total-budget-usd 18`
4. `sudo systemctl start superbot-arena-runner@deepseek superbot-arena-runner@qwen superbot-arena-runner@minimax`
5. Primo controllo dopo il primo ciclo: `trial_setup inspect`, `inference_trace.jsonl` (modello, token, latenza),
   spesa per AI nel registro.

**Dopo T0+72h** i runner restano `halted` (`arena_trial_expired`): nessuna nuova chiamata AI, nessuna nuova apertura.
Le uscite continuano finché `can-stop-exit` = 0 per ogni AI. Nessun rinnovo automatico.

**Emergenza**: `pause.flag` nelle tre run (stop alle nuove aperture), poi `systemctl stop superbot-arena-runner@*`;
mai fermare `superbot-arena-exit@*` con posizioni aperte.
