# RC84 — chiusure PAPER non protettive: commit contabile in due fasi (Claude, 08/11/2026)

PR #80 DRAFT, branch `cursor/rc84-running-stop-health-telegram-20261108`.
Base di questo lavoro: `2e2aad27b48627cef7807ac75c5ea1b54bbb3ad8`. **Commit codice+test: `5bc0f48bddea37fc353d1cfd92f7fdaf3ba11ab9`** (revisione ChatGPT #6727282024: P0-RC84-A, P0-RC84-B).
Nessun merge/deploy/VPS/riavvio/reset/ordine. Diario canonico non toccato.

## Problema
- **P0-A**: il conto poteva essere salvato «chiuso» con storico o learning mancanti; la notifica veniva solo soppressa.
- **P0-B**: dopo un salvataggio fallito i registri contenevano già il fill, il conto no; un nuovo tentativo a un altro istante scriveva un secondo terminale della stessa posizione.

## Protocollo (solo PAPER; `backend/desk/cli.py`, parametro opzionale in `long_s25.py`)
Per regole/Claude, manuale singola, «Chiudi tutto» PAPER, parziale e S25 a tempo:
1. **Pre-controllo**: se nei registri della run esiste già un terminale della stessa posizione (symbol, id, open_ms, side) la chiusura è **bloccata**, il conto e i registri non cambiano, viene segnalata (`HB["paper_close_blocked"]`, `last_action` per manuale/Chiudi tutto, `skipped["registro_incoerente"]` per S25).
2. **Fase 1 — checkpoint**: chiusura in memoria + **claim** con il record esatto (`state["paper_close_claims"]`, id univoco run|symbol|id|open_ms|close_ms|tipo|net) salvati **insieme** in `state_v2.json`. Se il salvataggio fallisce nei registri non si scrive nulla.
3. **Fase 2 — registri**: storico e learning scritti **dal record del claim** (mai ricalcolato), append-only; una riga identica già presente non si riscrive; un terminale incompatibile → `conflict`, nulla scritto, claim conservato e segnalato (`HB["paper_close_claims"]["conflict"]`).
4. **Fase 3 — definitiva**: claim provati rimossi, stato risalvato. **Solo ora** Telegram, legato al claim (non a simbolo+netto), al massimo una volta; un errore Telegram non annulla nulla.
5. **Ripresa**: all'avvio di ogni `run_cycle` (e in ogni commit manuale) i claim pendenti vengono completati con lo stesso record. Un claim non provabile resta pendente e visibile.

Le parziali hanno identità propria (close_ms, fraction, net): più parziali legittime restano distinte; un terminale successivo della stessa posizione non le rende incoerenti.
**Invariati:** `record_close` (identico alla base, usato da LIVE), ordine notify→record nei rami LIVE, stop protettivi RC82, strategie, Claude, prezzi, leve, size, formule economiche, formato delle righe storiche.

## Test — `backend/tests/test_v3_rc84_telegram_durable_close.py` (36)
Per ciascun percorso `manual|partial|rules|s25`: positivo (al momento del Telegram: conto definitivo su disco, 1 riga storico, 1 learning, stessi campi del conto); storico non scrivibile e learning non scrivibile (claim durevole, nessun Telegram, ripresa → 1+1 righe, 1 Telegram, stesso close_ms del claim); checkpoint fallito (0 righe, posizione aperta su disco; nuovo tentativo a +60 s = unico fill); crash dopo i registri prima del salvataggio finale (riavvio a +1 h completa lo stesso fill); terminale incompatibile preesistente (bloccato, storico byte-identico, nessun learning, nessun Telegram). Inoltre: nuova richiesta dopo crash non crea secondo terminale (manual/rules/s25), due parziali legittime distinte attraverso un crash, parziale pendente + terminale successivo non è conflitto, Chiudi tutto PAPER con storico non scrivibile, Telegram giù, notifica legata all'identità del claim, LIVE senza claim e con `record_close` originale. Ogni test verifica l'invariante: ogni fill dei registri è nel conto salvato, mai due terminali, nessuna posizione fantasma.
Sul codice di `2e2aad2` (con la sola costante `CLAIMS_KEY` aggiunta): **22 dei 34 test di allora falliscono** (tutti i casi registri non scrivibili, checkpoint fallito, crash, terminale incompatibile, parziali, identità notifica).

## Esecuzioni (sandbox, rete rifiutata con proxy su porta chiusa, nessun segreto)
```bash
PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider backend/tests/test_v3_rc84_telegram_durable_close.py   # 36 passed
HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider \
  backend/tests/ --ignore=backend/tests/test_auth_flow.py --ignore=backend/tests/test_profiles_engine.py
cd frontend && CI=true npx --no-install react-scripts test --watchAll=false --runInBand && CI=true npx --no-install react-scripts build
```
| | Base `2e2aad2` | Questo lavoro |
|---|---|---|
| backend esteso | 6 770 PASS / 32 FAIL / 3 xfail | **6 779 PASS / 32 FAIL / 3 xfail** |
| insieme dei 32 FAIL | — | **identico** (0 nuovi, 0 risolti) |
| Jest | — | 109/109 |
| build | — | Compiled successfully |

I 32 FAIL comuni NON sono superati: 20 `test_brain_f3_boundaries.py` (`PolicyFixture` senza `max_loss_margin_fraction`), 1 `test_desk_view.py`, 1 `test_live_view.py`, 1 `test_long_s25.py::test_engine_and_brain_files_are_unchanged_by_this_work` (hash di `brain.py` cambiato da RC82), 9 `test_superbot.py` (server live). `test_auth_flow.py` e `test_profiles_engine.py` non eseguiti (`sqlalchemy` assente).
Nota: una prima esecuzione completa ha mostrato 6 fallimenti manuali dovuti al mio test (timestamp della richiesta su orologio reale, gestore su orologio fissato); corretto nel test, non nel codice.

## Residui
1. Il percorso protettivo (stop/TP/liq) mantiene il protocollo RC82 (registri prima del salvataggio, replay deterministico sulla stessa barra). Se la barra non è più disponibile al riavvio, la riga orfana resta e il pre-controllo blocca le altre chiusure di quella posizione segnalandolo: richiede verifica umana.
2. Un claim in `conflict` (possibile solo con registri alterati dall'esterno dopo il pre-controllo) resta nel conto come chiuso e segnalato; non viene risolto automaticamente.
3. Con un registro permanentemente non scrivibile la chiusura resta pendente (conto chiuso, claim visibile in heartbeat) finché il disco non torna scrivibile; nessuna UI dedicata.
4. Due parziali identiche per close_ms, fraction e net nella stessa posizione non sono distinguibili (impossibile dopo la prima riduzione di quantità).
5. Gate RC84 aperti: browser autenticato/Android, sidecar Brain, backup off-host, nuova run solo con OK.

---

# Integrazione nel ciclo operativo (09/11/2026, base `8591dba8c2152c0e9cb4cc104e7ddcaba09b35de`, revisione ChatGPT #6734234466)

**Commit codice+test: `f0ea0c1d9e9110b439903c19785306c454375ca4`.** Il protocollo a claim non è stato ricostruito; tre guardie nel ciclo, tutte solo PAPER (in LIVE `_unresolved_claims` è sempre vuoto).

1. **Recupero in pausa/riavvio** — `_recover_paper_claims` in `loop_step` subito dopo `process_flags`, anche con bot in pausa e senza posizioni: nessun ciclo di mercato, nessun trade, al massimo un tentativo ogni `CLAIM_RECOVERY_S = 60` s, errori catturati (`HB["paper_close_claims_error"]`). Riusa `_commit_paper_closes`: Telegram solo per i claim provati e rimossi, quindi nessun duplicato. Correzione collegata: se il salvataggio finale fallisce lo stato in memoria torna ai claim (prima un salvataggio successivo, es. `sync_mode`, poteva rendere definitivo il claim senza avviso).
2. **Reset sicuro** — `_check_portfolio_reset_flag` rifiuta con claim pendenti o in conflitto, prima di `_archive_run`: nessun file toccato né spostato; `last_action` = «rifiutato: N chiusure contabili da riconciliare (M in conflitto); storico e learning non toccati». `reset.flag` (Chiudi tutto) non archivia nulla ed è già coperto dal protocollo a claim.
3. **Nessuna nuova esposizione** — se a inizio ciclo restano claim irrisolti (dopo il tentativo di riconciliazione), come in pausa: decisioni filtrate a `close/partial_close/hold` (niente aperture né DCA), seconde gambe pendenti annullate prima della prima passata protettiva, `long_s25.step(drain=True)` (resta la chiusura a tempo). Stop/TP/liquidazione e chiusure manuali di posizioni non coinvolte restano attive (il blocco per posizione è solo il pre-controllo già esistente).

## Test — `backend/tests/test_v3_rc84_claim_integration.py` (11) + `test_v3_rc84_telegram_durable_close.py` (36)
Ultima posizione chiusa a mano in pausa con claim pendente → `loop_step` (storage rotto: nessun crash e rate limit; poi scrivibile: riconciliazione, 1 avviso, nessun ciclo di mercato, nessun duplicato); riavvio da vero `state_v2.json`; crash nel salvataggio finale della riconciliazione; reset rifiutato (pendente e in conflitto) con file byte-identici e nessuna `archive/`; reset di nuovo possibile dopo la riconciliazione; apertura bloccata con claim e consentita dopo; DCA bloccato con claim di parziale e ripreso dopo la riconciliazione; S25 riceve `drain=True` solo con claim; stop protettivo e chiusura manuale di posizione non coinvolta attivi con claim; LIVE ignora i claim. Senza la patch 8 degli 11 falliscono (gli altri 3 sono controlli di non regressione).

## Esecuzioni (rete rifiutata, nessun segreto)
| | `8591dba` | `f0ea0c1` |
|---|---|---|
| backend esteso (escl. `test_auth_flow.py`, `test_profiles_engine.py`: manca `sqlalchemy`) | 6 779 PASS / 32 FAIL / 3 xfail | **6 790 PASS / 32 FAIL / 3 xfail** |
| insieme dei FAIL | — | **identico** (0 nuovi, 0 risolti) |
| Jest / build (frontend invariato) | 109/109 | 109/109, Compiled successfully |

La suite estesa **non è verde**: i 32 FAIL sono preesistenti (20 `test_brain_f3_boundaries.py` fixture senza `max_loss_margin_fraction`, 1 `test_desk_view.py`, 1 `test_live_view.py`, 1 `test_long_s25.py` hash di `brain.py`, 9 `test_superbot.py` server live).

## Limiti
- Il blocco usa i claim presenti a inizio ciclo: un claim creato e rimasto pendente a metà ciclo blocca dal ciclo successivo (le aperture del ciclo corrente sono già state decise).
- Un claim in conflitto non si risolve da solo: blocca nuove aperture/DCA e il reset finché un umano non interviene.
- Le seconde gambe pendenti vengono annullate (come in pausa) quando ci sono claim irrisolti.
- Nessuna UI per `paper_close_claims` (solo heartbeat/log); restano aperti i gate RC84 (browser autenticato/Android, sidecar Brain, backup off-host, nuova run solo con OK).

---

# Esposizioni nello stesso ciclo (09/11/2026, base `8b486f1d40aaec36e398ef43774fb19bc5106c26`, revisione ChatGPT #6734798159)

**Commit codice+test: `cd6436fc87bbc78b759afd190e78bcf401b824f2`.**

**Difetto confermato** (6 test nuovi fallivano sulla base): `claim_block` era calcolato una volta a inizio ciclo, quindi `close(A)` seguita da `open_long(B)`, `partial_close(A)` seguita da `dca(A)` e l'ingresso S25 dopo una chiusura a tempo passavano mentre il claim era ancora irrisolto.

**Correzione minima** (`cli.py`, parametro opzionale `entries_blocked` in `long_s25.step`; solo PAPER):
- `_settle_claims_now(state, acc)`: subito dopo ogni chiusura non protettiva (regole/Claude, parziale, S25) si salva il conto con il claim e si provano i registri. **Percorso sano invariato**: il claim si risolve (e parte l'avviso) prima della decisione successiva, quindi `close(A)+open(B)` e `partial(A)+dca(A)` avvengono nello stesso ciclo come prima. Un blocco "a claim presente" avrebbe invece rinviato anche le riaperture sane.
- Se il claim resta irrisolto (registro non scrivibile/conflitto): le azioni non di gestione successive (`MANAGE_ACTIONS` = close/partial_close/hold) vengono ignorate con log `[CLAIM]`, `long_s25.step` non apre (`entries_blocked`), le seconde gambe pendenti vengono annullate (come in pausa), prima della seconda passata protettiva.
- S25: un errore di salvataggio nella riconciliazione immediata non è nascosto dal `try/except` di S25: il claim resta irrisolto (blocca gli ingressi) e il commit finale del ciclo ritenta e solleva come per le altre chiusure.
- Seconda chiusura non protettiva della stessa posizione con claim parziale pendente: **ammessa** (è un'uscita); produce un secondo claim con identità distinta. Test contabile: dopo il ripristino 2 righe (parziale + terminale) in storico e learning, 2 avvisi, somma dei netti = chiusure del conto, mai due terminali, nessuna posizione fantasma.
- Invariati: protocollo a claim, LIVE (`_settle_claims_now` ritorna subito), registri append-only, AI, strategie, formule, leve, size, rischio, stop protettivi (RC82), chiusure manuali di posizioni non coinvolte.

**Test** — `backend/tests/test_v3_rc84_same_cycle_exposure.py` (11): per history e learning non scrivibili `close(A)+open(B)`, `partial(A)+dca(A)`, S25 dopo chiusura a tempo (bloccati nel ciclo, poi sbloccati dopo la riconciliazione a inizio ciclo successivo); i tre percorsi sani nello stesso ciclo; seconda chiusura con claim parziale pendente; stop protettivo con claim parziale pendente. Resa robusta la dipendenza dal minuto di esecuzione dei test precedenti (candela relativa all'istante simulato); verificato con orologio fissato a +5/+420/+810/+890 s dentro la barra da 15 min (`test_close_all…` escluso da quel controllo: confronta la data reale del file flag).

**Esecuzioni** (rete rifiutata, nessun segreto)
| | `8b486f1` | `cd6436f` |
|---|---|---|
| backend esteso (escl. `test_auth_flow.py`, `test_profiles_engine.py`: manca `sqlalchemy`) | 6 790 PASS / 32 FAIL / 3 xfail | **6 801 PASS / 32 FAIL / 3 xfail** |
| insieme dei FAIL | — | **identico** (0 nuovi, 0 risolti) |
| Jest / build (frontend invariato) | 109/109 | 109/109, Compiled successfully |

La suite estesa **non è verde**: i 32 FAIL sono preesistenti (20 `test_brain_f3_boundaries.py`, 1 `test_desk_view.py`, 1 `test_live_view.py`, 1 `test_long_s25.py` hash di `brain.py`, 9 `test_superbot.py` server live).

**Limiti**: la riconciliazione immediata aggiunge due salvataggi di stato per ogni chiusura non protettiva (comportamento atteso, non temporale); un claim in conflitto continua a richiedere un intervento umano; nessuna UI per i claim; gate RC84 aperti invariati (browser autenticato/Android, sidecar Brain, backup off-host, nuova run solo con OK).

---

# D1 — visibilità dei claim contabili (09/11/2026, base `0637e01b2b41a4c89fdbe7473bdc867ee5c58860`, revisione ChatGPT #6740016283)

**Commit codice+test: `973fe5722b7c7b8dee8cb25d273c24406652b8bb`.** Solo lettura; motore contabile, claim, strategie, AI, LIVE e Brain invariati.

**Backend** — `GET /api/v3/overview` (già autenticato) aggiunge a Falco e Toro `close_reconciliation`:
`{state: ok|pending|conflict|unknown, pending_count, conflict_count, affected_symbols (≤8, solo [A-Za-z0-9]{1,16}, ordinati, unici), checkpointed_not_final}`.
- `ok`: `paper_close_claims` vuoto/assente in uno stato leggibile; `pending`: claim non provati; `conflict`: claim con `status=conflict` (o conflitto annotato nell'heartbeat se fresco, < 120 s); `unknown`: stato mancante/vuoto o claim malformati — mai `ok` per default.
- Non esposti: `claim_id`, record `rec`, importi, motivi, notifiche. Il Brain non riceve il campo. Nessuna rotta nuova: le rotte restano 5 GET + l'unica POST preesistente `/brain/close`.

**Dashboard** — nuovo `ClaimReconciliationNotice` (`role="alert"`, solo testo, nessun controllo): mostrato in **I tre portafogli** e in **Classici** (Falco/Toro) anche con zero posizioni. Testi distinti per `pending` / `conflict` (intervento umano; aperture, DCA e reset bloccati) / `unknown`. Dice che equity, P&L e trade chiusi «possono includere chiusure non ancora definitive» e che i valori non vengono azzerati né ricalcolati (nessun importo toccato). Overview non raggiungibile o campo mancante → «non verificabile»; portafoglio `not_started` → nessun banner `unknown` (un conflitto resta sempre visibile). Layout, chiusure manuali e `ClassicStopNotice` invariati (i due file `ClassicStopNotice*` non toccati).

**Test**: `backend/tests/test_v3_rc84_claim_visibility.py` (19: pura, endpoint autenticato/401, solo GET, sola lettura di file, Brain assente, recupero, simboli, claim malformati); `ClaimReconciliationNotice.test.js` (11) + 4 test in `ThreePortfoliosNavigation.test.js` (zero posizioni con Brain giù, conflitto→riconciliato, overview assente, nessun controllo/POST).

| | audit `0637e01` (Python 3.11, completo) | `973fe57` |
|---|---|---|
| backend | 6 841 PASS / 34 FAIL / 3 xfail | **6 860 PASS / 34 FAIL / 3 xfail** |
| insieme dei FAIL | — | identico (0 nuovi, 0 risolti) |
| Jest | 109/109 | **124/124** (14 suite) |
| build `CI=true` | Compiled successfully | Compiled successfully |

I 34 FAIL **non sono superati**: 20 `test_brain_f3_boundaries.py` (fixture obsoleta), 1 `test_desk_view.py`, 1 `test_live_view.py`, 1 `test_long_s25.py` (hash `brain.py`), 9 `test_superbot.py` (server live), 2 `test_v3_rc80_paper_stop_hardening.py` (`os.chdir` all'import di auth/profiles).
**Limiti**: `status=conflict` si vede nell'overview solo se persistito nello stato o annotato nell'heartbeat fresco; nessuna procedura operativa scritta per i conflitti; nessuna prova in browser autenticato/Android; D2 e gli altri gate dell'audit restano aperti.

---

# D2 — un solo proprietario delle chiusure Brain PAPER (09/11/2026, base `c6082dfefc26d4ed61aaa3363bb24af45612db8b`, revisione ChatGPT #6740016283)

**Commit codice+test+template: `fcaa2758220e5a42a5d2ba8419424ab898d85d2d`.** Protocollo e procedura: `docs/v3/brain-paper-systemd/README.md`.

**Difetto riprodotto sulla base**: con un exit-worker che detiene il lease, `wiring.main --exit-mode legacy` partiva comunque (3 test nuovi falliscono con `wiring.py`/`runner.py` di `c6082df`).

**Modifiche** (`backend/v3/runner/wiring.py`, `runner.py`, `exit_worker.py`):
- runner `legacy`: acquisisce `LegacyExitFence` (stesso `flock` `.exit_service.lock` dell'exit-worker) **prima** di costruire il runner e lo tiene fino all'uscita; se è occupato esce con 3 `exit_owner_busy` senza creare journal né heartbeat. In `sidecar` non prende il lease (invariato: apre solo con exit-worker sano).
- exit-worker: lease occupato → 3 `exit_owner_busy` (prima finiva in "stopped_unexpectedly"); `--wait-lease-s N` (≤ 600) per il passaggio di consegne; `foreign_exit_owner()` rifiuta l'avvio (3) e degrada ogni tick (nessuna chiusura, aperture bloccate) se l'heartbeat del runner è senza `exit_mode` e più recente di 45 min, oppure illeggibile.
- heartbeat del runner: nuovo campo `exit_mode` (`legacy`/`sidecar`). **Cambio di contratto voluto**: aggiornate 6 attese esatte in `test_v3_runner_runner.py` (2), `test_v3_runner_e2e.py` (1), `test_v3_runner_daily_loss.py` (3), aggiungendo solo quel campo.
- Invariati: strategie, AI, rischio, executor, desk classici, frontend, LIVE (`DESK_MODE≠paper` rifiutato prima di qualunque lease o file).

**Test** `backend/tests/test_v3_rc84_brain_single_exit_owner.py` (21, sottoprocessi reali): exit-worker rifiutato con legacy aggiornato attivo; legacy rifiutato con exit-worker attivo; secondo legacy rifiutato; lease tenuto per tutta la vita del runner e liberato all'uscita; 6 processi concorrenti → 1 proprietario; crash `SIGKILL` → lease liberato e preso dal successore; riavvio senza certificazione ereditata; handover sequenziale (rilascio ≤ acquisizione, attesa < 2 s); attesa limitata fail-closed; heartbeat non aggiornato/obsoleto/sidecar/legacy/corrotto/symlink; worker rifiutato con runner vecchio vivo; worker in servizio che si ritira e poi riprende; lease legacy che non certifica mai il sidecar; due processi che chiudono la stessa posizione → 1 sola `paper_close`; modalità non PAPER rifiutata. Ripetuto 3 volte su Python 3.11: 21/21.

| | `c6082df` (3.11 completo) | `fcaa275` |
|---|---|---|
| backend | 6 860 PASS / 34 FAIL / 3 xfail | **6 881 PASS / 34 FAIL / 3 xfail** |
| insieme dei FAIL | — | identico (0 nuovi, 0 risolti) |

Frontend non modificato (Jest 124/124 e build attestati su `973fe57`). Template systemd verificati con `systemd-analyze verify` (systemd 255) su un'istanza con segnaposto fittizi: nessun errore (solo l'avviso sull'utente di prova `nobody`).

**Limiti aperti**
1. **Runner di versione precedente**: non rispetta il lease; l'esclusione verso di lui **non è dimostrabile**. Il riconoscimento via heartbeat (45 min) è solo difesa in profondità. La migrazione deve prima aggiornare il runner legacy (fase A) e solo dopo passare all'exit-worker (fase B).
2. Finestra di passaggio: tra rilascio del runner legacy e acquisizione dell'exit-worker al massimo un intervallo di attesa (0,25 s); il primo tick sano (monitor) avviene subito dopo.
3. Due runner `sidecar` sulla stessa run non sono esclusi da questo lease (non possiedono chiusure; le aperture restano serializzate da `open_serial`), ma scriverebbero lo stesso `heartbeat.json`.
4. Unità systemd e procedura: **non installate né provate su un sistema reale**; segnaposto da verificare; servono mandato, backup off-host e preflight VPS read-only.
5. Restano aperti gli altri gate dell'audit (34 FAIL preesistenti, CI 3.11, browser/Android, staging, release candidate pinned).

---

# Bonifica della suite backend (Python 3.11) e preparazione CI (09/11/2026, base `8e3dbb9c65b41dc37395081b8771e315d3f4365c`)

**Commit codice+test: `480cd53002d363432cac9790349e575bcd04d39a`.** D1 e D2 invariati. Nessuna modifica a strategie, AI, motore, leve, size, risk manager, PnL o storici.

## Interventi (uno per uno)
| # | File | Intervento | Natura |
|---|---|---|---|
| 1 | `tests/test_brain_f3_boundaries.py` | `PolicyFixture` con `max_loss_margin_fraction=None`, `min_leverage=1`, `max_leverage=125` = default di `RiskPolicy`: l'hash storico di `_policy_hash` non cambia, nessun limite di rischio cambia. Controllo "denti": disattivando la verifica della firma in una copia, 4 test falliscono (poi ripristinato). | solo test |
| 2 | `tests/test_auth_flow.py`, `test_profiles_engine.py` | `os.chdir(_TMP)` resta solo per gli import, poi ripristino; fixture autouse di modulo che entra in `_TMP` durante i test del modulo e ripristina in uscita. I test RC80 dei lock (sottoprocesso con `PYTHONPATH` relativo) passano in qualunque ordine (verificato anche con auth/profiles prima). | solo test |
| 3 | `live_view.py` | `can_close_position(hb, now)`: propaga l'orologio già passato a `build_portfolio`. Con `now=None` (produzione) comportamento identico. | applicativo, minimo |
| 4 | `desk_view.py` | `command_close_position`: bot con heartbeat fresco ma senza chiusura singola → 409 con `CLOSE_OLD_BOT_MESSAGE` (prima: «non risponde», il messaggio era irraggiungibile). Sempre 409, nessun flag scritto; heartbeat scaduto/assente/futuro → ancora «non risponde»; validazione simbolo e `exit_only` invariati. `test_desk_view.py`: nuovo test dei messaggi e delle non-scritture; nel test esistente aggiornate le asserzioni sul secondo clic al contratto RC73 (`f089030`: richiesta già in attesa ⇒ 409 «gia' in corso», niente sovrascrittura). | applicativo minimo + test |
| 5 | `tests/test_long_s25.py` | Pin di `brain.py` aggiornato a `4f040c14…`. Verificato prima: l'unica differenza da RC81 è `_append_json_line` (RC82 `dfc7059`, scrittura append robusta a righe troncate, coperta da test RC82); `engine.py` (formule economiche) invariato e ancora pinnato. | solo test |
| 6 | `tests/test_superbot.py` | `pytestmark`: marker `integration` + `skipif` senza `REACT_APP_BACKEND_URL`. I 9 test risultano **SKIPPED**, non PASS; non eseguiti (nessun server). | solo test |
| 7 | `v3_api.py` | Snapshot divergenti: heartbeat fresco con `paper_close_claims.pending > 0` ma stato senza claim ⇒ `close_reconciliation.state = unknown` (mai `ok`); heartbeat scaduto o non valido ignorato. +3 test. | applicativo, minimo (D1) |

## Risultati (Python 3.11.x, dipendenze di `requirements.txt`, rete rifiutata, nessun segreto)
| | prima (`8e3dbb9`) | dopo (`480cd53`) |
|---|---|---|
| backend, cartella intera | 6 881 PASS / 34 FAIL / 3 xfail | **6 910 PASS / 0 FAIL / 9 skipped / 3 xfail** |
| auth/profiles | 42 PASS | incluse (passano) |
| lock RC80 + processi concorrenti Brain (136 test, anche con auth/profiles prima) | — | PASS |
| Jest | 124/124 | 124/124 (14 suite) |
| build `CI=true` | Compiled successfully | Compiled successfully |

**Non eseguiti / non attestati**: i 9 `test_superbot.py` (richiedono un server vivo: eseguirli solo contro un ambiente di prova autorizzato, con `REACT_APP_BACKEND_URL`); 3 xfail preesistenti. Su Python 3.13 `sqlalchemy==2.0.28` non si importa: la suite va eseguita su 3.11 (o 3.12).

## GitHub Actions — verifica in sola lettura
- 89 workflow. **Nessuno scatta in automatico** su un push a `cursor/rc84-…` (tutti i `push` sono vincolati ad altri rami) né sugli eventi della PR #80 (base `cursor/rc82-…`; i soli `pull_request` esistenti hanno base `main` / `work/v3-brain-f2-grok`). `list_workflow_runs` sul ramo: 0 run.
- **Operativi (ssh/scp/docker/systemctl, segreti `SSH_PRIVATE_KEY`/`SINGAPORE_SSH_PRIVATE_KEY`/Bitget/Anthropic)**: tra gli altri `deploy.yml`, `desk-*`, `pool-*`, `superbot-restart.yml`, `staging-deploy.yml`, tutti i `v3-rc69…rc77`, `v3-stop-paper-workers.yml` e `v3-vps-inventory.yml`. **Non avviarne alcuno.** Attenzione: gli ultimi due hanno `push` su `main`: una futura fusione in `main` li farebbe scattare (decisione da valutare prima di qualsiasi merge).
- **Solo test, senza segreti** (`permissions: contents: read`, nessun ssh): `v3-rc74-full-v3-regression.yml` (`backend/tests/test_v3_*.py`, Python 3.11), `v3-peer-full-v3-regression-ci.yml` (+ Jest/build), `v3-rc73-final-guard-ci.yml`, ecc. Limiti: sono vincolati ad altri rami e coprono solo `test_v3_*.py` (non desk, F3, auth/profiles); `workflow_dispatch` richiede che il file esista sul ramo predefinito (`main` non li ha).

**Procedura proposta per la CI sullo SHA finale** (da approvare; non eseguita):
1. Fissare lo SHA finale (senza `[skip ci]` nell'ultimo commit, oppure `workflow_dispatch`).
2. Aggiungere, in un commit separato e revisionato, un workflow dedicato **solo test** `rc84-tests.yml`: `permissions: contents: read`; trigger `workflow_dispatch` e `push` limitato a `branches: [cursor/rc84-running-stop-health-telegram-20261108]` con `paths: ['.github/workflows/rc84-tests.yml']`; job backend `ubuntu-24.04`, `python-version: '3.11'`, `pip install -r backend/requirements.txt`, `PYTHONPATH=.:backend DESK_MODE=paper DESK_MACRO_FETCH=0`, `python -m pytest -q -p no:cacheprovider backend/tests/`; job frontend Node 20, `npm ci` (o `yarn --frozen-lockfile`), `CI=true react-scripts test --watchAll=false --runInBand`, `CI=true react-scripts build`. Nessun `secrets.*`, nessun ssh/docker/deploy.
3. Per il solo avvio manuale servirebbe che il file sia sul ramo predefinito: valutare di far scattare il `push` del file stesso sul ramo, che è l'unico evento già filtrato per questo ramo.
4. Controllare prima, con `list_workflows`, che nessun altro workflow dichiari lo stesso ramo.
Non ho creato né avviato alcun workflow.

## Limiti
- I test sono stati allineati solo dopo aver verificato la causa; il test dei messaggi `desk_view` e le 3 asserzioni F3 verificano ancora fail-closed (mutazione intercettata).
- Nessun test è stato "reso verde" con skip tranne i 9 di integrazione, dichiarati.
- Restano aperti i gate dell'audit: CI reale su SHA pinned, browser autenticato/Android, staging (password di bootstrap nel workflow), backup off-host, preflight VPS, release candidate unica (#76 e 2 commit di `main`), systemd Brain non provato su sistema reale.

---

# Preparazione CI offline sicura (09/11/2026, base `10ac0cce626716ee97983319f23cfb538b377ce1`, revisione ChatGPT #6746349575)

**Commit codice+test+documento: `bee85fda7b2c513fec19af86ae211213fade924d`.** Nessun workflow creato, avviato o modificato (`.github/` non toccata). Nessun codice applicativo modificato: solo test e un documento.

- **Rischio confermato**: con `REACT_APP_BACKEND_URL` impostata `test_superbot.py` eseguiva davvero 9 richieste, tra cui `POST /api/bot/start`, con una password fissa nel repository.
- **Correzione fail-closed**: `backend/tests/conftest.py` (marker `integration`; test saltati salvo `SUPERBOT_ALLOW_INTEGRATION=1` e host `127.0.0.1`/`localhost`/`::1`), seconda barriera nel wrapper di `test_superbot.py`, password statica rimossa (`SUPERBOT_TEST_PASSWORD`).
- **Prova di sicurezza** `test_ci_integration_guard.py` (17): finto server locale che conta le richieste; URL fittizi (anche non locali) senza opt-in ⇒ **0 richieste, 0 POST, 9 skipped**; `-m "not integration"` ⇒ 9 deselected; controllo positivo che il contatore vede `GET /api/health` e `POST /api/bot/start`. Mutazione (barriere neutralizzate) ⇒ 4 fallimenti; ripristinato.
- **Proposta di pipeline**: `docs/v3/RC84-CI-OFFLINE-PROPOSAL-20261109.md` (YAML in blocco Markdown, inerte). `test_v3_rc84_ci_proposal.py` (8, senza PyYAML, non saltabile) controlla: permessi `contents: read`, nessun segreto/ssh/docker/systemctl/deploy/curl/Bitget/altri workflow, solo azioni `actions/*`, trigger esatti (push filtrato sul solo file e sul solo ramo RC84 + `workflow_dispatch`), URL vuota, `-m "not integration"`, 3 `unshare -n`, Python 3.11, Node 22. `actionlint` 1.7.12: nessun avviso.
- **Evento che lo attiverebbe**: solo un push sul ramo `cursor/rc84-running-stop-health-telegram-20261108` che modifichi `.github/workflows/rc84-offline-verify.yml` (il commit che lo aggiunge ⇒ 1 run; commit senza `[skip ci]`); `workflow_dispatch` non utilizzabile finché il file non è sul ramo predefinito.

Risultati locali (Python 3.11, stessi comandi del YAML, namespace di rete vuoto; connessione esterna e DNS di `api.bitget.com` provati bloccati): backend **6 935 passed, 0 failed, 3 xfailed, 9 deselected**; Jest 124/124 (14 suite); build `CI=true` compilata. **Non è una CI**: il workflow non è mai girato su GitHub.

Limiti: azioni non pinnate a SHA (tag `@v4`/`@v5`, da pinnare all'approvazione); `sudo`/`iproute2`/`unshare` sul runner non provati su un runner reale; restano `v3-stop-paper-workers.yml` e `v3-vps-inventory.yml` con push su `main`; gli altri gate dell'audit restano aperti.

---

# Rifinitura sicurezza CI (09/11/2026, base `74fbde2ae0327503241e1e7e1ca15513b818de28`, revisione ChatGPT #6747209165)

**Commit test+documento: `56877eecee148e7c35c5cc3fcf526bec2cd46770`.** Solo test e documento in `docs/v3/`. Nessun workflow creato o avviato; `.github/` non toccata; trading, AI, D1, D2, rischio, capitali e dashboard invariati.

1. **Wrapper HTTP d'integrazione** (`test_superbot.py`): verifica l'URL effettivo (schema/host/porta = `REACT_APP_BACKEND_URL`), nessun redirect seguito (un 3xx è un errore), nessun proxy ereditato (`trust_env=False`, `proxies` del chiamante ignorati), timeout (10 s, massimo 30). Prova in-process con un finto server che risponde `302` verso `sentinel.invalid`, `https://example.org`, un'altra porta locale e un URL relativo allo schema: una spia su `HTTPAdapter.send` registra ogni richiesta e non apre connessioni fuori dal server finto ⇒ solo la richiesta al server finto, **nessuna richiesta esterna**; un controllo con sessione `requests` normale mostra che il redirect verso la sentinella partirebbe. Con il wrapper precedente 14 di questi test falliscono. `test_ci_integration_guard.py`: 32 test.
2. **Preflight fail-fast** (proposta YAML, in entrambi i job, prima di installare e testare): `unshare`/`ip`/`sudo -n` presenti, diagnostica (kernel, release, `ip -V`, `unshare --version`, sysctl AppArmor), sonda dentro `sudo -n unshare -n` (solo `lo`, nessuna rotta, loopback usabile, `ENETUNREACH` verso `192.0.2.1`, nome `.invalid` non risolvibile). Qualunque anomalia ⇒ `exit 1`. Nessun `||` di ripiego, nessun `continue-on-error`. Sonda provata qui in tre casi: dentro il namespace OK; fuori ⇒ errore; namespace senza loopback ⇒ errore.
3. **`PYTHONPATH` esplicito e assoluto** (`<workspace>:<workspace>/backend`, equivalente a `.:backend` ma immune ai test che cambiano cwd; un `PYTHONPATH` relativo da un'altra cwd fallisce, documentato da un test), inoltrato a `sudo env`, più passo che verifica gli import da una cartella estranea. `test_v3_rc84_import_paths.py` (7): import da cwd estranea, ordini avanti/inverso/ruotato/mescolato, auth/profiles prima e dopo i test di lock.
4. **Pin a SHA** (verificati con `git ls-remote` in sola lettura sui repository ufficiali, poi `git fetch --depth 1`: oggetto `commit`; il tag maggiore coincide con il patch più alto): `actions/checkout` v4.4.0 `11d5960a…7262`, `actions/setup-python` v5.6.0 `a26af69b…065`, `actions/setup-node` v4.4.0 `49933ea5…020`, `actions/upload-artifact` v4.6.2 `ea165f8d…fa02` (SHA completi nel documento). Stessa serie maggiore dei workflow esistenti; nessuna azione nuova.

**Proposta**: `docs/v3/RC84-CI-OFFLINE-PROPOSAL-20261109.md`; `actionlint` 1.7.12 senza avvisi; `test_v3_rc84_ci_proposal.py` (11) controlla trigger, permessi, assenza di segreti/operazioni, pin, preflight prima dei test, assenza di ripieghi, `PYTHONPATH`; 4 mutazioni intercettate (ripiego `||`, tag al posto dello SHA, preflight rimosso, `PYTHONPATH` relativo).

| eseguito qui (Python 3.11, dipendenze di `requirements.txt`, namespace di rete vuoto) | esito |
|---|---|
| backend offline, ordine alfabetico | **6 960 passed, 0 failed, 3 xfailed, 9 deselected** |
| backend offline, file in ordine inverso | **6 960 passed, 0 failed, 3 xfailed, 9 deselected** |
| Jest (Node 22) | 124/124, 14 suite |
| build `CI=true` | Compiled successfully |

**Richiede un runner GitHub reale (NON verificato)**: `sudo -n`, `ip link set lo up` e `unshare -n` su `ubuntu-24.04` ospitato; eventuali restrizioni AppArmor/namespace; `setup-python`/`setup-node`/cache; upload degli artefatti; comportamento di `concurrency`. Il preflight è pensato per fallire subito con una diagnostica, mai per ripiegare. Il workflow non è mai girato su GitHub.
