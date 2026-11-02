# 2026-11-02 13:32 Europe/Rome — Audit completo 291 PAPER chiusi invariati; 1 S2 ADA OPEN

## Evidenza Termius fornita dall'operatore
Screenshot delle 13:32 Europe/Rome: audit S1 read-only da container `superbot-pool` (lettura SQLite `/app/data/pool/pool.db?mode=ro`, candele cache, confronto con `rule_pool.replay` e `journal._FIELDS/_same`):
```
TRADE_S1_CHIUSI: 18
DIFFERENZE_S1: 0
POSIZIONI_POOL_APERTE: 1
OPEN: R_S2_top10 ADA/USDT:USDT SIDE: -1 ENTRY_UTC: 2026-11-02T07:00:00+00:00
AUDIT_S1: PASS
DATABASE_ORIGINALE: NON MODIFICATO
```
Precedente audit S2 (screenshot 11:31): `TRADE_S2_CHIUSI: 273`, `TRADE_COMPATIBILI: 273`, `DIFFERENZE: 0`, `AUDIT_S2_STORICO: PASS`. Inventario globale (screenshot 12:00): `291 closed` e `1 open`, sei gruppi PAPER.
Combinando i due audit: **291 / 291 trade closed PAPER esaminati compatibili, 0 differenze**; l'unico OPEN non fa parte dell'audit dei closed. I risultati sono output osservati su screenshot, non accesso diretto dell'assistente alla VPS. Non affermare identità snapshot se il DB è cambiato tra i controlli; rivalutare l'ultima fotografia prima del deploy.

## Anomalia che richiede diagnosi
Un record PAPER `open`, `R_S2_top10`, `ADA/USDT:USDT`, short (`side=-1`), `entry_t=2026-11-02 07:00 UTC` (08:00 Europe/Rome) appare nel DB, benché gli screenshot precedenti indicassero il servizio Pool `unhealthy` con `last_ok_ms` molto datato. Verificare sola lettura ultimo ciclo, meta last_ok_ms/forward_from_ms, timestamp file, log recenti e identità writer prima di interpretare il record. Non aggiornare o chiudere questa posizione artificialmente; nessuna prova di ordine exchange o stop locale attivo. Il Pool è un motore paper di ricerca.

## Stato del fix e sicurezza
PR #28 consultata su GitHub il 2026-11-02: OPEN, DRAFT, NON MERGED, SHA `38f370fcb83e4ed82058e27b6e58d32af1df18b4`; CI 41425516433 già documentata 69/69 PASS, non deployata.
Resta richiesto backup consistente con prova restore, preflight ultimo snapshot, controllo integrità/versionamento codice del simulatore condiviso e autorizzazione esplicita per merge/deploy; stato `healthy` solo dopo vero ciclo completato.
Falco e Toro intatti, Brain e AI Shadow in pausa, niente ordini, ripartenze, reset, deploy o modifiche al DB.
AI: ChatGPT (chat di continuità SuperBot).
