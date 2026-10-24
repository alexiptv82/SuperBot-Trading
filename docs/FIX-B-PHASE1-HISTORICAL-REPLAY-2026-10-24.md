# Fix B – Fase 1. Replay storico osservazionale (10–23 ottobre 2026 UTC)

**Data esecuzione:** 24 ottobre 2026. **Esecuzione:** sola lettura, branch `work/fix-b-profit-guardian`. **Nessun ordine, chiamata Claude/DeepSeek, merge, deploy o modifica ai dati PAPER.**

**Fonte verificabile:** [GitHub Actions run 40099527699](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40099527699); script `deploy/scripts/fix_b_historical_replay_v1.py`. Dati letti direttamente sul VPS da `/opt/superbot-desk-data/{hawk,bull}/learning_log.jsonl`, `trade_history.jsonl` e `/opt/superbot-sidecar-data/{hawk,bull}/events-*.jsonl`. Periodo di **14 giorni UTC completi**, chiusure finali tra 10/10 00:00 e 24/10 00:00 UTC.

## Risultati verificati

| Metrica | Hawk | Bull | Totale |
|---|---:|---:|---:|
| Trade chiusi ricostruiti | 155 | 49 | 204 |
| Trade con osservazioni storiche sidecar | 43 | 19 | 62 |
| ROI netto >=20% **osservato prima della chiusura** | 13 | 7 | 20 |
| Di questi, giveback rispetto a uno snapshot netto migliore | 7 | 4 | 11 |
| Di questi, risultato finale ROI sotto 20% | 5 | 3 | 8 |
| Di questi, **TP originale successivamente raggiunto** | 6 | 3 | 9 |
| Giveback rispetto al massimo netto **osservato**, non eseguibile per definizione | +305,27 $ | +219,50 $ | +524,77 $ |
| Massimo MFE lordo teorico compatibile con >=20% (NON conferma di ROI netto) | 87 | 26 | 113 |
| Trade con ROI finale >=20% (NON prova di checkpoint anticipato) | 57 | 17 | 74 |

Quattro ulteriori trade storici (2 Hawk, 2 Bull) sono esclusi dalla ricostruzione perché non possiedono un evento OPEN univoco nei registri, senza inventarne il contesto. `learning_log` e `trade_history` concordano sul totale dei P&L registrati nell'intervallo per ciascun bot: Hawk **+548,29 $**, Bull **+653,56 $**. Questi P&L NON includono il non-realizzato delle posizioni aperte.

Gli snapshot periodici esistono **solo dal 19 ottobre**. Per 142 dei 204 trade ricostruiti non è disponibile una traiettoria di ROI netto pre-chiusura sufficiente. I 20 checkpoint sono un **minimo osservato e non una stima del totale effettivo**.

## Benchmark controfattuale LIMITATO (non una decisione di Claude)

Su tutti i 20 trade con checkpoint osservato:
- **Risultato finale effettivo**: +486,25 $ netti.
- **Valore stimato da uscita prudente al PRIMO snapshot con ROI>=20%**: +623,83 $.
- **Differenza aritmetica**: +137,58 $ (non fill eseguito, non previsione di Fix B; il prossimo prezzo potrebbe divergere e Claude potrebbe scegliere HOLD_TP o parziale).

Sottogruppo **13 trade senza parziali, DCA e split**:
- Chiusura immediata teorica al primo checkpoint avrebbe migliorato **4** trade, peggiorato **9**; il risultato combinato stimato rispetto alle chiusure reali sarebbe +78,85 $.
- Tra i peggioramenti, **8** riguardavano posizioni che hanno raggiunto successivamente il take profit.
- Un benchmark di chiusura 50% **senza stop sul residuo** darebbe una differenza aritmetica +39,43 $: **non è il protocollo TAKE_PARTIAL autorizzato**, per il quale occorrono storico stop e fill della barra successiva.

**Non esiste una stima certificabile del profitto che Fix B avrebbe veramente protetto.** I +524,77 $ sono giveback *ex post* dal migliore snapshot al netto effettivo: non è il profitto che la strategia avrebbe necessariamente incassato.

## I 20 checkpoint verificabili

La colonna “stop & fill” è sconosciuta: la stima prudente non corrisponde a un ordine realmente eseguibile. **La colonna Δ vale solo per trade semplici** e indica l'effetto ipotetico di CLOSE_FULL immediato al primo checkpoint rispetto alla chiusura reale.

| Bot | Simbolo | Primo checkpoint (UTC) | Max ROI osservato | Netto reale | Uscita prudente stimata al 20% | Δ teorico full (solo semplice) | TP successivo |
|---|---|---|---:|---:|---:|---:|---|
| Hawk | STX | 2026-10-20 10:36 | 57.8% | +70,65 $ | +38,11 $ | -32,54 $ | TP |
| Hawk | NEAR | 2026-10-20 10:52 | 32.3% | -101,50 $ | +21,22 $ | +122,72 $ | — |
| Hawk | OP | 2026-10-22 06:06 | 23.2% | +23,17 $ | +22,33 $ | -0,84 $ | — |
| Hawk | ARB | 2026-10-22 08:43 | 33.3% | -61,00 $ | +29,85 $ | +90,85 $ | — |
| Hawk | AVAX | 2026-10-22 08:12 | 43.1% | +48,47 $ | +36,54 $ | -11,93 $ | TP |
| Hawk | STX | 2026-10-22 08:12 | 75.4% | +80,93 $ | +35,94 $ | -44,99 $ | TP |
| Hawk | OP | 2026-10-22 08:43 | 68.2% | +61,45 $ | +20,80 $ | -40,65 $ | TP |
| Hawk | LINK | 2026-10-22 16:50 | 29.1% | +35,49 $ | +28,13 $ | -7,36 $ | TP |
| Hawk | ETH | 2026-10-22 16:50 | 24.0% | +24,83 $ | +22,99 $ | -1,84 $ | TP |
| Hawk | UNI | 2026-10-22 16:34 | 47.1% | +21,82 $ | +26,04 $ | n.c. (parziali/DCA/split) | — |
| Hawk | SUI | 2026-10-22 16:50 | 31.9% | +17,44 $ | +30,94 $ | n.c. (parziali/DCA/split) | — |
| Hawk | DOT | 2026-10-22 08:12 | 24.6% | +4,87 $ | +23,77 $ | n.c. (parziali/DCA/split) | — |
| Hawk | SOL | 2026-10-22 20:38 | 26.1% | +3,49 $ | +13,85 $ | +10,36 $ | — |
| Bull | OP | 2026-10-22 03:20 | 33.3% | +54,52 $ | +38,01 $ | n.c. (parziali/DCA/split) | TP |
| Bull | AVAX | 2026-10-22 08:10 | 39.5% | +70,86 $ | +54,42 $ | -16,44 $ | TP |
| Bull | OP | 2026-10-22 13:15 | 53.1% | +99,55 $ | +31,44 $ | -68,11 $ | TP |
| Bull | ARB | 2026-10-22 06:24 | 51.2% | +60,67 $ | +37,51 $ | n.c. (parziali/DCA/split) | — |
| Bull | UNI | 2026-10-22 16:33 | 44.1% | +23,61 $ | +46,09 $ | n.c. (parziali/DCA/split) | — |
| Bull | DOT | 2026-10-22 07:09 | 37.5% | -7,44 $ | +31,83 $ | n.c. (parziali/DCA/split) | — |
| Bull | ADA | 2026-10-22 20:51 | 21.9% | -45,63 $ | +34,02 $ | +79,65 $ | — |

## Claude, alert e attendibilità

- **Claude operativo Fix B:** non invocato storicamente su questi snapshot; **CLOSE_FULL / TAKE_PARTIAL / HOLD_TP per singolo trade non sono recuperabili come decisioni reali**. Non vanno sostituite con classificazioni dedotte dall'esito futuro (look-ahead).
- **DeepSeek:** architettura shadow invariata, nessuna chiamata né promozione di un co-decisore.
- **Portfolio Trend Alert:** non valutabile storicamente con certezza dai due file di trade e dagli snapshot disponibili, perché occorrono contemporaneamente barre OHLCV 1h *chiuse* per tutte le SHORT e BTC/ETH, serie EMA20/EMA50, RSI e volume degli stessi timestamp. **Non assumere alert=false**.
- Per un replay esecutivo attendibile servono OHLC 15m/1h storiche validate con completezza e data di chiusura, reconstituzione cronologica delle modifiche DCA/split/parziali, eventuali gap, fill della barra successiva, costi/funding al tempo dell'ordine; in più chiamate Claude su prompt *as-of* (esplicitamente autorizzate e costate nel budget) o etichette di riferimento chiaramente non-Claude.
- L'esito suggerisce che **chiudere tutte le posizioni al 20% non è corretto**: almeno 9 trade su 20 hanno raggiunto un successivo take profit.

## Sicurezza

I workflow si avviano solo tramite trigger sul branch di ricerca. Sono in sola lettura sul VPS e non usano segreti AI o exchange. Nessuna modifica a `rule-pool`, `main`, `profit_guardian.py`, `portfolio_alert.py` o ai container. Capital V1 rimane OFF. Prima di ogni attivazione serve esplicito OK utente.
