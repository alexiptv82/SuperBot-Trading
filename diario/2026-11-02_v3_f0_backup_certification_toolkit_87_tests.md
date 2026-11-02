# Checkpoint SuperBot V3 F0 — 2026-11-02 — toolkit backup certificabile, non ancora certificato

## Autorizzazione e perimetro

Utente «ok procedi» dopo correzioni Claude F1. Sviluppo proseguito esclusivamente sul branch `work/v3-foundations-event-risk-20261102`, PR #29 DRAFT. **Nessun SSH/VPS, merge, deploy, trade, reset o avvio bot e AI eseguito in questa sessione.** Non dichiarare gli attuali servizi VPS verificati nuovamente. Il precedente workflow SSH root è ancora rimosso sul ramo.

## Nuovo codice su GitHub

- `backend/v3/backup_certification.py`:
  - `observe_brain_source_readonly()`: impronta indipendente da fonte SQLite mode=ro (inclusi WAL confermati), COUNT, MAX(seq), digest del flusso eventi e hash stato PAPER Brain; nessuna scrittura applicativa.
  - `capture_brain_copy()`: usa SQLite Connection.backup() per copiare una fonte **ferma/isolata** in directory nuova, confronta osservazione prima/dopo e nella copia, fsync del DB, manifest JSON scritto per ultimo; ritorna digest del manifest ma NON si dichiara certificato esternamente.
  - `verify_brain_offhost()`: richiede valori aspettati della fonte e SHA manifest registrati **fuori** dalla copia; confronta integralmente file, stato, eventi, metadata e `PRAGMA integrity_check` sul restore. Mancanza valori o differenze → fail-closed.
  - Nota: se il testimone esterno non è autentico, neppure questa procedura può dimostrare provenienza reale; non si può dimostrare completezza da un DB copiato grezzo e privo del WAL originale.
- `backend/v3/f0_classic_certificate.py`:
  - witness read-only dell'intero insieme Falco/Toro stato, trade_history, learning_log e archive/*.
  - validatore offhost richiede digest esterno, quantità chiusure, run storiche e run corrente, oltre al PASS di riconciliazione del cash e degli archivi.
- `backend/tests/test_v3_backup_certification.py`: fixture con WAL attivo ma commit, backend cattura le nuove transazioni; negativo per copia storicamente vecchia ma autoconsistente, manipolazioni manifest/DB, witness mancante, copia incompleta, account non-PAPER.
- `backend/tests/test_v3_f0_classic_certificate.py`: positivo su restore separato, negativi su summary alterato, learning divergente pur economicamente coerente, archivi mancanti e witness errato.
- Runbook tecnico: https://github.com/alexiptv82/SuperBot-Trading/blob/work/v3-foundations-event-risk-20261102/docs/v3/f0-backup-certification-runbook.md
- README V3 e PR #29 aggiornati.

## CI verificata

GitHub Actions https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41510393826 : **SUCCESS, 87 PASS Python 3.10 e 87 PASS Python 3.11**. Le prove sono sintentiche, eseguite in GitHub Actions senza SSH e senza uso di backup privati.

## Gate residui / non dichiarare risolti

1. Il database Brain storico reale NON è ancora stato ricatturato via API SQLite con WAL incluso, e il witness indipendente sul server al momento dello stop NON è disponibile.
2. Non è provata una copia cifrata OFF-VPS e il restore su host diverso POST-stop; backup locale precedente non basta.
3. Le run archiviate reali di Falco/Toro devono superare il nuovo validatore; i 534 eventi pre-audit sono un risultato precedente e non l'approvazione del gate attuale.
4. La chiave SSH/root nei secrets non è stata ruotata/limitata e gli altri workflow non sono stati globalmente controllati; il vecchio workflow vulnerabile è stato tolto dal ramo, non dalla VPS.
5. Non confondere archivio storico con nuovo capitale V3. Nessun nuovo portafoglio 1000/1000/1000 è stato creato.
6. Non procedere con importazione persistente, merge, riavvio o deploy senza verifica F0 indipendente e nuovo consenso utente.
