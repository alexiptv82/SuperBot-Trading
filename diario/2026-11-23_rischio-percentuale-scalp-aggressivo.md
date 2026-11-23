# 2026-11-23 — Ricalcolo percentuale di rischio e profitto per Falco Evoluto + Brain Scalp

## Decisione richiesta e PROPOSTA di ChatGPT (ancora non installata)
- Utente chiede di abbandonare la rappresentazione di perdita fissa in USDT, riparametrando il Risk Manager con percentuali coerenti con leve 15-45x e margini Falco 100-250, Brain 250-450.
- **PROPOSTA da sviluppare e testare, non dichiarata già approvata per trading:** max 4% equity corrente di rischio stimato per trade; max 20% del margine impegnato; max 10% equity corrente di rischio aperto aggregato; stop nuove aperture su perdita giornaliera da valutare a 8% dell'equity di inizio giornata. Fino a 4 posizioni, non obbligatorie.
- Formula del rischio approvabile: `risk_allowed = min(0.04 * equity_current, 0.20 * actual_trade_margin, 0.10 * equity_current - existing_open_risk, equity-floor guard and other limits)`. Tutte le perdite calcolate come stimato al prezzo di stop + commissioni/slippage stimati; non massimi garantiti contro gap, liquidazione o guasti.
- **TP 3R** era parametro precedente: chiarire differenza tra 3 volte distanza stop (lordo/prezzo) e 3 volte rischio net all-in. ChatGPT raccomanda TP obiettivo 3R NETTO con costi, ma questo cambierebbe la semantica delle uscite: richiede patch e test, revisione della probabilità di raggiungere il target. Non dichiararlo già implementato o approvato per deploy.
- Break-even +1R, trailing avvio +1,5R distanza 1R e 24h max restano come da proposta sviluppo. Leva 15-45x, margini specifici, 4 posizioni max, modello e struttura del confronto invariati.
- **Compatibilità**: con Brain 450*45=20.250 notional, buffer 16bp=32,40; budget max rischio 4% su equity iniziale 2.000=80, residuo 47,60 -> stop circa 0,235% prezzo, che può essere troppo stretto per ATR, quindi non forzare. A 45x 250 margine, cap 20% margine=50, costi stimati 18 e stop max 0,284%; nessuna apertura se stop strutturale più largo. Esempio illustrativo non quote corrente.
- Quattro posizioni tutte al 4% non permesse perché cap aggregato 10%; scelta di slot vuoti valida. Controllo correlazione e limiti per exchange.
- Stop giornaliero non garantisce loss massimo: feed e slippage reali possono causare scostamenti; interrompe solo nuove aperture. 8% daily stop è una PROPOSTA da verificare.

## Stato sviluppo
- Branch Claude `claude/falco-evoluto-20261123` commit `a6661a0d`, profit protection runtime con gate test; non deployato.
- Brain RC1 pausa ancora NON verificata con root; non assumere pausa senza prova. Falco storico non riattivato.
- Consegnare a Claude aggiornamento della proposta; modifiche solo in ramo isolato senza start, deploy, merge, mandati.