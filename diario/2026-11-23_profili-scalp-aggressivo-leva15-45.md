# 2026-11-23 — Profili Scalp Aggressivo PAPER (decisione utente per SVILUPPO)

## Modifiche richieste
- Falco Evoluto: 1.000 USDT PAPER, leva min 15x max 45x, margine min 100 max 250 USDT per operazione.
- Brain Scalp: 2.000 USDT PAPER, leva min 15x max 45x, margine min 250 max 450 USDT per operazione.
- RESTO INVARIATO dal piano precedente: max 4 posizioni, rischio stimato per trade 2% equity, rischio aperto totale 6%, TP 3R, break-even +1R, trailing da +1,5R a distanza 1R; protezione dei profitti, AI DeepSeek sempre Brain e rara su Falco, regole LONG e SHORT, NO_TRADE consentito. Margine totale max 50% equity salvo decisione futura del proprietario.
- NON autorizzato deploy, merge, start servizi, nuova run attiva o modifica di mandati: solo sviluppo configurazioni isolate e test.

## Vincoli da non aggirare
- Con Brain 450 USDT per 45x = 20.250 USDT notional. A budget rischio 2% di 2.000 = 40 USDT, buffer costi stimati 16 bp (se resta questo valore) = 32,40 USDT; resta circa 7,60 USDT per distacco stop pari allo 0,0375% del prezzo. Non è uno stop robusto. Rifiutare operazione se incompatibile con rischio e volatilità.
- Leva minima 15x: non scalare silenziosamente sotto 15x; se non esiste una quota consentita 15-45x, NO_TRADE. Rispettare limiti di leva di ogni simbolo/exchange.
- Margini minimi sono condizionati a rischio, capienza margine totale e liquidazione, non ordini obbligatori. Quattro posizioni al margine massimo eccederebbero il margine totale 50% dell'equity.
- Le 2 posizioni iniziali di Brain RC1 e richiesta di pausa preesistente: non dichiarare la pausa confermata senza verifica live. Non chiudere posizioni del proprietario.

## Continuità
- Ramo Claude falco-evoluto commit a6661a0d: protezione dinamica codificata ma non installata, Falco LONG/analista/AI occasionale e dashboard confronto ancora da sviluppare.
- Aggiornare parametri e test casi estremi, senza toccare produzione e storici.