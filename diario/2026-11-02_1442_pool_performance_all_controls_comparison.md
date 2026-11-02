# 2026-11-02 14:42 Europe/Rome — Pool: statistiche PAPER complete, nessuna regola batte controllo

## Evidenza screenshot Termius dell'operatore
Eseguita query SQLite `mode=ro` su `/opt/superbot-pool-data/pool.db` per le righe PAPER chiuse `CTL_S2_top10` e `R_S1_majors`, con risultato:
```
('CTL_S2_top10', 120, 39, -3.42, -409.88)
('R_S1_majors', 5, 0, -262.61, -1313.07)
```

## Confronti completati
I 291 chiusi comprendono 114 R (strategie testate) e 177 CTL (controlli).
| Regola | N | Win | Media net_bp | Controllo associato | N CTL | Media CTL net_bp | Differenza R−CTL |
|---|---:|---:|---:|---|---:|---:|---:|
| R_S1_majors | 5 | 0 | -262.61 | CTL_S1_majors | 13 | -69.67 | -192.94 |
| R_S2_majors | 18 | 3 | -87.05 | CTL_S2_majors | 44 | -29.19 | -57.86 |
| R_S2_top10 | 91 | 18 | -103.92 | CTL_S2_top10 | 120 | -3.42 | -100.50 |

Tutte le R hanno rendimento netto medio negativo e inferiore al controllo associato. Questi sono BP di operazioni simulate **non** profitti sul capitale, non PnL USDT, non prova statisticamente controllata della superiorità delle strategie e non una comparazione normalizzata con Falco/Toro/Brain. CTL usa ingresso spostato casualmente rispetto alle R e il conteggio dei trade non è eguale; evitare inferenze causali assolute sull'ingresso. Campione S1 molto piccolo. Non promuovere in Brain senza OOS e risk-adjusted evidence.

## Stato operativo
Backup Pool completo del 2026-11-02T12:59:29Z in `/opt/superbot-pool-backups/20261102T125929Z` testato con hash, estrazione identica e SQLite integrity ok. Il Pool era stato fermato con stop esplicito su autorizzazione dell'utente e non deve essere riavviato implicitamente. PR #28 resta da considerare per fix del Journal storico, ma non rende profittevoli queste strategie. Falco, Toro, Brain/Shadow invariati.

Solo audit/report, nessun merge/deploy/ordine.
AI: ChatGPT (continuità SuperBot).
