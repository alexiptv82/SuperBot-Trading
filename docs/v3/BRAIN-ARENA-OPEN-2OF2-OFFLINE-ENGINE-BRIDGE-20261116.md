# Brain AI Arena — OPEN sintetico 2/2 e confine modello-verso-Brain (16 novembre 2026)

## Risultato verificato dall'utente su VPS alle 14:42

- SELFTEST=PASS_OFFLINE; 0 chiamate e 0 ordini nel selftest.
- Qwen 3.7 Plus: PASS_SYNTHETIC_OPEN_FORMAT, modello corrispondente, finish_reason=stop, input 132 token, output 41, 0 campi assenti, in più o errati.
- MiniMax M3.1 Flash: PASS_SYNTHETIC_OPEN_FORMAT, modello corrispondente, finish_reason=stop, input 298 token, output 41, 0 campi assenti, in più o errati.
- passed=2/2; orders=0; services_changed=0; RESULT=BOTH_SYNTHETIC_OPEN_FORMATS_VERIFIED_NO_DEPLOY.
- Limiti chiave residui PRIMA delle due richieste: Qwen 1.99906072 USD, MiniMax 1.99988063 USD. Distinti dal saldo conto OpenRouter (ricarica 10 USD dichiarata dall'utente).

**Non dimostra abilità finanziaria o un vantaggio commerciale**. Il modello copia un esempio OPEN fittizio, Qwen LONG e MiniMax SHORT. Nessun dato Bitget reale e nessun ordine PAPER.

## Nuova fase su branch isolato

Branch: work/arena-model-to-brain-offline-integration-20261116, derivato da work/arena-synthetic-open-offline-20261116.
File: backend/v3/arena/test_model_to_brain_boundary.py (**8 test sintetici scritti; ancora da eseguire**).

Testa esclusivamente funzioni locali, con trasporti AI simulati:
1. Contesto e market payload identico per entrambe le AI, hash identico, ma proposte direzionali indipendenti (Qwen LONG, MiniMax SHORT).
2. Passaggio alla funzione BrainEngine._validate_decision sulla run Arena di ciascun provider; una proposta valida resta DRAFT, non APPROVED o EXECUTED_PAPER.
3. Rifiuto della proposta di Qwen se attribuita al wallet MiniMax, e viceversa; rifiuto di proposte Arena sulla run storica DeepSeek.
4. NO_TRADE deve restare NO_TRADE, senza aperture forzate.
5. Output malformati, side 0, leva booleana, confidence e campi anomali vengono rifiutati senza retry.
6. Rifiuto prima della richiesta AI in caso di regime discordante o market view base non OK.

I test simulano build_market_view e build_scoreboard: **verificano il confine di integrazione**, non la correttezza degli indicatori su candele Bitget reali, né l'analisi finanziaria dei modelli. Richiedono esecuzione in checkout isolata, senza GitHub Actions per risparmiare i minuti.

## Prossimi blocchi

- Test offline effettivo e regressioni L5/Brain; poi feed di candele chiuse Bitget, cache e hash snapshot unici per DeepSeek/Qwen/MiniMax.
- Universo di ricerca da 23 crypto per market cap più XAUUSDT e XAGUSDT, ranking e categorie affidabili, vincoli exchange, liquidità e possibili discrepanze di contratti.
- Risk gate deterministico, tre journal, tre exit service, budget separati, tre wallet PAPER da 2.000 USDT, avvio T0 comune e frontend verificato. Nessuna run Arena è ancora partita.
- Falco SHORT: archivio codice GitHub esistente, ancora da completare backup dei dati e della configurazione effettiva su VPS prima di ogni pausa. Toro e Falco non modificati.
- Collaborazione selettiva AI rimane shadow-only, senza autorità trading.

Nessun merge, deploy, test GitHub Actions, API pagata, modifica servizio, reset o operazione PAPER effettuati da questa fase.
