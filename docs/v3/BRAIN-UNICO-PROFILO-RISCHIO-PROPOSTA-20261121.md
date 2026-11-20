# Brain Unico: proposta del profilo di rischio definitivo (21/11/2026)

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
- **La leva oggi la chiede il modello.** "Leva dinamica" significa calcolarla: la **minima** che dà il rischio pieno entro il tetto di margine. È la più lontana dalla liquidazione e quella con la perdita da gap più contenuta.

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
  - lasciano scegliere la leva dal calcolo;
  - rifiutano i trade dominati dai costi: il filtro sui costi è proposto, vedi sotto;
  - con un gap del 3 % perdono tra l'1 % e il 7 % del capitale.

## Vantaggi e svantaggi
| Profilo | Vantaggi | Svantaggi |
|---|---|---|
| **A Prudente** (0,75 %) | danni minimi negli errori iniziali; 20 perdite piene prima del pavimento; costi ≤ 20 % del rischio | esclude gli stop sotto lo 0,64 % (niente scalp stretto); campioni per l'apprendimento più lenti a pesare in USDT |
| **B Bilanciato** (1 %) | equilibrio tra crescita e sopravvivenza; stop dallo 0,48 %; leva fino a 30× solo quando il calcolo la richiede; giorno peggiore circa −8 % | 4 posizioni da 1 R tutte correlate a BTC equivalgono a una scommessa da 4 R |
| **C Dinamico** (1,5 %) | rendimento più alto se esiste un vantaggio; ammette stop dallo 0,32 % e leva fino a 50× | giorno peggiore circa −12 %; un gap del 3 % con stop allo 0,5 % costa il 7,2 %; senza un vantaggio misurato, accelera soltanto le perdite |

**Raccomandazione per il collaudo PAPER: B Bilanciato.** Il vantaggio del Brain non è ancora misurato fuori campione: la priorità è sopravvivere abbastanza a lungo da misurarlo, con trade abbastanza grandi da essere significativi.

## Valori del profilo B nella configurazione (da approvare; cambia il `policy_hash`, quindi serve un nuovo mandato)
`max_loss_fraction 0.01`, `max_open_risk_fraction 0.04`, `max_position_margin_fraction 0.20`, `max_total_margin_fraction 0.50`, `minimum_equity 1600`, `estimated_roundtrip_cost_bp 16`, `liquidation_buffer_fraction 0.5`, `min_leverage 1`, `max_leverage 30`, `max_loss_margin_fraction 1`, `daily_loss_warn_fraction 0.03`, `daily_loss_halt_fraction 0.04`.

`max_loss_margin_fraction 1` disattiva il vincolo storico. Il vincolo di liquidazione resta sempre più stretto, perché impone leva × (stop + costi) < 0,5.

## Facoltativi: richiedono codice e la tua approvazione
1. **Leva calcolata** al posto di quella chiesta dal modello: la minima che dà il rischio pieno. È consigliata.
2. **Filtro sui costi:** rifiutare se costi > 25 % del rischio. Oggi non esiste, e la tabella lo mostra come proposta.
3. **Tetto nella stessa direzione** per gli 8 simboli correlati a BTC, ad esempio 3 R.
4. **Stop minimo** come multiplo dell'ATR del timeframe d'ingresso.

Nessuno è indispensabile per il collaudo PAPER. Senza il filtro sui costi, gli stop stretti restano ammessi con costi fino al 35 % del rischio.

## Limiti dichiarati
- **Funding:** non è nei 16 bp. A 0,01 % ogni 8 ore su un nozionale di 3.030 USDT costa 0,30 USDT per scadenza, cioè l'1,5 % di R. Va misurato per simbolo.
- **Slippage:** 2 bp è un'ipotesi. Lo slippage reale per simbolo va misurato durante il collaudo.
- **Gap nel PAPER:** il PAPER non tronca la perdita da gap al margine, quindi sui gap è prudente rispetto al margine isolato reale.
- **Rendimenti:** le tabelle sono aritmetica, non previsioni di rendimento.
