# Audit integrato pre-rilascio — SuperBot V3 — Claude — 09/11/2026

**SHA verificato:** `0637e01b2b41a4c89fdbe7473bdc867ee5c58860` (PR #80 Draft, head remota uguale al checkout, working tree pulito).
**Modalità:** sola lettura, offline. Nessuna modifica a codice, strategie, parametri, VPS o dati operativi; nessun merge/deploy/reset/riavvio/ordine. Rete esterna rifiutata durante i test (proxy su porta chiusa), nessun segreto. Le sonde girano solo su directory temporanee sintetiche.

## 1. Stack delle PR e provenienza

| PR | Head | Contenuta in RC84 | Note |
|---|---|---|---|
| #80 RC84 | `0637e01` | sì (HEAD) | base = branch RC82, **non main** |
| #79 RC82 | `1e64684` | sì | |
| #78 RC81 | `29eb757` | sì | |
| #77 RC80 | `50b75b9` | sì | |
| #75 RC78 | `b6eaa17` | sì | |
| #74 RC74 Brain chiusura singola | `91214f9` | sì | |
| #73…#70 | | sì | |
| **#76 RC79 diagnosi post-trade** | `35ba0c4` | **no** | ramo fratello da RC77 (4 file, solo osservabilità); fusione simulata senza conflitti |

- Tutte le PR della catena sono **Draft/aperte**; nessuna è fusa in `main`.
- `main` (`fb38267`) non è antenato di RC84: RC84 ha 485 commit in più, `main` ne ha 2 in più (PR #30/#31, `ops/f0/*`). La fusione simulata (`git merge-tree`) è **senza conflitti**.
- Tutti i commit RC84 portano `[skip ci]`: **nessuna CI GitHub** attesta questo SHA. Tutte le prove sotto sono esecuzioni locali in sandbox.

## 2. Test eseguiti

| Suite | Interprete | Risultato |
|---|---|---|
| Backend esteso, esclusi auth/profiles | Python 3.13 | 6 801 PASS / **32 FAIL** / 3 xfail |
| Backend completo, **inclusi** auth/profiles, dipendenze di `requirements.txt` | **Python 3.11** (Dockerfile.desk e CI) | 6 841 PASS / **34 FAIL** / 3 xfail |
| `test_auth_flow.py` + `test_profiles_engine.py` | Python 3.11 | **42/42 PASS** |
| Jest (13 suite) | Node 22 | 109/109 PASS |
| Build React `CI=true` | Node 22 | Compiled successfully |
| Copia dei test F3 con fixture allineata (solo scratch) | Python 3.13 | 37/37 PASS |

Il frontend non è cambiato tra `cd6436f` (dove ho eseguito Jest e la build) e `0637e01` (solo documentazione).
**La suite estesa NON è verde.** Nessuno dei FAIL sotto è contato come superato.

## 3. Classificazione dei fallimenti (riprodotti, nessuno mascherato)

Datazione: stessi file eseguiti sulle head delle PR #70→#79.

| # | Test | Causa riprodotta | Dal | Tipo | Impatto prodotto |
|---|---|---|---|---|---|
| 20 | `test_brain_f3_boundaries.py` | `PolicyFixture` del test non ha `max_loss_margin_fraction`/`min_leverage`/`max_leverage`, letti da `brain_f2/engine.py:89` (`_policy_hash`) dal commit `047d2b2` (06/11, profilo 75 USDT/leva adattiva). Con la fixture allineata, in una copia nello scratch, **37/37 PASS**. | ≤ RC70 | test obsoleto | nessuno sul codice; però **la verifica della firma operatore F3 oggi non è coperta dalla suite** |
| 1 | `test_desk_view.py::test_close_position_rules` | `command_close_position` controlla `close_worker_ready and can_close_position` insieme. Un bot vecchio con heartbeat fresco riceve «Il bot non sta rispondendo» invece di `CLOSE_OLD_BOT_MESSAGE`, che diventa irraggiungibile in quel ramo. Il codice 409 è corretto. | RC73 (`0f564eb`) | **difetto di messaggio** (UX) | nessuna chiusura sbagliata; diagnostica fuorviante per l'utente |
| 1 | `test_live_view.py::test_live_page_tells…` | `live_view.build_portfolio(now=…)` chiama `dv.can_close_position(hb)` **senza** `now`: il test usa `NOW=1_800_014_400` (2027), quindi l'heartbeat risulta nel futuro. | ≤ RC70 | difetto di propagazione del clock (testabilità) | nessuno in produzione (`now=None`) |
| 1 | `test_long_s25.py::test_engine_and_brain_files_are_unchanged_by_this_work` | hash fissato di `brain.py`, cambiato intenzionalmente in RC82 (`_append_json_line`) | RC82 | pin obsoleto | nessuno; serve una decisione esplicita di ri-pin |
| 9 | `test_superbot.py` | test di integrazione verso un server live: `REACT_APP_BACKEND_URL` vuoto produce `MissingSchema` | storico | ambiente/legacy | non eseguibile offline |
| **+2 (solo 3.11 completo)** | `test_v3_rc80_paper_stop_hardening.py::test_other_process_cannot_close_under_the_writer_lock`, `::test_open_but_unlocked_fd_is_not_ownership` | `test_auth_flow.py:28` e `test_profiles_engine.py:25` fanno `os.chdir(_TMP)` **all'import** senza ripristino; il sottoprocesso RC80 usa `PYTHONPATH=".:backend"` relativo e poi `ModuleNotFoundError: desk`. Riprodotto con ciascuno dei due file + RC80; da soli i test RC80 passano 30/30 (4 esecuzioni). | da quando i due file convivono | **isolamento dei test** | nessuno sul prodotto; **una CI 3.11 sull'intera cartella sarebbe rossa** |

**Dipendenze auth/profiles:** sono dichiarate in `backend/requirements.txt` (`sqlalchemy==2.0.28`, `fastapi==0.110.0`, `pyjwt`, `httpx==0.27.0` …). `sqlalchemy==2.0.28` **non si importa su Python 3.13** (`TypingOnly` AssertionError); si importa su 3.11 e 3.12. Deploy (`Dockerfile.desk`) e CI usano 3.11, le unità exit-only usano un venv 3.12: compatibili. Va però fissato l'interprete per i collaudi.

## 4. Difetti dimostrati

| ID | Gravità proposta | Descrizione | Prova |
|---|---|---|---|
| D1 | **P1 (gate rilascio)** | **Claim contabili RC84 invisibili in API/UI.** Con un claim pendente (storico non scrivibile) l'overview Falco mostra `open_positions=0`, `closed_trades=1`, `realized_pnl=5.03`, equity aggiornata, e nessun campo «claim/riconciliazione». Lo stato si vede solo in `heartbeat.json` (`paper_close_claims`) e nei log; un conflitto richiede un intervento umano che nessuno vede. | `probes/probe_claim_visibility.py` (dati sintetici) |
| D2 | **P1 (gate rilascio Brain)** | **Brain: nessuna mutua esclusione tecnica fra runner `legacy` ed exit-worker.** `wiring.main` ha `--exit-mode legacy` di default: il runner possiede monitor e comandi e **non** acquisisce `.exit_service.lock` né il fence `.brain-paper-open.lock`. `exit_worker --start-paper` richiede `--legacy-exits-disabled`, che il codice stesso dichiara «operator assertion only». Nulla impedisce due proprietari contemporanei; restano solo l'idempotenza del journal (`event_id` UNIQUE) e la rinomina atomica della richiesta. | ispezione `runner.py:82-90,113-128`, `wiring.py:263-310`, `exit_worker.py:163-168` |
| D3 | P2 | Copertura F3 (firma operatore/politica) assente dalla suite a causa della fixture obsoleta (20 FAIL). | §3 |
| D4 | P2 | Isolamento dei test: `os.chdir` a livello modulo in auth/profiles rompe 2 test RC80 nel run completo. | §3 |
| D5 | P3 | Messaggio «bot non risponde» al posto di «versione precedente» (desk_view). | §3 |
| D6 | P3 | `live_view` non propaga `now` a `can_close_position`. | §3 |
| D7 | P3 | Pin hash di `brain.py` obsoleto (`test_long_s25`). | §3 |
| D8 | P3 | `sqlalchemy==2.0.28` incompatibile con Python 3.13. | §3 |

## 5. Brain exit-worker — cosa manca per un responsabile unico delle chiusure

Già presente e verificato da test (RC83 + suite attuale): lease POSIX esclusivo fra istanze dell'exit-worker, heartbeat con token, gate `exit_service_healthy` su ogni OPEN in modalità `sidecar`, fence condiviso OPEN/CLOSE, chiusura manuale anche con AI in pausa, verifica read-only del journal all'avvio.

Manca:
1. **Esclusione reciproca runner `legacy` ↔ exit-worker.** Per esempio: il runner legacy rifiuta di partire se `.exit_service.lock` è detenuto, e l'exit-worker rifiuta se un runner legacy della stessa run è vivo (heartbeat recente con `exit_mode=legacy`). Oggi è un'asserzione dell'operatore.
2. **Default sicuro o procedura obbligata**: per la run 2000 USDT, avvio esplicito del runner con `--exit-mode sidecar` e dell'exit-worker, in quest'ordine, con verifica `healthy` in mezzo.
3. **Unità systemd** (`Type=notify`, `WatchdogSec`, restart) per l'exit-worker e per il runner sidecar: **non presenti nel repository**. Il docstring parla di un template che non esiste.
4. **Visibilità in dashboard** dello stato del sidecar (lease, heartbeat, `last_monitor_ms`, errori), oggi solo implicita in `brain_single_close_allowed`.
5. **Test di handover**: passaggio legacy→sidecar con posizioni aperte, crash dell'exit-worker durante una chiusura, riavvio, nessuna doppia chiusura e nessuna finestra senza proprietario.

## 6. Rischi ancora da verificare (non dimostrati)

- Stato reale VPS: versioni installate, modalità `exit_mode`, servizi attivi, dati correnti. Non verificabile offline; richiede un preflight read-only su mandato distinto.
- Comportamento reale del sidecar Brain sotto systemd (watchdog, riavvii) e cadenza dei controlli in produzione.
- Dashboard in browser autenticato e su Android: dati mancanti, refresh, rete assente.
- Backup off-host e restore certificati.
- Uscite protettive Falco/Toro su OHLC 15m periodico (15/30 min + durata ciclo): non continue, wick della candela d'ingresso non rigiocato. È una scelta di modello da accettare esplicitamente.
- Residuo RC84: un'orfana del percorso protettivo, se la barra non è più disponibile, blocca la posizione fino a un intervento umano. Claim in conflitto: nessuna procedura operativa scritta.
- `staging-deploy.yml` scrive `DASHBOARD_PASSWORD=superbot2024` (password di bootstrap nota, repository pubblico). `auth.py` la vieta come nuova password, ma va verificato se lo staging è ancora attivo e se quella password consente ancora un primo accesso.
- Integrazione o abbandono di #76 (RC79), oggi fuori dalla catena.
- Due salvataggi di stato aggiuntivi per ogni chiusura non protettiva: nessun problema riscontrato offline, non misurato su disco reale.

## 7. Checklist per il rilascio (PAPER: Falco/Toro 1 000, Brain 2 000)

**Bloccanti**
- [ ] D1: esporre `paper_close_claims` (pendenti/conflitto) in `/api/v3/overview` e in UI con allarme; documentare la procedura umana per i conflitti.
- [ ] D2: esclusione tecnica runner legacy ↔ exit-worker, oppure avvio obbligato in `sidecar`, con test di handover.
- [ ] Unità systemd Brain (exit-worker + runner sidecar) nel repository, revisionate.
- [ ] Suite backend verde sull'interprete di deploy (3.11): correggere D3, D4, D7 o rilasciarli con motivazione scritta; `test_superbot.py` fuori dalla suite offline o marcato integrazione.
- [ ] CI GitHub su uno SHA candidato senza `[skip ci]` (backend 3.11 + Jest + build).
- [ ] Release candidate unica e pinned (oggi catena di Draft #70→#80 non fusa; decidere su #76 e sui 2 commit di `main`).
- [ ] Backup off-host + restore provati; storico/learning/lessons/errors preservati (regola 4).
- [ ] Preflight VPS read-only su mandato distinto: versioni, servizi, `DESK_MODE=paper`, Secret.
- [ ] Browser autenticato + Android: Falco/Toro/Brain, allarmi stop, dati mancanti, Brain non disponibile.
- [ ] Consenso esplicito dell'utente per la nuova run PAPER.

**Non bloccanti (consigliati)**
- [ ] D5 (messaggio vecchio bot), D6 (clock `live_view`), visibilità dello stato del sidecar Brain, verifica della password di staging.

---
*Sonde (solo scratch/tmp, nessun dato reale): `claude/probes/probe_claim_visibility.py`, `claude/probes/test_f3_fixture_aligned.py`.*
