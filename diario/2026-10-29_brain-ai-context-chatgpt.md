# Brain: integrazione del contesto AI

## 29/10/2026 — Integrazione contesto AI e riferimento storico: IN CORSO
- Utente «ok procedi» dopo consegna audit/riferimento48808a6. Autorizzati sviluppo e test offline del collegamento al contesto DeepSeek/Claude, non deploy o chiamate a pagamento.
- Ramo nuovo work/brain-ai-context-20261029 da48808a6aa5cd9d2a4a1933b27ebc7828fd3ac480; baseline di ripristino preservata. Riutilizzare reference builder e contrattoPlan/BrainPair, niente scorer duplicato o fallback automatico ai classici.
- Contesto di un conto per richiesta, compatibile con walletunico2000 nel disegno; non creare/azzerare/sommare i due database per fingere migrazione già fatta. Limiti finanziari del nuovo conto devono essere espliciti: nessun nuovo valore imposto in questa fase.
- Preparare prompt verificabile con costi, capacità, entrambi i punteggi storici/avvisi, timestamp e fingerprint esposizione; rispostaJSON con piano condizionale oHOLD; DeepSeek principale/Claude revisore selettivo iniettati e testati con risposte sintetiche.
- Ammissione solo dopo risposta coerente, non scaduta, contesto esposizione valido e con guardie esistenti su quote correnti. Timeout/revisione mancante non generano trade. Nessuna APIkey, rawprompt o testo errore sensibile nei journal.
- Solo codiceScalp/test/docs/CIisolata e diario. Classici, BrainFree, PWA, main/rule-pool, deploy, VPS e memoria cumulativa intatti. Unico autore ChatGPT su questi file.
