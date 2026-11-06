# SuperBot V3 — S1b/S2: compatibilità runner e riuso L5 (ChatGPT)
**Data:** 6 novembre 2026 · **Stato:** sviluppo locale PAPER, nessun merge/deploy/push del codice, nessun intervento VPS.

## Verifica sorgenti e rami
- PR #57 runner `e25c8dd8db88fd6994e3b7a75ecfdec5ff258421` ancora draft.
- PR #61 dashboard `a9044b6759da327b44da04f9e7f51e211d44e03f` ancora draft, non unificata con #57.
- S0/S1 del pacchetto di prova sono RICOSTRUITI, non gli ZIP originali non materializzabili dalla Libreria. S2 proviene dal precedente pacchetto di provenance; nessun codice prod caricato.
- Base e25c8dd: 385 file nello ZIP, solo `backend/v3/runner/cycle.py` modificato TEMPORANEAMENTE nella sandbox. Consegnata una patch, non il file runtime; patch dry-run su originale PASS.

## S1b realizzato in copia e testato
- `PreparedMarketView` (snapshot L5 closed candles canonico + hash) è creato una volta e riusato da `record_observation`: non serve un terzo calcolo L5 per S1.
- Patch facoltativa `S1b-RUNNER-OPT-IN-NON-APPLICARE.patch` introduce `supervisor_evidence=False` default, osservazione prima del modello, risoluzione prima dell'ordine PAPER, eventi skip distinti da NO_TRADE. Scrittura non riuscita -> non esegue apertura. Non abilitato su GitHub o VPS.
- Risk quote non sempre presente in output engine anche su OPEN APPROVED; dashboard deve mostrare n.d., mai inventare.
- Ancora 2 calcoli L5 nel percorso completo con `DeepSeekL5Analyst` (regime/capture condiviso + vista che l'analista ricalcola); riuso completo richiede intervento separato sul proprietario dell'analista e test performance.

## Risultati verificati
- `PYTHONPATH=.:backend python -m pytest backend/tests/test_v3_*.py -q -p no:cacheprovider --disable-warnings` -> **4373 passed in 148.16s**, exit 0.
- Compatibilità mirata: **325 passed** (runner, daily-loss, manual-close, journal, S0/S1/S2).
- Da /tmp: **56 passed** sui test S0/S1/S2 e opt-in.
- Frontend: 3 file JSX con parsing valido e 9 assertion JS pure. **Jest/React interattivo NON eseguito**.
- Benchmark 6 simboli sintetici, 4050 candele chiuse ciascuno: base a 2 passaggi L5 5029,8 ms, S1b con append evidenza e 2 passaggi 5143,4 ms (+113,6 ms in questo campione). Tentativo 30 simboli SCADUTO per timeout e non dichiarato riuscito. No misure VPS/DeepSeek/stop.

## Artefatti conservati nella Libreria ChatGPT
- `/SuperBot-Trading/SuperBot-V3-S1b-S2-Integrazione-Isolata-2026-11-06.zip`, SHA256 `f6339da9ee963441cd12b92e8819c00a25fb05918d4932c69d085b25d4f86b5e`, library_file_id `libfile_da70c23ede4c819196bf760b990ff841`.
- `/SuperBot-Trading/RAPPORTO_SUPERBOT_V3_S1b_S2_INTEGRAZIONE_REVISIONE_2026-11-06.md`, SHA256 `9500021c605b321bd5227ed4e2a804a05a596e982b17cf9a044db23918bc8f3e`, library_file_id `libfile_3526f36410a48191ba159c26f8b51e01`.

## Prossimo gate
1. Revisionare patch con Claude (proprietario runner), distinguendo ricostruzione da S0/S1 originali.
2. Preparare branch di integrazione con PR #57 e #61 verificando conflitti, testare API/sessione e UI con Jest+build.
3. Benchmark 30 simboli sulla VPS PAPER e verificare che monitor stop/manual-close resti prioritario durante timeout DeepSeek 30s.
4. Opt-in resta off; nessun merge, redeploy, avvio Brain, modifica a strategie, capitale, rischio o storico senza OK esplicito.

**Parametri invariati:** perdita per trade 2% equity, rischio aperto 5%, warning 35%, halt 50% e floor 450 USDT. Solo PAPER.