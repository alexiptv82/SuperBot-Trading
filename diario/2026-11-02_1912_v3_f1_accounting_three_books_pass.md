# Checkpoint SuperBot V3 F1 — 2026-11-02 19:12 Europe/Rome

## Mandato e stato operativo
Utente autorizza «Okay, procediamo, ricordati se hai bisogno c'è sempre disponibile Cloud e Grok.» Si prosegue nel ramo `work/v3-foundations-event-risk-20261102`, PR #29 DRAFT, senza merge, deploy, cambio portafoglio, riavvio dei bot o modifica degli storici. Cloud (Claude) e Grok disponibili come revisori indipendenti su richiesta; nessuna consultazione esterna avviata in questo checkpoint.

## Sviluppo completato sul ramo isolato
- `backend/v3/legacy_accounting.py`: audit CASH di Falco/Toro sulla run corrente con equity contabile **escluso** unrealized; formula `cash+open_margin = 1000 + Σclosed.net - entry_fees_residue`, tolleranza 0,01 USDT. Fallimento esplicito se fee mancanti, ID dup, dati invalidi.
- `backend/v3/legacy_brain_books.py`: Brain Free SQLite PAPER frozen, abbina `open` a `trade_closed` e `partial_trade` alla sua chiusura finale, non duplica i net delle parziali già contenute nei finali. ID distinti per epoca V1/V2, epoche separate da `experiment_reframed`. Migrazione deve conservare cash identico prima/dopo e quello dello snapshot precedente.
- Test `backend/tests/test_v3_legacy_accounting.py` e `backend/tests/test_v3_legacy_brain_books.py` aggiunti; per reframe con ID ripetuti e top-up falso test di regressione.
- Workflow GitHub Action usa payload Python temporaneo inviato a `python3 -` su VPS Singapore con SSH pinned; legge SOLO copia del backup estratta in `/opt/superbot-v3-backups/20261102T144010Z/restore-test`; nessun file su VPS modificato.

## Evidenze verificate
- CI SUCCESS **49 PASS Python 3.10 + 49 PASS Python 3.11**: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41497835752
- Audit finale backup in sola lettura SUCCESS: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41497955027
- Falco storico: **348/348** chiusure riconciliate sulle run 2–8, run corrente 8 (59 chiusure e 6 posizioni aperte), `BOOK_CASH_PASS=True`, zero issue.
- Toro storico: **186/186** chiusure riconciliate sulle run 1–7, run corrente 7 (23 chiusure e 2 posizioni aperte), `BOOK_CASH_PASS=True`, zero issue.
- Brain Free: `8447` eventi totali, `182` aperture, `182` `trade_closed`, `55` `partial_trade`, `0` posizioni aperte. Dopo la separazione per epoca V1/V2 `BRAIN_BOOKS ELIGIBLE=True, CASH_PASS=True, SEGMENT_PASS=True, ENTRY_EXIT_PAIRING=True, ISSUES=NONE`. I 3 ID apparenti ripetuti sono reuse in due epoche; non trade duplicati.
- Gli storici PAPER sono stati soltanto LETTI e gli eventi chiusi dei classici generati in RAM; **nessuna importazione persistente L0 ancora effettuata**.

## Limitazioni e prossimi gate
- Cash/book audit non certifica mark-to-market né PnL non realizzato delle 8 posizioni PAPER aperte nei classici; non verifica slippage, commissioni o funding contro valori reali exchange.
- Backup generale post-stop locale certificato, **copia esterna cifrata POST-stop non attestata**: blocca vera migrazione/import senza ulteriore verifica.
- Successivo: schema versionato L0, import offline idempotente in DB V3 separato su ambiente di prova, riconciliazione import vs source, hash chain e prova di restore, senza modificare i DB originali. Preparare un pacchetto di revisione indipendente per Claude/Grok dei passaggi contabili.
- V3 1000/1000/1000 non creata; servizi bot/AI e strategie non riattivati; PR #29 resta DRAFT e F1 non marcata COMPLETATA.
