# Brain Unico: proposta del profilo di rischio definitivo (21/11/2026)

> **Decisione del proprietario (21/11/2026):** profilo **B Bilanciato** come riferimento del primo collaudo PAPER (2.000 USDT):
> - rischio per operazione 1 %;
> - massimo 4 posizioni e 4 % di rischio aperto;
> - limite giornaliero: avviso al 3 %, stop alle nuove aperture al 4 %;
> - pavimento di capitale 1.600 USDT;
> - leva consentita 1–30×.
>
> Il mandato **non** è ancora applicato. La leva minima calcolata e il filtro sui costi **non** sono operativi.

**Natura:** proposta per la decisione del proprietario. Nessun parametro operativo è cambiato.
**Riferimento:** capitale PAPER di 2.000 USDT, futures USDT-M Bitget.
**Costi della configurazione:**
- commissione 0,06 % per lato;
- slippage 0,02 % per lato;
- totale andata e ritorno 0,16 %.

**Verificabilità:** i numeri vengono da `ops/brain-unico/risk/profiles.py`, che usa solo aritmetica. Il test `backend/tests/test_v3_risk_profiles_lab.py` verifica che ogni riga coincida con il RiskManager reale (`quote_paper_risk`). Tutti e tre i profili sono esprimibili nella configurazione del runner **senza codice nuovo** (verificato con `load_runner_config`). Le soglie storiche del 35 % e del 50 % **non** sono approvate.

## Come funziona oggi il calcolo (RiskManager)
- **Perdita allo stop** = rischio scelto. La leva non la cambia, e i costi sono già inclusi.
- **Quantità** = minimo tra quella data dal rischio e quella data dal tetto di margine × leva. Con leva bassa il margine **riduce** la size, quindi il rischio effettivo scende sotto quello scelto. Non è un rifiuto.
- **Rifiuti legati alla leva richiesta:**
  - stop oltre metà della distanza di liquidazione;
  - rapporto perdita/margine (oggi 21,4 %).
- **Leva: cosa è operativo oggi** (`brain_f2/engine.py`, con il profilo di leva attivo):
  1. il motore parte dalla leva **proposta dal modello**, limitata all'intervallo del profilo (1–30× per B) e al limite dell'exchange;
  2. se è troppo vicina alla liquidazione, **scende automaticamente** di un passo alla volta fino a 1×, e la decisione registra `risk:leverage_adjusted`;
  3. **non sale mai**: se la leva proposta è bassa e il tetto di margine limita la size, il rischio effettivo resta **sotto** l'1 %, sempre nella direzione prudente.

  In nessun caso la perdita allo stop supera il rischio scelto.
- **Non operativo:** la scelta automatica della leva **minima che dà il rischio pieno**. Le colonne "Leva" delle tabelle mostrano quel calcolo **ipotetico**, per confrontare i profili, non la leva che il runtime userà.

## Le alternative
| Profilo | Rischio/trade | Posizioni max | Rischio aperto | Margine pos./tot. | Leva | Stop minimo (costi) | Giorno: avviso / stop | Giorno peggiore* | Pavimento | Perdite piene fino al pavimento |
|---|---|---|---|---|---|---|---|---|---|---|
| Storico (non approvato) | 4.29 % (86 USDT) | 3 | 12 % | 20 % / 55 % | 20–50× | nessuno | 35.0 % / 50.0 % (11.7 R) | 62.0 % | 450 (−77.5 %) | 18.1 |
| A Prudente | 0.75 % (15 USDT) | 4 | 3 % | 20 % / 40 % | 1–20× | 0.64 % | 2.0 % / 3.0 % (4.0 R) | 6.0 % | 1700 (−15.0 %) | 20.0 |
| B Bilanciato | 1.00 % (20 USDT) | 4 | 4 % | 20 % / 50 % | 1–30× | 0.48 % | 3.0 % / 4.0 % (4.0 R) | 8.0 % | 1600 (−20.0 %) | 20.0 |
| C Dinamico | 1.50 % (30 USDT) | 4 | 6 % | 20 % / 55 % | 1–50× | 0.32 % | 4.5 % / 6.0 % (4.0 R) | 12.0 % | 1500 (−25.0 %) | 16.7 |

| Profilo | Stop | Leva | Nozionale | Margine | Rischio effettivo | Distanza liquidazione | Costi/rischio | Pareggio con TP 2R | Gap 3 % (PAPER) | Esito |
|---|---|---|---|---|---|---|---|---|---|---|
| Storico (non approvato) | 0.3 % | 46× | 18400 | 400 | 85 USDT (ridotto dal margine) | 1.51 % | 35 % | 51.1 % | 581 (29.1 %) | ammesso, rischio ridotto |
| Storico (non approvato) | 0.5 % | 32× | 12800 | 400 | 84 USDT (ridotto dal margine) | 2.46 % | 24 % | 44.0 % | 404 (20.2 %) | ammesso, rischio ridotto |
| Storico (non approvato) | 1.0 % | — | — | — | — | — | 14 % | 38.7 % | — | rifiutato: perdita/margine 21,4 % |
| Storico (non approvato) | 2.0 % | — | — | — | — | — | 7 % | 36.0 % | — | rifiutato: perdita/margine 21,4 % |
| A Prudente | 0.3 % | — | — | — | — | — | 35 % | 51.1 % | — | rifiutato: costi (filtro proposto) |
| A Prudente | 0.5 % | — | — | — | — | — | 24 % | 44.0 % | — | rifiutato: costi (filtro proposto) |
| A Prudente | 1.0 % | 4× | 1293 | 323 | 15 USDT | 24.34 % | 14 % | 38.7 % | 41 (2.0 %) | ammesso |
| A Prudente | 2.0 % | 2× | 694 | 347 | 15 USDT | 49.34 % | 7 % | 36.0 % | 22 (1.1 %) | ammesso |
| B Bilanciato | 0.3 % | — | — | — | — | — | 35 % | 51.1 % | — | rifiutato: costi (filtro proposto) |
| B Bilanciato | 0.5 % | 8× | 3030 | 379 | 20 USDT | 11.84 % | 24 % | 44.0 % | 96 (4.8 %) | ammesso |
| B Bilanciato | 1.0 % | 5× | 1724 | 345 | 20 USDT | 19.34 % | 14 % | 38.7 % | 54 (2.7 %) | ammesso |
| B Bilanciato | 2.0 % | 3× | 926 | 309 | 20 USDT | 32.67 % | 7 % | 36.0 % | 29 (1.5 %) | ammesso |
| C Dinamico | 0.3 % | — | — | — | — | — | 35 % | 51.1 % | — | rifiutato: costi (filtro proposto) |
| C Dinamico | 0.5 % | 12× | 4545 | 379 | 30 USDT | 7.67 % | 24 % | 44.0 % | 144 (7.2 %) | ammesso |
| C Dinamico | 1.0 % | 7× | 2586 | 369 | 30 USDT | 13.63 % | 14 % | 38.7 % | 82 (4.1 %) | ammesso |
| C Dinamico | 2.0 % | 4× | 1389 | 347 | 30 USDT | 24.34 % | 7 % | 36.0 % | 44 (2.2 %) | ammesso |

*Giorno peggiore = soglia di stop alle aperture + rischio delle posizioni ancora aperte (che proseguono fino al loro stop), senza gap.

**Lettura delle tabelle:**
- **Profilo storico:**
  - rischia il 4,3 % per trade;
  - si ferma solo dopo 11,7 perdite piene in un giorno;
  - ha il pavimento a −77,5 %;
  - con il vincolo perdita/margine rifiuta gli stop dall'1 % in su, cioè proprio quelli fuori dal rumore;
  - un gap del 3 % con stop allo 0,5 % costa il 20 % del capitale.
- **Profili A, B e C:**
  - limitano la giornata a 4 perdite piene;
  - ammettono la leva da 1×, così gli stop larghi non vengono più rifiutati;
  - rifiutano i trade dominati dai costi: il filtro sui costi è proposto, vedi sotto;
  - con un gap del 3 % perdono tra l'1 % e il 7 % del capitale.

## Vantaggi e svantaggi
| Profilo | Vantaggi | Svantaggi |
|---|---|---|
| **A Prudente** (0,75 %) | danni minimi negli errori iniziali; 20 perdite piene prima del pavimento; costi ≤ 20 % del rischio | esclude gli stop sotto lo 0,64 % (niente scalp stretto); campioni per l'apprendimento più lenti a pesare in USDT |
| **B Bilanciato** (1 %) | equilibrio tra crescita e sopravvivenza; leva consentita 1–30×, abbassata dal motore se troppo vicina alla liquidazione; giorno peggiore circa −8 % | 4 posizioni da 1 R tutte correlate a BTC equivalgono a una scommessa da 4 R |
| **C Dinamico** (1,5 %) | rendimento più alto se esiste un vantaggio; ammette stop dallo 0,32 % e leva fino a 50× | giorno peggiore circa −12 %; un gap del 3 % con stop allo 0,5 % costa il 7,2 %; senza un vantaggio misurato, accelera soltanto le perdite |

**Raccomandazione per il collaudo PAPER: B Bilanciato.** Il vantaggio del Brain non è ancora misurato fuori campione: la priorità è sopravvivere abbastanza a lungo da misurarlo, con trade abbastanza grandi da essere significativi.

## Valori del profilo B nella configurazione (da approvare; cambia il `policy_hash`, quindi serve un nuovo mandato)
`max_loss_fraction 0.01`, `max_open_risk_fraction 0.04`, `max_position_margin_fraction 0.20`, `max_total_margin_fraction 0.50`, `minimum_equity 1600`, `estimated_roundtrip_cost_bp 16`, `liquidation_buffer_fraction 0.5`, `min_leverage 1`, `max_leverage 30`, `max_loss_margin_fraction 1`, `daily_loss_warn_fraction 0.03`, `daily_loss_halt_fraction 0.04`.

`max_loss_margin_fraction 1` disattiva il vincolo storico. Il vincolo di liquidazione resta sempre più stretto, perché impone leva × (stop + costi) < 0,5.

## Facoltativi: richiedono codice e la tua approvazione (nessuno nel primo PAPER)
1. **Leva minima per il rischio pieno, calcolata:** non implementata. Nel primo PAPER resta il comportamento sopra: proposta del modello, abbassata se insicura.
2. **Filtro sui costi (> 25 % del rischio): fuori dal primo PAPER.** Il motivo è nella sezione successiva.
3. **Tetto nella stessa direzione** per gli 8 simboli correlati a BTC, ad esempio 3 R.
4. **Stop minimo** come multiplo dell'ATR del timeframe d'ingresso.

## Filtro sui costi: decisione proposta (minima)
**Raccomandazione:** tenerlo **fuori** dal primo PAPER e **misurarlo**.

**Perché non è una protezione essenziale del capitale.** Il RiskManager include già i costi stimati (16 bp) nella perdita allo stop. Un trade con stop stretto perde quindi al massimo l'1 % come ogni altro, e limite giornaliero e pavimento restano intatti. Il filtro migliora l'**aspettativa**, non la sopravvivenza: con stop allo 0,3 % serve il 51 % di vincite per andare in pari, contro il 39 % con stop all'1 %.

**Perché non introdurlo adesso:**
- rifiutare trade proposti dal modello cambia il comportamento della strategia, e richiede una tua decisione esplicita;
- serve un nuovo campo nella politica di rischio, quindi cambiano schema, configurazione e mandato, con test dedicati: è un ciclo di sviluppo;
- la soglia del 25 % non è misurata sui nostri dati.

**Cosa si fa invece, senza codice:**
- **Misura nel collaudo:** quota delle aperture con costi > 25 % del rischio, e loro esito netto. Si calcola dal journal: l'evento `paper_open` registra prezzo d'ingresso, stop, leva e nozionale, e i costi stimati (16 bp) vengono dalla configurazione della run. Le leve abbassate dal motore sono registrate come `risk:leverage_adjusted` nelle fonti della decisione.
- **Decisione dopo il collaudo:** se le aperture con costi oltre il 25 % risultano in perdita netta fuori campione, il filtro si introduce con test mirati, come modifica approvata.

## Limiti dichiarati
- **Funding:** non è nei 16 bp. A 0,01 % ogni 8 ore su un nozionale di 3.030 USDT costa 0,30 USDT per scadenza, cioè l'1,5 % di R. Va misurato per simbolo.
- **Slippage:** 2 bp è un'ipotesi. Lo slippage reale per simbolo va misurato durante il collaudo.
- **Gap nel PAPER:** il PAPER non tronca la perdita da gap al margine, quindi sui gap è prudente rispetto al margine isolato reale.
- **Rendimenti:** le tabelle sono aritmetica, non previsioni di rendimento.
