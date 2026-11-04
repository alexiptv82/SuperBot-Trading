# Revisione ChatGPT — prototipo Brain V3 F2 consegnato da Grok (2026-11-03)

**Stato: DRAFT, NO DEPLOY, NO MERGE.** Questa PR confronta F2 con il branch F1 della PR #29, non con `main`.

## Integrità della consegna

Allegato utente `v3-brain-f2-isolated.tar.gz` (~5,9 KB compressi), 5 sorgenti Python e README da archivio. Estrazione controllata senza link o path traversal. I blob dei 5 sorgenti Python sono identici byte-per-byte ai file dell'archivio (Git blob SHA). README originale incluso come riferimento, con pulizia editoriale e aggiornamento dello stato del ramo; il contenuto funzionale resta quello consegnato da Grok.

Comando eseguito localmente con Python/pytest: `PYTHONPATH=. python -m pytest -q backend/tests/test_brain_f2.py` → **5 passed**. Il modulo non effettua richieste di rete, non ha esecutori PAPER né connessioni a VPS/AI reali.

## P0 — problemi dimostrati che impediscono ogni integrazione operativa

1. **OPEN senza risk gate obbligatorio:** `BrainEngine(..., risk_quoter=None)` + `MockClaudeReviewer(always_approve=True)` + contesto TRENDING produce `DecisionKind.OPEN`, `ProposalStatus.APPROVED` e `risk_quote=None`. Occorre un fail-closed obbligatorio con approvazione esplicita tramite `RiskQuote.allowed`, policy approvata e dati validati. La classe attuale produce una *proposta*, non deve essere trattata come ordine.
2. **Firma incompatibile con F1:** `engine.py` invoca `risk_quoter(decision.proposal)`, ma `backend/v3/risk.py` espone `quote_paper_risk(policy: RiskPolicy, request: RiskRequest)`. Iniettando direttamente la funzione F1 si ottiene `TypeError: missing 1 required positional argument: request`. Serve adapter esplicito che costruisca e validi `RiskRequest` dal portafoglio Brain corrente, includendo min equity e quote di costi.
3. **Persistenza dichiarata ma assente:** `journal_append` non viene chiamato (`pass` nel ramo), perciò memoria solo RAM. Probe con callback che registra invocazioni: 0 chiamate dopo un ciclo. Necessari `Event` validi, idempotency/event IDs, `portfolio_id=brain`, run scope, persistenza e test di riavvio.
4. **Rivalutazione posizioni inesistente:** `_reevaluate_positions` restituisce invariato HOLD; niente chiusure, trailing o protezione. Serve contratto posizione con ID, PnL/costi, market freshness, regole di chiusura e stop *non permissive*; nessuna operazione reale consentita.
5. **Mancano validazione input e invarianti di decisione:** contratti con `proposal: Any`, `risk_quote: Any`, timestamp/decimal/confidence/symbol e confini account non verificati. Non esiste un gate di fedeltà allo stato di mercato per decisioni stale e il revisore muta decisione/sources in-place.

## P1 — copertura test e onestà semantica

- `test_independent_portfolio_observation` include `assert ... or True`: asserzione tautologica, quindi non certifica provenienza o isolamento.
- `test_no_automatic_fallback` usa `force_no_trade=True`, non simula eccezioni reali/timeout/credit 402 di DeepSeek; l'analista può propagare un'eccezione senza decisione `NO_TRADE`.
- Il revisore non verifica davvero divergenze Falco/Toro o budget rischio, a differenza del suo docstring.
- Il mock DeepSeek è una regola trend-following LONG deterministica per test, **non AI libera** e non richiede o prova la strategia operativa futura.
- `ProposalStatus.EXECUTED_PAPER` esiste solo nell'enum, non avvengono esecuzioni.
- Mancano test di *close*, *modify stop*, idempotenza/restart, review corrompente, costi funding/slippage, raggruppamento portfolio/run e non-trading per market stale.

## Criteri prima di promuovere oltre DRAFT

Nessuna esecuzione PAPER/AI vera senza: backup off-host restaurabile certificato; F1 con gates accettati; risk gate su OPEN fail-closed con policy versionata, protezione assoluta 450 USDT invariata; contratti CLOSE/MODIFY_STOP protetti; EventJournal verificato e idempotente; no fallback meccanico e NO_TRADE su AI irraggiungibile; osservazione Falco/Toro non bloccante e senza contaminazione; test negativi; dashboard tre portafogli; approvazione separata dell'utente per merge, reset wallet, deployment e restart.

Questa PR preserva il prototipo **originale di Grok** per una revisione riproducibile, senza presentarlo come motore completo.
