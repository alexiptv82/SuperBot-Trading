# AI Arena — UI smoke build e monitoraggio P&L DeepSeek (17 novembre 2026)

## Provenienza
Questa fase prosegue la richiesta dell'utente di vedere sul Samsung le operazioni e le performance delle tre AI in tre portafogli PAPER separati. Branch `work/arena-ui-smoke-build-20261117` basato su `work/arena-dashboard-discoverable-readonly-20261117`, che a sua volta deriva dal frontend AI Arena read-only. Non è un deploy.

## Correzioni in questo branch
- `frontend/src/pages/Overview.js`: il collegamento `/arena` è ora un `<a href>` compatibile con i test SSR senza contesto Router e con `REACT_APP_BASENAME`. Falco/Toro e la pagina Overview rimangono invariati salvo il link.
- `frontend/src/brainArenaModel.js`: `markedOpenPnl` somma i soli P&L dei prezzi realmente presenti tramite `price_source=ticker`. Se **anche una sola** posizione manca di mark o se il numero di posizioni differisce fra le letture HTTP overview e trades, `unrealized_pnl=null` (non 0). `realized_pnl` resta separato; `trial_comparable=false` per lo storico DeepSeek.
- `frontend/src/pages/BrainArena.js`: gli open trade mostrano prezzo disponibile/ROI quando verificati, l'ultimo evento e il refresh ogni 30 s. `equity` non viene inventata quando `equity_basis=open_unmarked`.
- `frontend/src/brainArenaModel.test.js`: 3 test aggiunti su PnL multi-posizione verificato, rifiuto dei mark mancanti e disallineamento conteggi.
- `frontend/src/pages/BrainArena.test.js`: 3 test Jest nuovi su anteprima SSR dei tre portafogli, dati DeepSeek con PnL aperto e Qwen/MiniMax non avviati, errore API senza profitto fittizio e senza POST.
- `frontend/src/pages/Overview.test.js`: SSR verifica il link AI Arena senza Router esterno.
- `deploy/scripts/arena-ui-isolated-build-20261117.sh`: smoke completo compilazione React e test Jest **soltanto nel clone temporaneo**, con Yarn v1 frozen lock, resource gate, nice CPU, nessun postinstall, nessuna GitHub Action, nessuna modifica ai servizi. La build non è pubblicata e non tocca /opt. Necessita Node>=16, Yarn v1, >=1.4 GB fra memoria disponibile e swap e >=1.6GB disco nel clone; in caso contrario termina senza build.

## Collaudo ancora da eseguire sulla VPS
Con solo un comando Termius da root:

```bash
D=$(mktemp -d /tmp/arena-ui-smoke.XXXXXX) &&
git clone --quiet --depth 1 --single-branch --branch work/arena-ui-smoke-build-20261117 https://github.com/alexiptv82/SuperBot-Trading.git "$D/repo" &&
cd "$D/repo" &&
bash deploy/scripts/arena-ui-isolated-build-20261117.sh
```

Il risultato atteso è `ARENA_UI_BUILD RESULT=TESTS_AND_REACT_BUILD_VERIFIED_NO_DEPLOY` e un digest build. Non affermare che i test abbiano passato prima dello screenshot del risultato.

## Stato reale dei servizi
- App pubblicata: ancora non aggiornata. Il precedente `/arena` è presente nel branch, ma il bundle in produzione non è stato sostituito.
- Existing DeepSeek: il runner PAPER su GitHub utilizza la vecchia configurazione a 8 simboli; actual VPS config da controllare, storico separato dal trial a 3 AI.
- Qwen e MiniMax: **nessun journal/servizio PAPER di trial attivato**. Non visualizzare equity, trade o profitti fittizi.
- `backend/v3/arena/read_view.py` può verificare i journal individuali quando esisteranno, ma l'equity con posizioni aperte non ha ancora una fonte mark comune. Prima di poter chiamare la schermata "monitoraggio 3 AI live", serviranno un aggiornamento prezzi validato e il T0 comune.
- Universe: il controllo pubblico ha identificato 23 candidati + XAU/XAG, ma è `PROVISIONAL_LIST_CATEGORY_AND_CANDLES_PENDING`; non certificato. Il bridge di ricerca e il frontend sono su rami diversi, da integrare **solo dopo** test e consenso.

## Gate per la versione visibile sul telefono
1. Smoke test e build isolata: per verificare la UI senza interrompere i bot.
2. Una anteprima su URL distinto (protetto con autenticazione), dati reali solo dello storico DeepSeek e Qwen/MiniMax "non avviato", senza sostituire l'app in uso.
3. Successivamente 3 motori PAPER separati con rischi, limiti, output OpenRouter, journal e monitor uscite, e feed comune con mercati revisiti; T0 unico 14 giorni. Backup+verifica e consenso esplicito prima del cutover e deploy.
Nessun reset, merge, deploy, commit su rule-pool, API calls a pagamento, ordine, modifica di Falco o dei servizi Brain da questo ramo.
