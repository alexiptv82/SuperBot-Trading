# Checkpoint S1 — Supervisore SuperBot V3, evidenze prima della decisione
**Autore:** ChatGPT GPT-6 · **Data:** 6 novembre 2026 · **Stato:** sviluppo locale verificato, nessun merge, deploy o attivazione VPS.

## Punto di partenza
- ZIP esatto caricato `superbot-trading-e25c8dd.zip`, commit `e25c8dd8db88fd6994e3b7a75ecfdec5ff258421` (PR #57); modulo S0 precedente (pacchetto in chat).
- PR #61 dashboard su ramo separato, non integrato.
- Obiettivo deciso dall'utente: Supervisore tre portafogli / sei servizi; S1 cattura informazioni al momento della decisione, invece di inventare spiegazioni dopo.

## Lavoro consegnato
Nuovo `backend/v3/supervisor/evidence.py` (non applicato in branch codice):
- `supervisor_observation` append-only prima del modello con vista L5 delle sole candele chiuse (15m, 1h, 4h), snapshot di equity/margine/rischio PAPER stringhe Decimal, regimi e digest del mercato.
- Candidati scartati prima del modello registrati con codici chiusi senza trattarli come NO_TRADE.
- `supervisor_resolution` dopo BrainEngine: kind/status/rationale allowlist, proposta normalizzata, RiskQuote solo se disponibile, link journal verificato. Memoria/invalidation non registrati: non inventati.
- `read_evidence` read-only: verifica hash chain e unisce osservazioni/risoluzioni; idempotenza e fallimento chiuso.
- Documenti: `docs/v3/SUPERVISORE-S1-EVIDENZE-2026-11-06.md` e **proposta** `docs/v3/S1-OPT-IN-RUNNER.patch` per file `runner/cycle.py` di proprietà Claude; default disabilitato `supervisor_evidence=False`. La patch è stata applicata **soltanto in copia**, testata e rimossa. Il runner originale è rimasto identico.
- Test unitari `backend/tests/test_v3_supervisor_evidence.py`; 9 test integrativi opzionali in `integration/test_s1_runner_opt_in.py` che vanno lanciati solo sulla copia dove la patch sia stata applicata.

## Test ripetuti con esito verificato
- 83/83 test S1 dalla radice e da `/tmp`.
- 489/489 test di compatibilità (S1, S0, EventJournal, L1, cycle runner, manual close, daily-loss) senza modifiche al runner.
- 190/190 in prova isolata con patch attivabile, di cui 9 test espliciti opt-in (inclusa inibizione nuove aperture se registrazione evidenza fallisce).
- Dry-run patch su base `e25c8dd`: superato.
- **385/385 file originali ZIP byte per byte invariati.**
- Non eseguiti: tutta la suite 6k+, Jest, benchmark a 30 simboli, VPS, integrazione hook nel runtime reale.

## Pacchetto e rapporto negli allegati della chat
- `SuperBot-V3-Supervisore-S1-Evidenze-2026-11-06.zip`, SHA-256 `221c42b3c67c5826bda30bb97e532c0a073441bca16f5fa9d823fa5f6e8bf8ff`.
- `RAPPORTO_SUPERBOT_V3_SUPERVISORE_S1_2026-11-06.md`, SHA-256 `7428db6d99a464fdd5cea12a15c384deb48653edb3d7132e8d75c23ec461d8b2`.
- Per applicare: prima S0, poi nuovo evidence.py e test. Patch runner **non** auto-applicabile senza revisione del suo proprietario.

## Prossimo passo
**S1b**: coordinare integrazione con responsabile runner, test prestazionali su universe di simboli e CI su branch isolato prima di abilitare S1. Poi **S2**: API GET autenticata e terminale decisioni S0+S1 sulla dashboard PR #61. Poi **S3**: apprendimento con esperimenti preregistrati, costi e validazione OOS.

**Invariato e non autorizzato a cambiare:** PAPER; rischio 2% per trade, open risk 5%, floor 450 USDT, freno giornaliero warn 35%/halt 50%. Nessun avvio Brain, merge/deploy, redeploy classici, accesso VPS, dati reali o segreti.
