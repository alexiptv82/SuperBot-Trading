# SuperBot-Trading V3 — Brain F2 R1.9: audit finale offline

**Data:** 3 novembre 2026  
**Verdetto:** **OFFLINE F2 ACCEPTED — DRAFT ONLY, NO DEPLOY**

## Provenienza verificata

- Archivio caricato: `v3-brain-f2-r1.9-20261103.tar.gz`.
- SHA256 archivio materialmente ricevuto: `73a85c07005492b27ea937a6d700e70f2c322f60011c1060dd1cd687bfb28e4a`.
- Estrazione sicura: 19 membri (file e directory), senza path traversal o symlink.
- F1 immutata: Git blob `backend/v3/events.py` = `cd4ce09233cdfc41be43dd7083aac791e8e2c56d`; `backend/v3/risk.py` = `514159b990c99740aee4f73b3bdd8839226e65bc`.
- Gli esatti blob delle sorgenti R1.9 sono stati verificati con Git SHA prima del commit.

## Test indipendenti e CI

| Esecuzione | Risultato | Natura |
|---|---|---|
| Locale Python 3.13.5, test inclusi | **85/85 PASS** | Test dell'archivio ricevuto |
| Locale Python 3.13.5, +8 invarianti finali ChatGPT | **93/93 PASS** | Solo offline con SQLite temporaneo, dati sintetici |
| GitHub Actions Python 3.10, F1+F2 | **198 PASS, 0 FAIL, 0 xfail** | Log del job `126019613249` verificato |
| GitHub Actions Python 3.11, F1+F2 | **198 PASS, 0 FAIL, 0 xfail** | Log del job `126019614065` verificato |

CI: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41665508383

## Integrazione in bozza

- PR #33: https://github.com/alexiptv82/SuperBot-Trading/pull/33
- Branch: `work/v3-brain-f2-grok` (base PR #29, F1).
- Commit R1.9: `ec999f896addd7d90be6d85075ad4d7e09f8b667`.
- Un solo commit in PR DRAFT; confermato diff senza modifiche a `backend/v3/events.py` o `backend/v3/risk.py`.
- Implementazione attualmente isolata, solo mock, non collegata a runtime PAPER o VPS.

## Invarianti verificati nel perimetro offline

- Senza verificatore della policy: nessuna `OPEN/APPROVED`.
- Mandato richiede esplicitamente portfolio Brain, run, operatore, versione e policy hash; il callback verifier deve ritornare booleano `True` esatto.
- Rischio numerico non finito, pause/latch, dati stantii, contesti di mercato malformati e quote di rischio negate portano a `NO_TRADE`.
- Le decisioni non azionabili non conservano proposte e risk_quote non certificati nella risposta/memoria.
- SQLite EventJournal: append verificato, check hash chain, replay e concorrenza; nessuna doppia approvazione delle medesime richieste sintetiche.
- Solo `OPEN` può essere `APPROVED` come **proposta**, mai `EXECUTED_PAPER`; CLOSE/MODIFY_STOP rimangono non eseguibili.

## Gate ancora aperti per qualsiasi operatività

1. **Trust anchor reale per la policy:** l'iniezione di una callable di test con `return True` non autentica un operatore. Il runtime deve usare un registro/ricevuta o servizio fidato, indipendente dall'analista AI e vincolato al mandato; in assenza il Brain resta fail-closed.
2. Integrazione servizi AI DeepSeek/Claude reali con budget, errori 402/timeouts, Secrets e audit.
3. Contratti di esecuzione PAPER/posizioni, riconciliazione, kill-switch, gestione prezzi live e osservabilità.
4. Dashboard unificata Brain/Falco/Toro, monitoraggio e test operativi separati, backup/restore off-host verificati e autorizzazione esplicita per futuri deploy.
5. Pulizia README F2 originale: contiene alcune descrizioni legacy (journal solo hook) non aggiornate al codice R1.9. Documentazione non bloccante per il merge di codice in PR DRAFT, ma da correggere prima di promuovere la PR.

**Nessun merge, deploy, restart, reset, accesso VPS, pagamento AI, trading reale o PAPER operativo è stato effettuato.**
