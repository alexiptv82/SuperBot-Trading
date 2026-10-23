# Capital Management V1 — WIP / non distribuibile
23 ottobre 2026, autore ChatGPT chat normale. **NON MERGIARE, NON DEPLOYARE.**

## Autorizzazione ed esclusioni
Utente ha approvato l'implementazione in branch separati, A/B/C e parametri 20%, Hawk10%, Bull25%, 00:00 UTC, vault virtuale, pending, $450, slot10/6, PAPER. Nessuna autorizzazione a deployment, trigger o modifica main/rule-pool. Base codice bot f87f2d63c5849b177dbd33ee43c5be05ca58c8ed.

## Stato attuale del branch
Moduli:
- `capital_manager.py`: primitive Decimal per day budget, flow-neutral P&L, daily lock 20% e $450 (pure).
- `vault_manager.py`: rollover virtuale, lotti pending, manual withdraw (solo PAPER), idempotency receipts, contributi manuali esclusi da profitti (pure).
- `position_sizer.py`: 10%/25% del budget/day frozen, prenotazioni di DCA/split.
- `capital_journal.py`: prototipo journal fail-closed per trasferimenti, in volume sintetico, recupero caso crash intent->snapshot. **Non collegato a tutte le scritture legacy, perciò NON pronto a essere installato.**
- `engine.py`: aggancio opzionale `set_capital_policy()`; open/DCA/split rispettano limiti solo quando abiliti esplicitamente con giornata convalidata. Runtime distribuito NON modificato.
- Test: `test_capital_management_v1.py`, `test_capital_journal_v1.py`, `test_capital_engine_integration_v1.py`; workflow CI isolato `.github/workflows/capital-management-v1-ci.yml`.

App sviluppata separatamente da `main` su `work/capital-dashboard-v1`: `capital_view.py`, `desk_api.py`, frontend CapitalPanel + API Dashboard, test e workflow. Dashboard resta nascosta se non trova `capital.schema_version=1`, `status=READY` e heartbeat `capital_v1=true`. Il tasto prelievo invia solo richiesta e mostra completato SOLO dopo ACK; bot attuale non consuma tali richieste, quindi API fa fail-closed.

## Blocchi prima di poter parlare di integrazione finita
1. Un unico writer transazionale per **tutte** le operazioni che variano cash/margini/trade e vault. Il journal dimostra sicurezza di una transazione isolata, ma il bot legacy salva state_v2 a ogni ciclo e durante altri comandi: va unificato prima di qualsiasi deploy. Non creare istanze extra.
2. Runtime rollover logico 00:00 UTC valido anche con bot in pausa e prezzo affidabile del confine per posizioni aperte; fail-closed se manca storia, senza fare un "now" spacciato per mezzanotte. Idempotenza e recupero di giornate saltate.
3. Riconciliazione exact equality ledger/cassa/posizioni + test crash in ogni punto, backfill dello stato vecchio con vault0 SENZA reset; ledger e file del cervello nel backup/rollback. Stop 20% e latch agganciati al conto/CLI senza alterare la baseline fino a release.
4. Applicare politiche percentuali alle decisioni **rules e AI**, sistemare guardrail minimi $50/$150, importi forzati, testi dei prompt e P&L dashboard senza aggiornamenti di strategia non autorizzati. Nessun budget intraday gonfiato da withdrawal.
5. Implementare nel bot consumer `vault_transfer_request.json`, nonce/idempotenza, ACK persistentemente verificabile `capital.receipts`, e versioni dello stesso schema tra app e bot. Sicurezza cross-mode PAPER verificata.
6. Replay storico / property tests contabili / test portfolio reset / dump di SQL? backup e piano reversibile. Conflitto tra reset legacy e vault: rifiutare reset finché portafoglio non ha una procedura migration-safe.
7. Preparare diff strettamente limitato e review incrociata con Claude/Work, no deploy senza OK.

## Test
- Workflow `Capital Management V1 - offline safety tests (no deploy)` attivato sul ramo: nessun VPS/SSH/secret, runner GitHub.
- Python/accounting CI passate al run 39940415034 (prima dell'aggancio al motore) e run 39941245956 (dopo il primo aggancio), 29 test sintetici. Il run successivo con suite legacy sarà documentato dopo conclusione.
- Dashboard CI 39940918023: test backend/compilazione React passati, NON deploy.

## Prossimo lavoro autorizzato
Completare il contratto atomico dei writer, incorporare Capital/Vault nel ciclo del bot e negli ACK, fare replay e test compatibilità; poi freeze spec, PR, audit, solo successivamente richiedere OK deploy. Non usare `desk-deploy.yml` ordinario: rule-pool include modifiche ulteriori rispetto a baseline.
