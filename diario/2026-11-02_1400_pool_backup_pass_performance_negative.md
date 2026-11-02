# 2026-11-02 14:00 Europe/Rome — Pool fermato, backup e ripristino PASS; risultati performance PAPER

## Evidenza operatore da screenshot Termius 13:59–14:00

Il titolare ha incollato il comando autorizzato di stop+backup del solo Pool e il comando di analisi `net_bp` in sola lettura.

### Backup
Output:
```
POOL_FERMATO: OK
pool-data.tar.gz: OK
FILE_IDENTICI: PASS
SQLITE_INTEGRITY: ok
TRADE_BACKUP: [('closed', 291), ('open', 1)]
BACKUP_DIR: /opt/superbot-pool-backups/20261102T125929Z
BACKUP_VERIFICATO: PASS
POOL_RIMANE_FERMO: SI
FALCO_TORO_BRAIN: NON MODIFICATI
```
L'archivio conserva `/opt/superbot-pool-data` con SQLite e file candele. Hash SHA256, prova estrazione e confronto file, PRAGMA integrity_check della copia superati. Non è ancora attestata una seconda copia esterna alla VPS né una recovery dell'intero servizio Docker. Pool rimane fermo per volontà dell'utente; non riavviare/deployare implicitamente.

### Statistiche economiche dei PAPER chiusi
Il database contiene 291 trade PAPER chiusi: 114 regole `R_*` sperimentali e 177 controlli `CTL_*`. Si tratta di rendimenti in basis point `net_bp` dalla simulazione (non ROE di un wallet con leve, né PnL in USDT). Dai tre screenshot:
| Regola | N | Wins | Win rate | avg_net_bp | sum_net_bp | worst | best |
|---|---:|---:|---:|---:|---:|---:|---:|
| CTL_S1_majors | 13 | 4 | 30.8% | -69.67 | -905.75 | -326.60 | 254.12 |
| CTL_S2_majors | 44 | 13 | 29.5% | -29.19 | -1284.19 | -214.92 | 571.18 |
| CTL_S2_top10 | 120 | 39 | 32.5% calcolato | NON VISIBILE | NON VISIBILE | NON VISIBILE | NON VISIBILE |
| R_S1_majors | 5 | 0 inferito da best <0 | 0% inferito | ~-262.61 derivato da somma/5 | -1313.07 (dal frammento iniziale del secondo screenshot) | -389.22 | -145.09 |
| R_S2_majors | 18 | 3 | 16.7% | -87.05 | -1566.97 | -205.34 | 210.05 |
| R_S2_top10 | 91 | 18 | 19.8% | -103.92 | -9457.15 | -361.0 | 334.19 |

Attribuzione a R_S1 di `SUM=-1313.07`, worst `-389.22`, best `-145.09`: plausibile per posizione in stampa ordinata, ma intestazione non visibile; chiedere verifica solo se necessario.

Tutte le strategie R leggibili risultano negative al netto dei costi modellati. Le strategie non risultano empiricamente promuovibili ora; confronto rigoroso con classici Brain richiede capitale, leve, rischio, periodo e metriche omogenee. Somma BP NON è ROI del portafoglio. CTL_S2_top10 media e somma BP mancano dagli screenshot e richiedono output compatto mirato prima della classifica finale.

### Sicurezza / prossimo
PR #28 di correzione Donchian resta DRAFT non merge/non deploy; test CI 69/69 PASS. Non riavviare il Pool con codice vecchio. Conservare storico e backup; predisporre eventualmente una copia esterna cifrata. Falco, Toro e pause AI non modificati.
AI: ChatGPT (nuova chat).
