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

### Limite di spesa: cosa è garantito e cosa no (aggiornato dopo la revisione ChatGPT)

* **Prenotazione**: il costo massimo di una chiamata è ora un **limite superiore vero** (`worst_case_units`): byte UTF-8
  del testo inviato come token in ingresso (nessun tokenizer ne produce di più) + `max_tokens` in uscita (il fornitore
  tronca l'uscita, ragionamento compreso). Una chiamata fallita sull'Arena è registrata a quel limite, mai sotto. Costo
  massimo per chiamata a DeepSeek circa 0,010 USD: la prenotazione non frena il lavoro normale, solo gli ultimi centesimi
  del tetto.
* **Resta fuori dal nostro controllo**: la fatturazione reale del fornitore (listino che cambia, sconti di cache). Il
  registro usa i prezzi della config (listino di picco).
* **Qwen e MiniMax**: tetto lato fornitore = chiave OpenRouter con limite esattamente 6 USD (controllato a ogni chiamata).
* **DeepSeek**: **nessun tetto lato fornitore garantito da questo codice**. Il tetto è interno (2 USD/giorno, 6 USD
  cumulativi) con avviso a 5 USD. **Non abbassare il saldo del conto DeepSeek**: è un saldo di account, condiviso con il
  Brain storico, che si fermerebbe. Non dichiarare "18 USD garantiti": per DeepSeek sono **un limite interno con margine**.
  Da verificare nella console DeepSeek (non fatto): se esistono chiavi API separate con limite proprio, usarne una per l'Arena.
* **Avviso**: `trial_setup inspect` mostra la spesa per AI (`ai_spend_total_usd`, `ai_spend_today_usd`) e l'avviso
  `<ai>:AI_SPEND_ABOVE_5.00_USD`. Da controllare a mano a ogni verifica; non ferma nulla da solo.

## Stato del rilascio (aggiornato)
`--replace-prepared` scrive lo stato della sostituzione su disco (`/opt/superbot-v3-backups/.arena-replace-tx`) PRIMA
di fermare o spostare qualunque cosa, e ha il trap EXIT/HUP/INT/TERM scritto da ChatGPT. Dopo **SIGKILL, blackout o
sessione persa** (dove nessun trap scatta) si recupera con `--recover-replace`: idempotente, mai cancella, riporta run,
stage e uscite allo stato precedente. Finché il file esiste, una nuova sostituzione è rifiutata. Provato con `kill -9`
dopo l'archivio e dopo il salvataggio dello stage. Corretto anche un difetto del rollback: se l'archiviazione falliva a
metà, le run originali finivano tra i "falliti" invece di restare al loro posto.

**Eseguire in una sessione che non muore con Termius:**
`sudo systemd-run --unit=arena-replace --collect --wait --pty bash $S --replace-prepared --sha <SHA>` oppure dentro `tmux`.

## Fase 1 — sostituzione delle tre run preparate (uscite fermate solo con 0 posizioni)

```
S=/tmp/arena-prep.sh
curl -fsSL https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/<SHA>/deploy/scripts/arena-prepare-paused-runs-20261118.sh -o $S
sudo bash $S --inspect --sha <SHA> --day <ARENA_DAY>
sudo bash $S --replace-prepared --sha <SHA>
```

Atteso: `ZERO_POSITIONS_VERIFIED=TRUE`, `OLD_RUNS_ARCHIVED=...`, `NEW_RUNS_PREPARED_PAUSED_NO_T0=TRUE`,
`RESULT=PREPARED_RUNS_REPLACED_EXITS_HEALTHY`. Rifiuti previsti: runner Arena attivo, Brain storico non attivo,
`can-stop-exit` negato, archivio su altro disco. Se la sostituzione fallisce, il wrapper prova a ripristinare le run precedenti, lo stage precedente
e i servizi di uscita. `ROLLBACK_RESTORED=TRUE` significa che le richieste di start delle uscite
sono state inviate, **non** che gli heartbeat siano automaticamente verificati: prima di riprovare,
eseguire `trial_setup inspect` e accertare le tre `exit_service_healthy=true`.
Se appare `MANUAL_RECOVERY_REQUIRED=TRUE`, NON avviare i runner e conservare l'archivio; dopo una sessione persa:
`sudo bash $S --recover-replace --sha <SHA>` (atteso `RECOVERY_DONE=TRUE` oppure `NOTHING_TO_RECOVER=TRUE`), poi `inspect`.
Il bridge resta acceso con il codice precedente in memoria fino a un riavvio separato.

## Fase 2 — prova a secco sul VPS (nessun credito)

```
P=/opt/superbot-arena-stage/.venv/bin/python3; export PYTHONPATH=/opt/superbot-arena-stage:/opt/superbot-arena-stage/backend
sudo -E DESK_MODE=paper $P -s -m backend.v3.arena.smoke --day <ARENA_DAY>
```

Atteso: per ogni AI `state: running`, `opened: 0`, `model_calls` vicino a 27 (meno i simboli senza dati, elencati),
`real_runs_untouched: true`. Durata misurata in locale: vedi PR. Le run vere restano `PREPARED_PAUSED_NO_T0`.

## Fase 3 — web/Samsung in sola lettura e chiusure

`GET /api/v3/arena` autenticato deve mostrare tre card "Preparato · in pausa". Il collegamento app → bridge si verifica,
in sola lettura, con:

```
sudo bash /opt/superbot-arena-stage/deploy/scripts/arena-bridge-web-check-readonly-20261118.sh superbot
```

Esegue DENTRO il container web (con il suo UID/GID reale) una sola richiesta `status` per un id inesistente. Risultati:
`CHANNEL_OK` (404 atteso), `PERMISSION_DENIED_ON_SOCKET_NEEDS_DEDICATED_GROUP` (socket root 0600 e web non-root: il
caso più probabile oggi, serve `V3_ARENA_CLOSE_GROUP_GID` nel bridge e `--group-add` nel container, vedi matrice §3),
`SOCKET_MISSING...` (mount assente), `BRIDGE_NOT_LISTENING`. **Provato in locale con un utente reale** per i diversi
casi; **non** provato sul container vero. Con qualunque esito diverso da `CHANNEL_OK` la chiusura dal Samsung **non è
dichiarata operativa**; il fallback sicuro è fermare le nuove aperture con `pause.flag` da Termius. Anche con
`CHANNEL_OK` resta da provare una chiusura vera su UNA posizione PAPER, con il tuo OK.

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
