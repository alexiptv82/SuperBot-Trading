# AI Arena — motivazioni manuali nel bundle di memoria (17 novembre 2026)

## Problema concreto

La PR #102 scrive le motivazioni umane dopo una chiusura PAPER confermata in `human_close_annotations.jsonl` (una catena append-only per run); tuttavia `collect_arena_learning_evidence` sul ramo base marca **ogni** chiusura manuale come `AWAITING_USER_ANNOTATION` anche quando la motivazione esiste. Ciò perderebbe il nesso semantico nel futuro archivio Brain, pur conservando il registro sorgente.

## Modifica isolata, solo lettura, mai live

- `backend/v3/arena/annotation_evidence.py`: connette ogni annotazione **già verificata tramite `manual_close.read_annotations`** a uno specifico evento `paper_close` nel journal e a un outcome manuale attribuito all'AI corretta.
- Rifiuta annotazioni di altre AI/run, chiusure automatiche, eventi inesistenti, tempi impossibili, duplicati, ID invalidi e note fuori contratto. Fallisce chiuso, mai associazioni “probabili” basate su PnL.
- Il record contiene `user_reason`, `user_reason_status=VERIFIED_HUMAN_ANNOTATION` (o `HUMAN_ANNOTATED_UNSPECIFIED`), `user_annotation_sha256` e `user_note_present`.
- **Non copia le note libere** nell'archivio condiviso; restano nel registro sorgente. Il digest consente una revisione umana riservata. Nessun testo privato in GitHub.
- `learning_evidence.py` rilegge le annotazioni dopo la verifica del journal: se cambiano durante la lettura, rifiuta l'export. Estende i contatori con `verified_human_annotation_count` e il digest dell'ultima annotazione; schema esportazione `arena_learning_evidence_v2`.
- Le annotazioni mancanti restano esplicitamente `AWAITING_USER_ANNOTATION`; nessuna esperienza diventa una regola di trading da sola (`eligible_for_automatic_promotion=False`).
- Nessuna API, bot, servizio o dashboard è avviata/aggiornata da questa patch.

## Gate prima del merge nel ramo di laboratorio

Eseguire *localmente*, senza GitHub Actions, almeno:

```bash
python -m pytest -q backend/v3/arena/test_annotation_evidence.py backend/v3/arena/test_learning_evidence.py
python -m pytest -q backend/v3/arena/test_arena_manual_close.py
```

Quindi un test d'integrazione con registri JSONL reali, un journal della run simulata e hash-chain integre: scrivere una nota tramite endpoint, verificare l'outcome, esportare, controllare corrispondenza `position_id`/`close_event_id`/`run_id`, alterare una riga e verificare il rifiuto. Testare anche back-up/restore con il file separato di annotazioni, **non solo `journal.db`**.

**Stato di questi test:** aggiunti nel ramo, non eseguiti su questa sessione né sulla VPS. Cloud può eseguirli nel suo ambiente e riferire output reale. Nessun deploy, merge operativo, spesa AI o trade.
