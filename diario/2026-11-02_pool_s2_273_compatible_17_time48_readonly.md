# 2026-11-02 — Audit PAPER Pool S2: 273 compatibili, 17 uscite time al limite 48h

## Evidenza fornita dall'operatore (Termius, VPS Singapore)
Screenshot 11:31: audit eseguito in sola lettura con codice di replay corretto sui quattro gruppi S2. Output mostrato:
- TRADE_S2_CHIUSI: 273
- TRADE_COMPATIBILI: 273
- DIFFERENZE: 0
- AUDIT_S2_STORICO: PASS
- DATABASE_ORIGINALE: NON MODIFICATO

Screenshot 11:45: query sqlite3 read-only `file:/opt/superbot-pool-data/pool.db?mode=ro`, venue paper, status closed, rule_id LIKE '%S2%', conto esiti why='time' e abs(hold_h-48)<0.001:
| Regola | Chiusi | TIME_48H |
|---|---:|---:|
| CTL_S2_majors | 44 | 1 |
| CTL_S2_top10 | 120 | 10 |
| R_S2_majors | 18 | 1 |
| R_S2_top10 | 91 | 5 |
| TOTALE | 273 | 17 |

Interpretrazione: 17/273 trade S2 (~6.23%) sono terminati a 48 ore per limite di tempo; **non sono 17 errori**. L'audit d'insieme sui 273 S2 mostra 0 differenze. La query di conteggio da sola non è prova di replay generale; l'audit S2 è testimonianza dell'output terminale fornito dall'utente, non una lettura diretta del DB da questo assistente.

## Stato rilascio e vincoli
- Il candidato fix Donchian della PR #28, work/pool-donchian-maxhold-immutability-20261102, resta DRAFT, non mergiato e non distribuito.
- Precedente CI 41425516433 69/69 PASS; nessuna modifica al Journal immutabile.
- Il simulatore `strategy_lab.simulate_exit` è condiviso; inventario e, dove presenti, audit di eventuali trade PAPER non-S2 (es. S1) ancora da verificare prima del deploy.
- Prima di rilasciare: backup verificato/ripristinabile, controllo completo del journal, autorizzazione esplicita; aggiornamento Pool `healthy` solo dopo ciclo reale completato.
- Non toccati Falco/Toro, pause Brain e Shadow, dati, wallet, deploy, ordini, protezione 450 USDT.
AI: ChatGPT (nuova chat di continuità).
