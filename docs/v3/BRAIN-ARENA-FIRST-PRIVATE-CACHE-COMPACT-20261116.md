# Brain AI Arena — prima cache persistita → indicatori reali (16/11/2026)

## Prova VPS delle 18:39 (fonte: screenshot utente)

**Bootstrap completato.** Sono state recuperate 575 pagine storiche per 25 mercati, con `snapshot_age_seconds=223`. Il file privato di ricerca `/var/lib/superbot-arena-research/arena-market-research-cache.json` è stato creato con successiva verifica di rilettura e digest:
`a60016942548699e6b8b71049570d8313bae139d8208fbf22c931fc1b5e944ad`.
Hash preparato uguale per DeepSeek/Qwen/MiniMax; nessuna richiesta AI reale, nessun ordine, nessun servizio cambiato, `RESULT=FIRST_PRIVATE_CACHE_SAVED_NO_DEPLOY`.

**Importante:** al momento della prima scrittura questo file era un'istantanea storica, NON un servizio aggiornato automaticamente. `incremental_cache.delta_plan` rifiuta un ritardo oltre 30 minuti; non affermare che la cache sia ancora fresca ore dopo. Il recupero sicuro di un lungo downtime e il timer di aggiornamento non sono ancora implementati né installati.

## Nuovo step isolato: sola lettura dei dati VERI

Branch `work/arena-cache-to-compact-readonly-20261116`, file `deploy/scripts/arena-cache-compact-audit-20261116.py`.

Lo script accetta solo `--audit <expected_sha256>`, usa la cache privata già salvata e `load_default_params()`, verifica che siano 25 asset incluso oro e argento, che il digest coincida con quello dello screenshot, poi usa **l'implementazione originale di Brain** `build_compact_market` → `build_market_view`, senza formule nuove. Verifica i 3 timeframe principali per tutti i 25 asset, produce hash del riepilogo JSON compatto e verifica parità di byte destinati a DeepSeek, Qwen e MiniMax. Stampa soltanto conteggio regimi, byte e SHA, non le candele.

L'esecuzione non effettua rete, non apre posizioni, non legge chiavi, non contatta AI né scrive nulla. Se indicatori reali, origine, hash o dati non passano, stampa `NOT_VERIFIED_...`: fallimento utile a correggere *solo* il laboratorio, nessun deploy.

**Stato verifiche:** il nuovo codice ha superato soltanto il controllo statico; il collaudo integrato sui 25 asset veri **non è ancora stato eseguito dalla VPS**. L'esito desiderato è `RESULT=25_REAL_BRAIN_INDICATORS_VERIFIED_NO_DEPLOY`.

## Cosa segue

Dopo la verifica riuscita occorre definire un aggiornamento incrementale e soprattutto il recupero dopo un gap oltre 30 minuti senza riscaricare 575 pagine a ogni decisione; solo poi valutare una prova controllata dei tre modelli sullo stesso input compatto, con costi autorizzati e senza ordini. I tre portafogli PAPER da 2.000 USDT e i 14 giorni non sono avviati. Falco SHORT non viene modificato; Toro resta da parte; Brain attuale invariato.

Nessun merge, branch di produzione, container o GitHub Actions intenzionale.
