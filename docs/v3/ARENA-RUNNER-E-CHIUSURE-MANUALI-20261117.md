# AI Arena — runner PAPER indipendenti e chiusure manuali con motivazione (Issue #100)

Ramo: `work/arena-paper-runners-manual-close-20261117` (base `work/arena-classic-archive-learning-foundation-20261117`).
Stato: **codice e test locali**. Nulla è installato, avviato o abilitato. Nessun credito AI usato.

## 1. Cosa esiste ora

| Pezzo | File | Note |
|---|---|---|
| Runner per AI (DeepSeek prova, Qwen, MiniMax) | `backend/v3/arena/runner.py` | Riusa il Brain V3 in modalità *sidecar*; cartella propria `<root>/<provider>/<run_id>`; journal, budget e heartbeat propri. |
| Preparazione run (in pausa, mandato NON approvato) | `backend/v3/arena/prepare.py` | Mai sovrascrive; rifiuta le radici di Falco/Toro/Brain storico; stessa politica di rischio per le tre AI (hash comune). |
| Configurazioni 2.000 USDT | `backend/v3/arena/configs/{deepseek,qwen,minimax}.json` | Copie della config Brain 2000 PAPER; cambia solo modello/prezzi. |
| Provenienza per AI | `deepseek_l5.py`, `cycle.py`, `wiring.py` | `originating_ai` = provider su ogni decisione/apertura; budget per provider. Default storico invariato. |
| Chiusura manuale + motivazione | `backend/v3/arena/manual_close.py` | Libreria lato host (vedi §2). |
| Canale host dedicato | `backend/v3/arena/close_bridge.py`, `close_bridge_server.py` | Socket `/run/superbot-arena-close/arena.sock`, separato dal bridge storico. |
| Rotte autenticate | `backend/v3/arena/close_router.py` | Montate solo con opt-in (§3). |
| Guardia sola lettura | `backend/v3/cutover_gate.py`, `backend/server.py` | Apre solo le due POST dell'Arena; `/api/v3/brain/close` invariata. |
| Dashboard | `frontend/src/components/ArenaCloseControls.js`, `arenaCloseModel.js`, `pages/BrainArena.js` | Chiusura per AI con conferma e motivo, dietro flag. |

## 2. Protocollo della chiusura manuale (per ciascuna AI)

1. `POST /api/v3/arena/{provider}/close` `{"position_id", "request_id"}` — sessione obbligatoria; il web inoltra al
   processo host; l'host rivalida ambiente PAPER, manifest della run (provider, run_id, paper, 2000), posizione aperta,
   servizio uscite **di quella run** sano (lease + heartbeat), nessuna richiesta già in volo; poi registra la richiesta
   (append-only, catena di hash) e scrive `close_request.json` nel formato del Brain. Il servizio uscite è l'unico che chiude.
2. `GET /api/v3/arena/{provider}/close/{request_id}` — stato letto dal **journal**:
   `pending` → `closed` (paper_close con motivo `manual`) | `closed_by_other_exit` (stop/target prima) |
   `failed` (es. `price_unavailable`, `expired`) | `unconfirmed` (il servizio non ha mai preso in carico).
3. `POST /api/v3/arena/{provider}/close/{request_id}/annotation` `{"reason", "note"?}` — solo dopo `closed`.
   Motivi: `profit_protection`, `loss_reduction`, `trend_change`, `other`, `unspecified` (scelta esplicita). Nota ≤ 280
   caratteri, una riga. Una sola motivazione per posizione, legata a `position_id` e `close_event_id`. Mai dedotta dal PnL.
4. `GET /api/v3/arena/{provider}/annotations` — elenco + `manual_close_ready`.

Registri nella cartella della run: `arena_close_requests.jsonl`, `human_close_annotations.jsonl` (append-only, catena
SHA-256; un file alterato blocca la lettura con `registry_corrupt`). Il journal resta l'unica fonte dei trade: la
motivazione non crea un secondo evento di chiusura, quindi niente doppio conteggio.

Le AI dell'Arena **non** passano mai da `/api/v3/brain/close`.

## 3. Interruttori (tutti spenti per default)

| Variabile | Dove | Effetto |
|---|---|---|
| mandato `approved=true` + rimozione `pause.flag` | cartella della run | senza, il runner resta `halted` e non chiama il modello |
| `V3_ARENA_ALLOW_INFERENCE=1` | runner Qwen/MiniMax | senza, OpenRouter rifiuta (NO_TRADE per AI non disponibile) |
| `V3_ARENA_READONLY_ENABLED=1`, `V3_ARENA_TRIAL_DAY` | web | rotta di lettura `/api/v3/arena` |
| `V3_ARENA_ALLOW_MANUAL_CLOSE=1` + `V3_ARENA_CLOSE_SOCKET=/run/superbot-arena-close/arena.sock` | web e host | rotte di chiusura e guardia di sola lettura |
| `REACT_APP_BRAIN_ARENA_SHADOW_API=1`, `REACT_APP_ARENA_MANUAL_CLOSE=1` | build frontend | sezioni dell'esperimento e pulsanti di chiusura |

## 4. Test locali eseguiti

* `backend/v3/arena/` — 86 test superati (runner, preparazione, chiusura manuale: idempotenza, doppio clic
  concorrente, richiesta in volo, id riusato, prezzo mancante, servizio uscite assente, mancata presa in carico
  (timeout), crash dopo la presa in carico e ripresa, uscita automatica in corsa, registri manomessi, copia di backup e
  ripristino verificabile; API autenticata, guardia di sola lettura, socket UNIX reale).
* Frontend: 19 suite, 156 test superati (`react-scripts test`).
* Suite backend completa: vedi rapporto della PR (7 fallimenti preesistenti identici sul ramo base).

## 5. Blocchi che richiedono una decisione dell'utente

1. **Ragionamento**: DeepSeek usa *thinking* attivo; per Qwen/MiniMax la config usa `omit`. Va scelto se uniformare.
2. **Prezzi Qwen/MiniMax** (2,00/8,00 per milione di token) sono stime prudenziali da verificare sul listino.
3. **Budget OpenRouter**: limite della chiave vs tetto giornaliero della config.
4. **Avvio**: approvazione dei mandati, `V3_ARENA_ALLOW_INFERENCE`, installazione dei servizi (runner, servizio uscite,
   bridge host) e mount in sola lettura nel container web: nessuno di questi passi è stato fatto.
5. Il giorno comune di partenza (`trial_start_ms`) deve essere lo stesso per le tre AI.

## 6. Cosa manca per la dashboard dell'app Samsung

* Build con i due flag React e deploy del frontend (autorizzazione).
* Server con le variabili del §3 e il socket montato nel container web.
* Servizi uscite delle tre run attivi: senza, la chiusura resta disabilitata con il messaggio dedicato.
* Verifica a schermo (larghezza telefono) dopo il deploy.
