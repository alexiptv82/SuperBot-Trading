# Brain AI Arena — storico completo 25/25 e riepilogo indicatori reali

**16 novembre 2026.** Ramo isolato `work/arena-compact-real-indicators-20261116`, derivato da `work/arena-dynamic25-fullhistory-20261116`. Nessun merge, deploy, pausa o reset.

## Risultato effettivo VPS — screenshot dell'utente ore 17:09–17:10
- `ARENA_FULL25 history_GETs=575`, 23 pagine storiche per ciascuno dei 25 mercati.
- `ARENA_FULL25 RESULT=ALL_25_SHARED_HISTORY_VERIFIED_NO_DEPLOY`.
- Stesso hash SHA-256 per la preparazione dati destinata a DeepSeek, Qwen e MiniMax:
  `6466a8ec48912e9f5878700f6ad837446b59dbbf8ce5fca9168e181d6f2a03d6`.
- `classification=PROVISIONAL_NOT_TRADE_APPROVED`; `orders=0 paid_AI_calls=0 services_changed=0`.
- Questo non prova alcuna inferenza AI e non apre posizioni. **Lo snapshot è stato costruito in memoria, non persistito come cache riutilizzabile**.
- Minimo Brain preso dal suo codice originale: 1m=60, 15m=2893, 1h=733, 4h=193 candele chiuse per simbolo. Le 575 GET sono state una prova diagnostica, NON una frequenza accettabile per la produzione.

## Novità: convertitore di mercato compatto, stesso motore Brain
- `backend/v3/arena/compact_market.py`: riceve un `FrozenMarketBatch` completo e integra `backend/v3/brain_market/view.py::build_market_view` **senza duplicare la matematica**. Le candele Bitget sono convertite in `backend/v3/features/indicators.py::Bar` con prezzi e volumi `Decimal` reali.
- Per ogni asset legge solo barre chiuse e verificate, includendo il requisito di integrità del minuto 1m (mentre gli indicatori configurati da Brain sono 15m, 1h, 4h).
- Esige indicatori `status=ok` su 15m/1h/4h e regime conosciuto; se una barra o uno storico è incoerente, rifiuta il riepilogo (non invia un segnale incompleto).
- Produce JSON canonico compatto di tutti i `market` originali e del prezzo dell'ultima candela 15m, con due hash SHA-256: **provenienza delle candele complete** e **configurazione degli indicatori**. Non include le migliaia di candele raw, né i dati dei portafogli, né un permesso a operare.
- `for_provider("deepseek" | "qwen" | "minimax")` torna identici byte e hash; questa è **parità del dataset pronto**, non un invio a provider né una prova di competitività. Modelli non chiamati.
- `backend/v3/arena/test_compact_market.py`: 10 test offline che esercitano il vero codice Brain, il payload comune, provenienza, rifiuto dati manomessi/corti e la separazione dall'autorità trading. **Scritti, non ancora eseguiti sulla VPS**.

## Prossimo comando di collaudo
Clone isolato del ramo di ricerca, nessun GitHub Actions; eseguire:
```bash
python3 -m unittest -q backend.v3.arena.test_compact_market
```
Se i test non passano, correggere **solo il ramo di ricerca**. Non si richiedono dati/crediti provider.

## Problema architetturale da risolvere dopo i test
La procedura delle 575 pagine non deve essere ripetuta a ogni decisione. È necessaria una **cache locale incrementale, atomica e limitata**, che salvi la storia chiusa in un'area dati separata e recuperi poi soltanto le nuove candele chiuse. Occorre confrontare hash, gestire API fallite, orari, exchange rollover, ranking dinamico e uscite di posizioni appartenenti a monete uscite dalla top. Nessuna cache operativa è stata installata finora.

Lo schema degli indicatori comprende EMA20/50/9, ATR e percentile, RSI, MACD, Bollinger, Donchian, ADX, VWAP e regime; viene da Brain L5, non da un algoritmo aggiunto per l'Arena.

## Ambiti da non oltrepassare
- L'universo è **provvisorio**: 23 crypto ranking + XAU/XAG richiedono verifica categorie native/non-native e mapping definitivo cross-provider.
- Falco SHORT: conservare strategia funzionante e preparare backup VPS effettivo prima di eventuale pausa. Toro non toccato; Brain DeepSeek attuale invariato.
- Qwen/MiniMax: chiavi con limiti di 2 USD ciascuna e ricarica 10 USD dichiarata dall'utente; nessuna nuova chiamata API a pagamento da questi file.
- Tre portafogli PAPER da 2000 USDT, rischio deterministico, exits indipendenti, UI e confronto 14 giorni **non ancora avviati**; richiedono prove separate e autorizzazione prima del deploy.
