# LONG P1 e classici come consiglieri del Brain — audit 30/10/2026

## Verdetto verificato nel repository

**LONG P1 NON integrato nei classici attuali.** Il ramo operativo `rule-pool` e il ramo isolato `work/classics-manual-teaching-20261030` contengono la stessa versione `backend/desk/signals.py` (blob SHA `57b524e75593b0fe6f3a0712af1a0b2f14bd4a75`); il ramo P1 `work/fix-p1-long-scoring` usa un diverso scorer (blob `d052adc7032592b49bea9345c2db8f784bf47821`). P1 riduce peso 4h 20→14 e 1d 15→10 e introduce bonus rimbalzo RSI1h e momentum 1h. La storia del codice non coincide, non fare merge automatico.

**Consiglio classico non alimentato nel servizio H24**: `legacy_reference.py` esiste come adattatore read-only per un vecchio scorer *frozen*, ma `BrainService.tick()` attualmente chiama `supervisor.step(markets,contracts)` **senza references**. Quindi non dichiarare attivo l'advisor P1 del Brain. `ai_context.py` consente reference non vincolante se fornita dal chiamante; i test sintetici dimostrano l'interfaccia, non il collegamento al market feed.

## Requisito dati importante

I classici originali ricavano 1h,4h,1d da `fetch_candles(...,15m,limit=1000)`. Circa 1000 barre 15m /16 = 62,5 barre 4h al massimo. P1 per il suo contributo EMA200 4h richiede almeno 200 barre 4h (circa 3200 barre 15m); **non interrompe automaticamente l'intero scorer**, ma il bonus trend 4h risulta assente e i punteggi possono restare sotto la soglia. P1 consente un trend 1d affidabile solo con 200 barre daily chiuse; senza di esse la componente viene lasciata assente. Occorre una sorgente 4h/1d affidabile o buffering storico causale dedicato, senza alterare gli stop o usare candele incomplete.

## Piano di integrazione non operativa

1. Creare un feed causale multi-timeframe 1h/4h/1d per il profilo P1, con controllo barre chiuse, buchi, precisione timestamp, 200 barre e cache. Non rallentare il tick di protezione. Una risposta incompleta equivale a advisor indisponibile, non a segnale SHORT.
2. Eseguire confronto P1 vs classico originale in shadow su LONG, SHORT, HOLD e mercati di inversione; test su dati reali fuori campione, non adottare il lettore Claude bocciato al laboratorio.
3. Pubblicare *solo* `long_score`/`short_score`/evidenza con SHA del codice e età dati; nessun ordine, nessun voto coercitivo, nessun veto. DeepSeek Brain resta autorità sulle proposte, stop del wallet autorità sulla sicurezza, Claude revisore selettivo.
4. Integrare l'advisor nel servizio Brain tramite worker cache/timeout separato e nella `supervisor.step(...,references=...)` solo dopo il gate prove. Senza dati il Brain continua con DeepSeek e le sue protezioni (nessun riferimento fabbricato).
5. Profilo P1 nei classici soltanto con consenso su attivazione specifica e test di regressione; nuovo deploy/merge separato dai rami UI.

Questo documento non attiva P1, non cambia scoring o dati VPS e non installa alcuna AI nei classici.
AI: chatgpt (chat normale)
