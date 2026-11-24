# SuperBot V3 F1 — Stato dopo revisione indipendente Claude (2 novembre 2026)

## Modalità e stato operativo

**SOLTANTO RAMO DI SVILUPPO**. PR #29 DRAFT. Non eseguiti merge, deploy, reset, nuove operazioni PAPER/LIVE, avvio bot né interventi sui database storici/VPS in questo turno. La verifica della VPS post-intervento NON è stata ripetuta: non descriverla come attestata "ora".

## Revisione Claude: 4 P0 / 10 P1 / 7 P2

Riferimento: PDF fornito dall'utente "SuperBot V3 F1 — Revisione indipendente di Claude.pdf" e script di prova `v3_f1_probe_wal_immutable.py`, `v3_f1_probe_p0_p1.py`, `v3_f1_probe_cash_invariant.py`.

### Correzioni già applicate

1. **P0-4 controllo SSH root:** rimossi dal ramo `.github/workflows/v3-legacy-snapshot-readonly.yml` e `deploy/v3-legacy-audit.trigger`. Il job non può più partire da questo ramo e invocare `python3 -` come root sulla VPS. **Non è attestata la revoca/rotazione della chiave già presente nei secrets**, né verificato ogni altro workflow. Nessun nuovo accesso remoto è stato tentato.
2. **P0-1 WAL:** aggiunto `open_frozen_sqlite()` in `legacy_audit.py`, riusato da `legacy_accounting.py` e `legacy_brain_books.py`. Rifiuta copie con `-wal` o `-journal` non vuoti o collegamenti simbolici. **Questo NON certifica una copia priva di WAL già omesso**; servono manifest di cattura con COUNT/MAX(seq), backup tramite API SQLite e ripristino fuori-host.
3. **P0-2 eventi doppi:** disabilitato con `NotImplementedError` `plan_classic_closed_events`, lasciando un solo `plan_classic_multirun_events`. IDs basati su portafoglio, run, posizione, orario di uscita e hash canonico del record; non più sulla riga.
4. **P0-3 vecchie run:** verifiche contro due chiusure finali dello stesso ID/run, parziali senza finale nelle run passate, righe learning con portafoglio sbagliato. Nuovo `legacy_archives.py`: confronta le run storiche con `archive/*/{summary.json,state_v2.json,trade_history.jsonl}`, conteggi, cash e PnL con tolleranza esplicita; se mancanti o incoerenti, FAIL-CLOSED. `offline_import.py` ora richiede `audit_classic_archives(...).eligible` e include anche i file archiviati nel digest degli input. **Non è stato rieseguito questo gate sui backup reali**, perché l'accesso root è stato disabilitato.
5. **P1-9 protezione equity minima:** rischio aggiuntivo allo stop `<= equity - minimum_equity - existing_open_risk`.
6. **P1-2 integrità coda:** `verify_chain(expected_count, expected_head)` fallisce in caso di troncamento rispetto a un ancoraggio esterno; la catena da sola non può rilevare una cancellazione di coda.
7. **P1-4/P1-5 Brain:** l'audit respinge timestamp fuori ordine e più `experiment_started` non spiegati. Provenienza completa per `experiment_id` e `build_sha` ancora da verificare.

## Test/CI

Ultima CI su ramo di sviluppo:
https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41508485519
**72 PASS Python 3.10, 72 PASS Python 3.11**. Unit test su dati sintetici, non prova della completezza economica dei backup reali. I test nuovi coprono WAL non vuoto, planner duplicato, finali doppi, partial orfane, contaminazione portfolio, rischio floor, timestamp Brain, avvii ripetuti, taglio del journal, archivi mancanti e cash archive sbagliato.

## NO-GO rimane in vigore

- **Nessun import persistente con dati reali** prima di nuova cattura SQLite Brain che includa WAL, prova off-host del backup post-stop, manifest con COUNT/MAX(seq), archivi legacy completi e risultati di audit re-eseguiti in modalità segregata. Non riutilizzare il precedente workflow SSH-root.
- Gli otto trade PAPER ancora aperti dei classici sono fatti storici, non vanno chiusi inventando prezzi.
- Non sono state approvate soglie di trading V3, non sono stati creati i portafogli 1000/1000/1000 e nessun motore AI è stato riavviato.
- Prima di promuovere PR: versione schema `v3_meta`, ancoraggio hash esterno, attestazione run Brain `experiment_id/build_sha`, inventario delle altre sorgenti fuori F1, revisione da Claude/Grok del diff finale, test negati sul backup ripristinato, consenso esplicito dell'utente.

## Prossima azione quando sarà autorizzata la procedura F0

Progettare un workflow con accesso di sola lettura imposto da OS (utente dedicato/chiave ristretta, nessun codice del branch eseguibile come root), creare backup SQLite API con manifest ed estrarre su macchina diversa. Non cambiare la VPS direttamente tramite un job di test arbitrario.
