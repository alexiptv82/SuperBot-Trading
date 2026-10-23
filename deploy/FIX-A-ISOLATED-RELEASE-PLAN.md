# Fix A — piano rilascio ISOLATO, non autorizzato all'esecuzione
Data 2026-10-23. Materiale di PREPARAZIONE: nessuna attivazione/merge/trigger.

## Artefatto unico
- BASE RUNTIME: `fa3e220f1fba86c3426fb0da69348035084167a4` / code_version `fa3e220` (misura 23/10 06:07 UTC).
- CANDIDATO: `f87f2d63c5849b177dbd33ee43c5be05ca58c8ed` / code_version prevista `f87f2d6`.
- RAMO CODICE: `work/fix-a-only-fa3e220-20261023` (figlio diretto di fa3e220, non è da unire a rule-pool).
- INVENTARIO esatto: backend/desk/{brain,cli,signals,position_card}.py e backend/tests/test_profit_correctness_isolated.py.
- engine.py, market_context.py, Dockerfile.desk e tutte le altre parti sono identici a fa3e220; daily_stop 12% invariato.
- Test autonomi su `work/fix-a-ci-validation-20261023`, esecuzione senza segreti e senza deploy.

## Differenze ESCLUSE, future decisioni indipendenti
- Cambio engine.py `daily_stop: 0.12 -> 0.10` presente su rule-pool non parte della fix A: da deliberare a parte.
- Differenze aggiuntive di cli.py fra fa3e220 e 8efc0a9 sono ESCLUSE (cache 1D, controlli dati/ciclo e altre modifiche oltre alle sole nuove chiamate 4H/scheda A).
- Aggiornamenti di market_context.py fra fa3e220 e 8efc0a9 sono ESCLUSI.
- Nessun cambio di strategia, prompt di ingresso salvo il calcolo nell'esempio Bull, B, DeepSeek o Step 6.

## Come rilasciare SOLO dopo nuovo OK dell'utente
1. Verificare di nuovo test CI e assenza deploy concorrenti; controllare codice/runtime/stati e PAPER.
2. Review del workflow dedicato `.github/workflows/desk-fix-a-isolated-deploy.yml` in questo ramo. NON usare `desk-deploy.trigger` ordinario: accetta solo SHA antenati di rule-pool e produrrebbe bundle con altre modifiche.
3. Solo dopo OK unire esclusivamente il workflow dedicato al ramo rule-pool, senza il trigger. Verificare che sia ancora inerte.
4. Poi, con lo stesso OK esplicito che autorizza il rilascio e solo quando i prerequisiti risultano PASS, creare/modificare `deploy/desk-fix-a-isolated.trigger` su rule-pool. Quel solo evento deve eseguire backup validato e singolo rollout dei due bot.
5. La procedura dedicata controlla SHA e parent fissati, lista di 5 file, file core identici alla baseline, modo PAPER, ambiente rischio, SHA256 sorgenti runtime, versione heartbeat fa3e220, spazio, backup cervello verificato; conserva rollback e controlla entrambe le code_version, singola istanza per bot.
6. Dopo il deploy confermare code_version effettiva **f87f2d6** su Hawk e Bull, heartbeat nuovo, PAPER, dati/storico integri e manifesto. In caso di gate fallito: NO deploy e nuova decisione, niente disabilitazione guardie.

**STATO: NON DEPLOYATO.** Il workflow rimane su ramo di preparazione senza trigger in rule-pool.