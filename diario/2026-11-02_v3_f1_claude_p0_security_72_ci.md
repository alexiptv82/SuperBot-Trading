# SuperBot V3 — checkpoint 2026-11-02 dopo revisione Claude F1

## Mandato
Utente: "adesso puoi continuare". Ripresi soltanto i lavori di sicurezza/test nella PR #29 DRAFT. Nessun merge, nessun deploy, nessun reset, nessun import dati reali e nessuna sessione SSH/VPS eseguita.

## Modifiche effettive al ramo
- Eliminati `.github/workflows/v3-legacy-snapshot-readonly.yml` e `deploy/v3-legacy-audit.trigger` per impedire l'avvio del workflow del branch capace di eseguire codice arbitrario come root via SSH.
- Aggiunto `open_frozen_sqlite` comune, che BLOCCA l'audit Brain se trova `-wal` o `-journal` non vuoti. Non risolve il caso di una copia grezza dalla quale il WAL era stato omesso: serve nuovo snapshot con API SQLite e confronto COUNT/MAX(seq).
- Disabilitato `plan_classic_closed_events` (ID incompatibili) e mantenuto solo pianificatore multirun con identificatori derivati dal contenuto del trade.
- `legacy_multirun` blocca finali duplicate per run/ID, partial senza finale su run precedenti, learning di portafoglio sbagliato e run future.
- Nuovo `legacy_archives.py` controlla summary, stato, trade, cassa e P&L di ogni run archiviata; archivi mancanti/divergenti bloccano. `offline_import.py` adesso richiede il gate e include gli archivi tra i file sorgente hashati.
- `risk.py`: budget floor = equity − 450 − rischio già aperto.
- `events.py`: verify_chain() accetta attesi conteggio/head da manifest esterno e rileva troncamento di coda rispetto a quelli.
- `legacy_brain_books.py`: rilevamento ts fuori ordine e secondo `experiment_started`.
- Test avversari aggiunti per P0-1/2/3 e P1; suite **72 PASS Python 3.10 + 72 PASS Python 3.11**: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41508485519.
- Stato tecnico dettagliato sul ramo V3: https://github.com/alexiptv82/SuperBot-Trading/blob/work/v3-foundations-event-risk-20261102/docs/v3/claude-f1-remediation-status-20261102.md

## Stato del rilascio
**NO-GO per importazione reale.** Non è stata attestata una copia cifrata esterna post-stop, né backup Brain WAL-consistente tramite API SQLite, né archivio completo run legacy con gate nuovo eseguito sui file reali. Non è stata ruotata/limitata la chiave SSH già nei secrets; il workflow pericoloso è stato rimosso solo dal ramo. Non sono state verificate tutte le altre pipeline di automazione. La PR #29 resta DRAFT.

## Prossimo ordine operativo
1. Audit/F0 backup post-stop: inventario dei file e sidecar, cattura SQLite via backup API da conto senza permessi extra, SHA manifest, copia cifrata fuori VPS e ripristino indipendente.
2. Rieseguire gli audit *nuovi* su copia recuperata, confermare archive summary di tutte le run, traccia code_version, esperimenti Brain e saldo.
3. Completare P1: schema V3 versionato, hash testata ancorato fuori host, legame experiment_id/build_sha tra epoche, modello di esecuzione per evitare doppio conteggio.
4. Ulteriore revisione di Cloud/Grok, poi richiesta OK per importazione effettiva e per rilascio. `NO_TRADE` e isolamento dei tre wallet PAPER restano vincolanti.
