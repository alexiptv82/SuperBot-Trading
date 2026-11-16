# Brain AI Arena — recupero lacune oltre 30 minuti (16/11/2026)

## Evidenza reale VPS (19:15)
- `ARENA_COMPACT_AUDIT RESULT=25_REAL_BRAIN_INDICATORS_VERIFIED_NO_DEPLOY`.
- `markets=25`, `source_bytes=738539`, `compact_bytes=31026`, `EXPANSION=11`, `RANGE=11`, `UNCERTAIN=3`.
- Identico SHA-256 del riepilogo per DeepSeek, Qwen e MiniMax: `5073abe0edbec55e99b237b710c94314d4702553f524b8fc23c0f7ba3a792db8`.
- Origine cache `a60016942548699e6b8b71049570d8313bae139d8208fbf22c931fc1b5e944ad`, time-asof `2026-11-16T17:32:18.639Z`, età all'audit 2.550 secondi.
- Non c'è esecuzione di modelli, nessun PAPER Arena, nessun ordine. **Gli indicatori sono STORICI, non dati di trading live**.

## Problema e soluzione di ricerca isolata
La libreria `incremental_cache.delta_plan` rifiuta intervalli oltre 30 minuti. Lo storico persistito ha già superato quel limite. Non bisogna cancellarlo né rieseguire le 575 pagine a ogni interruzione.

Sul ramo di ricerca `work/arena-gap-recovery-offline-20261116`:
- `backend/v3/arena/recovery_gap.py`: nuova libreria PURA per pianificare GET pubblici per soli intervalli mancanti, fino a **72 ore** di ritardo, con pagine massime di 190 candele e **125 GET complessive** su 25 mercati. Il controllo non consente tempi regressivi, missing/duplicate/incomplete OHLC e riconvalida il dataset completo in modo atomico **in memoria**.
- Recupero specifico per timeframe: se il numero di candele mancanti supera l'intera finestra conservata, il timeframe è **REBASED** a una nuova finestra completa, normalmente 60 recenti candele 1m. La continuità delle candele intermedie **non viene ricostruita** né affermata, e il dato `rebased` resta esplicito. Gli indicatori dei timeframe lunghi mantengono gli storici preesistenti.
- Oltre 72 ore, o se la pianificazione richiede più di 125 GET, **ferma e richiede revisione manuale**. Nessun fallback a un download full senza decisione dell'utente.
- `backend/v3/arena/test_recovery_gap.py`: 13 nuovi test **scritti, ancora da eseguire** sulla VPS. Include una prova sintetica di 72h su 25 mercati e 125 pagine, controlli anomalie e immutabilità del vecchio snapshot.
- `deploy/scripts/arena-gap-recovery-plan-20261116.py`: si limita a **leggere** la cache esistente e a calcolare il preventivo di GET, dato l'hash noto. **Non esegue il download né salva nulla.**

## Gate da rispettare
1. Eseguire i nuovi 13 test sulla VPS su clone del ramo. Se falliscono, correggere il ramo di ricerca, senza toccare runner/servizi.
2. Solo dopo i test: eseguire la pianificazione READ ONLY sulla cache vera e leggere conteggio richieste e regole di rebase.
3. Predisporre un adattatore GET e persistenza che usi una copia/verifica indipendente del file attuale, lock esclusivo, età massima della fotografia e checkpoint. **Non ancora scritto**.
4. Solo dopo: prove comparative AI su input comune, limite di costi esplicito, zero ordini; infine autorizzazione PAPER e UI dei tre portafogli da 2.000 USDT.

Falco SHORT preservato, Toro a riposo, Brain DeepSeek attuale non modificato. Nessun deploy, merge, riavvio, GitHub Actions volutamente avviate o chiamata AI a pagamento.
