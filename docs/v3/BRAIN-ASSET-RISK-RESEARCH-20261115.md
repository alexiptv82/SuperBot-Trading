# Brain V3 — Audit del rischio per singolo asset (15/11/2026)

**Stato:** laboratorio offline isolato. **Nessun simbolo disabilitato**, nessun cambio leva/stop/risk gate, nessun deploy/merge o GitHub Actions.

## Evidenza della dashboard alle 20:33 (Europe/Rome)

Schermata fornita dall'operatore, non esportazione del journal. Risultati PAPER netti realizzati, da non confondere con prezzi o PnL latenti.

| Asset | Trade chiusi | Vincenti | PnL netto USDT | Osservazione |
| --- | ---: | ---: | ---: | --- |
| BTCUSDT | 10 | 7 | +515,64 | Contributo maggiore; non prova che sia robusto su altri mercati. |
| LINKUSDT | 3 | 2 | +150,00 | Pochi trade. |
| XRPUSDT | 3 | 2 | +102,69 | Pochi trade. |
| SOLUSDT | 3 | 1 | +24,01 | Rapporto trade/PnL da valutare. |
| ADAUSDT | 2 | 1 | +22,40 | Campione insufficiente. |
| BNBUSDT | 5 | 2 | −97,79 | Watchlist: perdite, ma in recupero rispetto ad audit precedente. |
| ETHUSDT | 5 | 1 | **−292,80** | **Priorita' 1** per diagnosi e confronto con BTC. |

Altri dati coerenti dalla stessa schermata: **31 posizioni chiuse**, 29 SHORT (16 vinte, netto +561,56), 2 LONG (0 vinte, netto −137,42); 16 `take_profit` (+1.629,21) e 15 `stop` (−1.205,07), netto totale **+424,14 USDT**. Commissioni registrate **295,68 USDT**: gia' contenute nel PnL realizzato, **non sottrarle due volte**. Le somme per asset differiscono di 0,01 USDT per arrotondamenti di dashboard.

### Cosa possiamo inferire e cosa NO

- ETH e BNB insieme: **−390,59 USDT**. BTC da solo: **+515,64 USDT**, piu' del profitto netto complessivo. C'e' una concentrazione dei risultati da monitorare.
- Su ETH abbiamo **solo 5 trade**, su BNB **solo 5**. Anche BTC (10) e' un campione limitato: un ban definitivo, un adattamento delle leve, o la riduzione di margine calibrata su questi dati sarebbe **overfitting**.
- Il solo PnL **non dimostra** un eccesso di volatilita': mancano ATR/volatilita' ai tempi di ingresso, rapporto stop/ATR, sequenza MFE/MAE, direction/regime dei singoli trade e confronto a parita' di condizioni.
- Il segnale FRRD separato potra' spiegare se una quota degli SHORT ETH/BNB viene aperta durante `EXPANSION + RIMBALZO_LOCALE`, non sostituisce l'audit per simbolo.

## Laboratorio indipendente

Su branch `work/brain-symbol-risk-research-20261115`:
- `research/brain_asset_risk/audit.py`: legge solo il journal SQLite con `mode=ro` e `PRAGMA query_only=ON`. Collega `paper_open`, `paper_close` e (quando possibile) la `brain_decision` che riporta `regime`; rifiuta eventi incoerenti.
- Per ciascun simbolo: n, win rate, PnL netto e commissioni, profit factor, media R netta stimata, ritorno totale pesato per rischio iniziale, mediana distanza stop (% prezzo), stop/TP, LONG/SHORT, risultati per regime e posizioni ancora aperte.
- Gli open trade non entrano nel PnL chiuso. La mediana dello stop dipende dal prezzo e non misura la volatilita' vera: **serve ancora ATR storico**.
- Non assegna automaticamente simboli da disattivare e non produce modifiche a configurazioni, journal o runner; il campo `symbols_excluded` e' sempre vuoto.
- `test_audit.py`: test sintetici scritti per lettura sola lettura, fee nel PnL netto, mancata contaminazione di run, anomalie, posizioni aperte, nessuna esclusione automatica. **Test non ancora eseguiti su CI o VPS.**

Esempio da una **copia isolata** del journal, non dalla directory operativa:

```bash
python -m pytest -q research/brain_asset_risk/test_audit.py
python -m research.brain_asset_risk.audit --journal /archivio/copia/journal.db --run-id brain-v3-paper20261111
```

L'output e' JSON su terminale; per salvare file scegliere un percorso di ricerca esterno. Non caricare chiavi e dati personali.

## Roadmap decisionale (non policy di trading)

1. **ETH — priorita' alta**: ricostruire le cinque operazioni con posizione direzionale, regime e rapporto **stop/ATR 15m** al momento dell'ingresso; confrontare i risultati con BTC a parita' di regime/volatilita', size, commissioni e timeframe.
2. **BNB — sorveglianza**: stessi controlli, distinguere recupero recente da miglioramento persistente.
3. **Tutti i simboli**: calcolare stop/ATR e MFE/MAE, costo round-trip in bp, tempo fino a TP/SL e cluster di perdite correlate; scoprire se ETH/BNB perdono nei *medesimi* momenti in cui Brain perde in EXPANSION.
4. **Osservazione prospettica** su un campione successivo, prima di scegliere: nessuna modifica, solo un filtro condizionale, o esclusione reversibile del simbolo. Studiare anche quanti trade vincenti sarebbero persi escludendolo.
5. **Mai applicare blacklist o riduzioni della leva automaticamente**: anche con 20 o 30 trade serve verificare stabilita' fuori campione e rischio aggregato di portafoglio.

## Vincoli del progetto

PAPER soltanto. Falco SHORT e Toro LONG indipendenti. Nessun utilizzo di GitHub Actions, deploy, merge, riavvio, reset o modifica dei servizi. Questo file usa solo evidenza della schermata e codice di studio, non dati estratti dalla VPS.
