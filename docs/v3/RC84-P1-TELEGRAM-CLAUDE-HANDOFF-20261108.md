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
