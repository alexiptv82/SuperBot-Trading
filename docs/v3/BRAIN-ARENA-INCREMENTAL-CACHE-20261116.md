# AI Arena — Cache incrementale isolata (16 novembre 2026)

## Stato provato sulla VPS
- Screenshot utente, ore 17:19 locali: `Ran 10 tests in 0.725s`, `OK` sulla conversione indicatori reali Brain in `backend.v3.arena.test_compact_market`.
- Precedenti prove user: 25/25 storico completo, 575 pagine, zero ordini, zero chiamate AI. **Lo snapshot di quei 25 mercati era solo in memoria; non è una cache persistente già disponibile.**
- I modelli DeepSeek/Qwen/MiniMax NON hanno ancora analizzato dati simultaneamente, e i 14 giorni PAPER NON sono iniziati.

## Nuovo lavoro
Branch: `work/arena-incremental-research-cache-20261116`, isolato, nessuna modifica al runner o alla UI.

`backend/v3/arena/incremental_cache.py`:
1. `delta_plan`: prende un batch verificato e un timestamp futuro, determina esattamente gli intervalli mancanti dei timeframe 1m/15m/1h/4h. Limita l'età della cache a 30 minuti; scaduto -> **stop, richiesta di nuovo bootstrap completo**, non dati interpolati.
2. `merge_delta`: accetta soltanto nuovi dati di candele **completamente chiuse**. Verifica presenza simboli/timeframe richiesti, timestamp esatti, nessun duplicato o gap; ricostruisce un nuovo `FrozenMarketBatch` e torna il nuovo SHA. Fail-closed: nessuno snapshot parziale.
3. `save_research_cache` e `load_research_cache`: scrittura opzionale atomica con file 0600, fsync, rename e hash SHA-256. Consenti **solo** cartella scratch `/tmp/superbot-arena-research-*` o radice dedicata `/var/lib/superbot-arena-research` che deve essere creata separatamente previa autorizzazione. Rifiuta link simbolici, cartelle arbitrarie, dati manomessi e cache eccessive.
4. Non esegue I/O di rete, né usa API a pagamento, né scrive nel journal, nei portafogli, nei container, nelle directory operative o nelle chiavi private.
5. Le 25 crypto restano una lista **provvisoria**, oro e argento inclusi. Non autorizza trade.

`backend/v3/arena/test_incremental_cache.py`: **14 test scritti** su fronte multiframe, gap, duplicati, futuro, dati illeciti, scadenza, integrità, ripresa da file e protezione path. **Revisione statica superata**, ma i 14 test **non sono ancora stati eseguiti sul checkout Python reale**. Prossima azione: clone locale del branch, eseguire con unittest senza rete, senza scaricare 575 pagine.

## Attenzione operativa
Questa è una **libreria di cache**, non un servizio attivo: serve ancora il meccanismo di primo bootstrap (la vecchia prova era volatile) e l'adattatore GET di aggiornamento che rispetti limiti Bitget. Per il ciclo operativo 15 minuti la cache può ridurre il numero di pagine, ma in futuro dovremo tenere conto di rate limit, periodi di disconnessione, riconciliazione del timestamp, cambio di universo e protezione delle posizioni ancora aperte.

La cache non deve essere usata come fonte di indicatori di trading se vecchia, incompleta o corrotta. Tutto invariato per Falco SHORT, Toro e Brain DeepSeek attuale; nessun deploy, nessun merge, nessuna GitHub Action intenzionale.
