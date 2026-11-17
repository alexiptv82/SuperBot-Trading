# AI Arena — matrice d'installazione PAPER sul VPS (NON eseguita)

Nulla di questo documento è stato eseguito. Ogni passo richiede l'OK esplicito dell'utente. Falco, Toro, il Brain
storico, il bridge RC84 e HI-TV non vengono toccati. Le tre run dell'Arena vivono solo in `/opt/superbot-ai-arena-paper`.

## 0. Prerequisiti da verificare sul VPS (sola lettura)

| Verifica | Comando (sola lettura) | Atteso |
|---|---|---|
| Python e SQLAlchemy del target | `/opt/superbot-v3-rc70-stage/.venv/bin/python3 -c 'import sys,sqlalchemy;print(sys.version,sqlalchemy.__version__)'` | versione su cui i 6 test di base passano (qui falliscono con Python 3.13) |
| UID/GID del processo web | `docker exec <container-web> id` | se `uid=0`: il socket root-only basta; se non-root: serve il gruppo dedicato (§3) |
| Remap dei namespace utente | `docker info --format '{{.SecurityOptions}}'` | senza `userns`: il GID numerico nel container coincide con quello dell'host |
| Spazio libero | `df -h /opt /run` | margine per tre journal SQLite |
| Bitget raggiungibile dal VPS | `curl -s https://api.bitget.com/api/v2/public/time` | `code 00000` |

## 1. Codice (stage separato)

* Copiare il ramo di questa PR in `/opt/superbot-arena-stage` (nuova cartella), con venv proprio o riusando lo
  stage RC70 solo in lettura.
* **Correzione `contracts.py` (BTC/ETH con leva exchange 150×)**: riguarda anche il Brain storico. Va decisa e
  installata a parte; senza, l'Arena non valuta mai BTC ed ETH.

## 2. Run PAPER (in pausa, mandato non approvato)

```
mkdir -m 0700 /opt/superbot-ai-arena-paper
python -m backend.v3.arena.universe_cli --out /opt/superbot-ai-arena-paper/universe_T0.json   # rifare a T0
python -m backend.v3.arena.readiness_cli                                                  # exit 2 finché mancano prove
for p in deepseek qwen minimax; do DESK_MODE=paper python -m backend.v3.arena.prepare --provider $p \
  --root /opt/superbot-ai-arena-paper --day <AAAA-MM-GG> --trial-start-ms <T0 comune> --confirm-capital 2000; done
```

Le tre AI ricevono lo stesso `trial-start-ms`. Se l'istantanea a T0 cambia la lista dei simboli, va aggiornata la
config prima di `prepare`, uguale per tutte e tre.

## 3. Canale di chiusura (bridge Arena)

* Cartella del socket: `install -d -m 0700 -o root -g root /run/superbot-arena-close` (web root), oppure, con web
  non-root, `install -d -m 0710 -o root -g <GID dedicato> /run/superbot-arena-close` e
  `V3_ARENA_CLOSE_GROUP_GID=<GID>` in `/etc/superbot-arena/bridge.env`. Al container web si aggiunge
  `--group-add <GID>`. Mai 0777, mai il web come root solo per questo.
* Servizio: `deploy/arena-paper-services/superbot-arena-close-bridge.service` (senza rete, nessuna sezione di installazione).
* Prova reale UID/GID eseguita qui (`test_socket_real_uid.py`): un processo `nobody` con il GID dedicato raggiunge il
  socket, senza GID viene rifiutato. Sul VPS va ripetuta dal container web (§6).

## 4. Servizi per AI (tre volte, `%i` = deepseek, qwen, minimax)

1. `/etc/superbot-arena/trial.env` (vedi `trial.env.example`).
2. `superbot-arena-exit@%i.service`: proprietario unico delle uscite della run; heartbeat e lease nella run.
3. `superbot-arena-runner@%i.service`: legato al servizio uscite. Resta `halted` finché il mandato non è approvato e
   `pause.flag` esiste.
4. Spesa AI, solo dopo decisione su prezzi, tetti e ragionamento (`ARENA-PREZZI-RAGIONAMENTO-BUDGET-20261117.md`):
   * DeepSeek: `DEEPSEEK_API_KEY` in `/etc/superbot-arena/deepseek.env` (0600);
   * Qwen/MiniMax: chiavi in `/etc/superbot-brain-ai-arena/openrouter-keys.json` (0600) e
     `V3_ARENA_ALLOW_INFERENCE=1` in `/etc/superbot-arena/<provider>.env`. Il limite della chiave oggi deve essere
     ≤ 2 USD (`KEY_LIMIT`).
5. Approvazione dei tre mandati e rimozione dei tre `pause.flag` **nello stesso momento** (T0 comune).

## 5. Web e app (Samsung)

* Container web: `/opt/superbot-ai-arena-paper` montato **in sola lettura**; `/run/superbot-arena-close` montato
  (solo il socket). Variabili: `V3_ARENA_READONLY_ENABLED=1`, `V3_ARENA_TRIAL_DAY=<giorno>`,
  `V3_ARENA_ALLOW_MANUAL_CLOSE=1`, `V3_ARENA_CLOSE_SOCKET=/run/superbot-arena-close/arena.sock`, oltre a
  `DESK_MODE=paper` e `TRADING_MODE=paper` già presenti.
* Build frontend: `REACT_APP_BRAIN_ARENA_SHADOW_API=1`, `REACT_APP_ARENA_MANUAL_CLOSE=1`.
* Prova eseguita qui: build di produzione con quei flag; percorso completo a 320 px (Galaxy S9+) e 360 px
  (Galaxy S24) senza scorrimento orizzontale né errori, chiamate solo a `/api/v3/arena/qwen/close…`
  (`frontend/e2e/arena-mobile-smoke.js`, API simulate).

## 6. Prove sul target prima di dichiarare operativa la chiusura

| Prova | Come | Atteso |
|---|---|---|
| Web → socket | `docker exec <web> python3 -c "from backend.v3.arena import close_bridge as C; print(C.send('status','qwen',{'request_id':'req-0000000000000000'}))"` | `ArenaBridgeError 404 request_not_found` (canale vivo); `arena_bridge_unavailable` = permessi o mount errati |
| Servizio uscite sano | `GET /api/v3/arena/qwen/annotations` | `manual_close_ready: true` |
| Chiusura reale PAPER | una posizione, dall'app | `pending` → `closed` entro il ciclo del servizio uscite; un `paper_close` con motivo `manual` nel journal |
| Prezzo mancante / crash | arresto del servizio uscite con richiesta in volo, poi riavvio | `pending`, poi `closed` alla ripresa; oltre ~12 minuti `unconfirmed` |
| Backup / ripristino | copia di journal + `*.jsonl` e `collect_arena_learning_evidence` sulla copia | stesse catene di hash, motivo umano legato |

## 7. Ritorno indietro

Fermare `superbot-arena-runner@*`, poi `superbot-arena-exit@*`, poi il bridge Arena. Togliere le quattro variabili web e
ricompilare il frontend senza flag. Le run in `/opt/superbot-ai-arena-paper` **non si cancellano** (memoria).
