# 2026-11-02 12:00 Europe/Rome — Inventario completo Pool PAPER (sola lettura)

Fonte: screenshot Termius dell'operatore; query SQLite al file `/opt/superbot-pool-data/pool.db` in modalità `mode=ro`, raggruppata per regola/versione/stato.

| Rule id | Versione | Status | Conteggio |
|---|---:|---|---:|
| CTL_S1_majors | 1 | closed | 13 |
| CTL_S2_majors | 1 | closed | 44 |
| CTL_S2_top10 | 1 | closed | 120 |
| R_S1_majors | 1 | closed | 5 |
| R_S2_majors | 1 | closed | 18 |
| R_S2_top10 | 1 | closed | 91 |
| R_S2_top10 | 1 | open | 1 |

Totale **291 closed** (= 273 S2 già auditati 273/273 comparabili zero differenze + 18 S1 da verificare), **1 open** sul portafoglio simulato del Pool. `INVENTARIO_POOL_COMPLETATO` mostrato in Termius. Questo NON certifica che l'open abbia una protezione attiva, dato che il Pool è unhealthy; posizione di journal PAPER, non un ordine reale accertato.

Passo successivo: audit in sola lettura dei 18 S1 con replay del codice installato e dettagli del singolo S2 open, senza `sync_journal` (che scriverebbe). Se zero differenze, predisporre preflight/backup con restore attestabile prima di merge/deploy del fix #28.

PR #28 resta DRAFT, non merged/deployed. Classici Falco/Toro e pause Brain/Shadow intatti. Nessuna autorizzazione operativa ampliata.
AI: ChatGPT.
