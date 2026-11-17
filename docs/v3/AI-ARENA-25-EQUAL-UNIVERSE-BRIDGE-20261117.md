# AI Arena — Piano condiviso 25 mercati, confronto con il Brain operativo (17 novembre 2026)

## Causa del problema verificata nel codice GitHub
Nella configurazione `backend/v3/runner/runner_config_brain2000_paper.json` il Brain 2.000 PAPER ha tuttora esattamente **8 simboli**: `BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT, ADAUSDT, LINKUSDT`.
`backend/v3/runner/wiring.py::build_runner` passa `config.symbols` a `run_brain_cycle`, che fa un giro e chiede decisioni per ciascun simbolo. `backend/v3/runner/config.py` permette fino a 40 simboli, ma **aumentare direttamente la lista da 8 a 25 non equivale a usare una sola analisi sui 25**: potrebbe triplicare il lavoro sulle candele e il numero di chiamate DeepSeek per ciclo, incontrando il budget `daily_cap_usd`. Inoltre `runner_config.json` (1.000 USDT) contiene gli stessi 8. La versione effettiva installata oggi sulla VPS va comunque confrontata con questi file: GitHub non prova quale configurazione abbia caricato il processo.

La ricerca AI Arena ha già uno **snapshot storico pubblico completo di 25 mercati** (23 criptovalute + XAUUSDT/XAGUSDT), digest comune a DeepSeek/Qwen/MiniMax, e una prova reale delle tre risposte. La classificazione è ancora `PROVISIONAL_NOT_TRADE_APPROVED`: il mapping CoinGecko→Bitget è ancora preliminare e alcune crypto possono richiedere verifica native/wrapped/stablecoin. Una selezione dinamica di top-market-cap non implica permesso di aprire PAPER.

## Nuovo lavoro (solo ricerca)
Branch `work/arena-shared25-runner-bridge-20261117` derivato da `work/arena-first-three-ai-results-20261116`. Nessuna patch al runtime, ai journal o all'app.

- `backend/v3/arena/trial_universe_bridge.py`: funzione pura `review_equal_universe` che legge il pacchetto comune dei 25 mercati, il `RunnerConfig` reale da 2.000 e — eventualmente — 25 identità contrattuali indipendentemente revisionate. Riporta **la stessa lista proposta** a DeepSeek/Qwen/MiniMax, la lista precedente degli 8 e problemi da correggere.
- Il gate rifiuta o segnala dati oltre 15 minuti, capitale diverso da 2.000, equity floor diverso da 450, leva incompatibile, identità ancora solo per corrispondenza nome, contratti disattivati/quote non-USDT/limiti leva insufficienti, ID o rank duplicati, classificazione metal errata e wrapped token presentati come native. Senza mappatura verificata, il risultato **NON È PRONTO**.
- `TrialUniverseReview.executable=False` **sempre**, anche se tutte le identità sono revisionate: il codice prepara l'integrazione successiva ma non genera permessi di trading, ordini o file di configurazione. Falco SHORT, Toro, Brain e tutti i servizi restano invariati.
- `backend/v3/arena/test_trial_universe_bridge.py`: 14 casi offline contro la configurazione 2.000 e fixture reali degli indicatori Brain. **Scritti, non ancora eseguiti sulla VPS.**
- `deploy/scripts/arena-runner-universe-audit-20261117.py`: `--audit <expected_private_cache_sha256>` legge la cache privata PAPER di ricerca, non contatta Bitget né le AI, non modifica file, fa audit degli 8 contro i 25 e dichiara `UNIVERSE_PREVIEW_ONLY_NOT_DEPLOYED`.

## Percorso più corto verso la richiesta dell'utente
1. Test offline + audit configurazione sulla VPS; verificare il parametro `--config` effettivo del servizio runner, **senza ristartarlo**.
2. Verificare una **roster persistente e certificata per il trial**, 23 crypto native ammissibili per capitalizzazione + XAU/XAG, contratto USDT e le sue leve, liquidità e freshness; mantenere T0 congelato per 14 giorni per parità, aggiornare dinamicamente solo con policy dichiarata e gli stessi refresh per tutti.
3. Un unico snapshot locale condiviso per ciclo, una chiamata *comparabile* per modello che ordina o respinge i 25 mercati, invece di 25 chiamate a modello; fare la selezione candidato prima di chiamare il risk engine del rispettivo wallet. Stesso risk/fee/slippage e strutture LONG/SHORT, run/journal/exit owner isolati. Il modello OpenRouter DeepSeek usato nella prova singola va distinto dal `deepseek-flash` realmente operativo.
4. Completare la UI già esistente nel ramo `work/brain-arena-readonly-wallets-ui-fix-20261116` e collegare una nuova API `GET /api/v3/arena` soltanto dopo test e montaggio autentico dei 3 journal. Mostrare saldo/equity/PnL/trade per ciascuna AI, non valori inventati; T0 comune e refresher ~30s. Le 3 card esistono già come prototipo; **non sono installate**.
5. Dopo suite di integrazione, backup, cutover PAPER e consenso di deploy, avviare i tre wallet virtuali da 2.000 USDT, senza cancellare la run storica Brain né la strategia Falco. Fino ad allora non dire che la prova 14 giorni sia iniziata.

## Protezioni
Nessun deploy, merge, reset, ordine, chiamata AI a pagamento, GitHub Action avviata o modifica del runner attuale da questo branch. Le posizioni PAPER già aperte sul vecchio Brain devono continuare ad avere il servizio di uscita e la possibilità di chiusura manuale anche dopo l'eventuale avvio di un trial separato.

Le prove dei nuovi 14 test rimangono da eseguire prima di presentarle come PASS.


## Colllaudo VPS confermato dall'utente (17/11/2026 ore 11:01 Europe/Rome)

Il comando `python3 -m unittest -q backend.v3.arena.test_trial_universe_bridge` ha prodotto `Ran 14 tests in 15.898s / OK`.
L'audit sulla cache privata ha prodotto:
- `repository_brain2000_config_symbols=8`, `candidate_count=25`, `parity_across_3_models=TRUE`
- `readiness_issues=STALE_RESEARCH_SNAPSHOT,ASSET_IDENTITY_AND_CONTRACTS_NOT_REVIEWED`
- `live_deepseek_config_changed=NO`, `paper_wallets_started=0`, `orders=0`, `paid_AI_calls=0`
- `RESULT=UNIVERSE_PREVIEW_ONLY_NOT_DEPLOYED`

I 25 candidati nello snapshot storico includevano GRAMUSDT, HBARUSDT, HYPEUSDT, PEPEUSDT, QNTUSDT e ZECUSDT. Non attribuire loro categorie o eleggibilità finché CoinGecko ID e contratto Bitget non sono esaminati con una nuova fotografia. La stessa parità tra tre AI NON implica che la lista sia corretta o autorizzata per trading.

### Prossima diagnosi con soli tre GET pubblici
Sul checkout VPS già esistente (senza cambiare branch o bot):
```bash
python3 -m unittest -q backend.v3.arena.test_universe &&
python3 deploy/scripts/arena-public-marketcap-preview-20261116.py --selftest &&
python3 deploy/scripts/arena-public-marketcap-preview-20261116.py --probe
```
Il probe legge un catalogo CoinGecko e due cataloghi Bitget, stampa coin_id, rank, ticker, esiti di preselezione, e dichiara che rimane PROVISIONAL. Nessuna operazione, credential, scrittura, deploy. Il test `test_universe` è offline e controlla che il monitor uscite mantenga il simbolo già aperto anche se scompare dalla lista top-cap.
