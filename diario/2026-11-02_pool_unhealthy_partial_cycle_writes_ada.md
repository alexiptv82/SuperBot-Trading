# 2026-11-02 13:41 Europe/Rome — Pool unhealthy ma Journal continua a ricevere trade PAPER

## Nuova evidenza dell'operatore (Termius, sola lettura)
```
POOL=running HEALTH=unhealthy
last_ok_ms 2026-10-22T02:45:20+00:00
forward_from_ms 2026-10-09T13:45:00+00:00
OPEN_COUNT: 1
OPEN: ADA/USDT:USDT -1 2026-11-02T07:00:00+00:00
CONTROLLO_SOLO_LETTURA_COMPLETATO
```
Il database contiene dunque uno SHORT PAPER simulato aperto il 2 novembre ore 07:00 UTC (08:00 Europe/Rome) nonostante l'ultimo ciclo COMPLETO attestato risalga al 22 ottobre ore 02:45:20 UTC (04:45:20 Europe/Rome).

## Causa tecnica confermata da codice GitHub (`rule-pool`)
`backend/rule_pool/runner.py:run_once` richiama `replay.sync_journal` **regola per regola, simbolo per simbolo**. `rule_pool/journal.py:Journal.upsert_trade` esegue `commit()` per ogni nuovo trade/aggiornamento, senza transazione globale di ciclo. `backend/rule_pool/cli.py:iteration` aggiorna `last_ok_ms` **solo dopo** che `runner.run_once` termina. Se il bug XRP `ImmutableTradeError` scatta su una regola successiva, righe inserite prima dell'errore restano scritte mentre lo stato non diventa sano. Ordine `initial_rules`: R_S1, R_S2_majors, R_S2_top10, poi controlli; perciò ADA R_S2_top10 può essere scritta prima dell'errore CTL_S2_top10. Questa è una spiegazione coerente e suffragata dal codice, non prova del singolo stack runtime senza nuovi log.

## Stato audit
Screenshot precedenti: 273/273 PAPER S2 chiusi compatibili, 18/18 S1 chiusi compatibili; 291/291 chiusi confrontati con 0 differenze, su controlli distinti. Un OPEN ADA escluso dall'audit dei closed. `last_ok_ms` NON indica assenza di scritture successive.

## Sicurezza e prossima azione
- Non disabilitare immutabilità, non toccare/rimuovere/modificare il PAPER open, non riscrivere Journal né fingere healthy.
- PR #28 ancora DRAFT e NON DISTRIBUITA; 69 test CI PASS non prova il runtime.
- Diagnosticare log recenti in sola lettura; poi backup consistente di DB **e** candele, con hash/verifica restore, da effettuare evitando scritture del solo Pool (richiedere OK esplicito prima di qualunque stop/pausa o deploy).
- Falco/Toro e le pause Brain Free/Pilot/Shadow non modificati.
AI: ChatGPT, continuità SuperBot.
