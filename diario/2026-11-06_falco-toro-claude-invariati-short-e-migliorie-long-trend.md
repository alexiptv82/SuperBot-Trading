# Direttiva definitiva Falco e Toro V3 — Claude invariato, SHORT invariati

Data: 2026-11-06. Conferma esplicita utente: **Falco e Toro NON devono diventare bot esclusivamente meccanici**. Devono continuare a consultare **Claude** come nella versione precedente. Tutta la logica e le capacità SHORT precedenti si conservano: l'utente riferisce che gli SHORT funzionavano bene. Nessun rifacimento, nuovo sizing, nuovi limiti di leva/margine o cambio Risk Manager classici è stato richiesto.

## Uniche migliorie autorizzate rispetto ai classici precedenti
1. **LONG S25** (nuovo segnale orario EMA9/VWAP): integrare in modo additivo, esclusivamente PAPER nella prima nuova run, senza togliere/sostituire SHORT preesistenti; attivazione esplicita dopo i controlli. Non forzare proporzioni LONG/SHORT.
2. **Riconoscimento di possibile cambio trend** a supporto di Claude e delle valutazioni LONG/SHORT. Usare segnale dati/indicatori, non introdurre un veto, inversioni forzate o generazione di trade per raggiungere un numero prefissato di LONG. SHORT continuano quando i dati lo giustificano.

## Riscontro codice PR #62, HEAD b9a611f5fcc7360e7b2085d22e3482575cb7f383
- `backend/desk/cli.py` mantiene `call_claude`, cadenza oraria o revisione scalp urgente, budget/finestre; quando non produce decisioni chiama `rules_decisions`. Non trasformare in rules-only.
- `backend/desk/brain.py` crea il prompt con score LONG/SHORT, trend 4h, trend giornaliero e pattern di possibile inversione. **Questi dati trend preesistenti sono già inviati a Claude**, ma non è dimostrata la presenza di un nuovo evento separato `trend_change`/alert autonomo dedicato.
- `backend/desk/signals.py` genera indicatori trend 1h/4h/1d e pattern hammer, shooting_star, bullish/bearish engulfing. Non cambiare logica SHORT per forzare LONG.
- `backend/desk/long_s25.py` è presente, **OFF** senza `DESK_LONG_S25=1`. È una strategia LONG supplementare: una posizione S25 usa gestione stop, target e max 12h e il modulo `protect` filtra le azioni Claude/regole di CLOSE, PARTIAL_CLOSE e DCA soltanto su **posizioni S25**, non sulle posizioni classiche. Informare l'utente di questa differenza se pertinente; non cambiarla tacitamente.
- I limiti 100USDT max/trade Falco e 350USDT Toro, leva tiers e daily stop dei classici restano come prima: non applicare per errore la policy Brain 20–50x o 12%. Il numero di LONG non è un obiettivo, conta la direzione effettiva del trend.

## Gate e operatività
- PR #62 resta DRAFT, niente merge, deploy, reset o riavvio. Falco/Toro non sono stati aggiornati sulla VPS durante questo chiarimento.
- Non alterare le posizioni storiche PAPER (Falco 6, Toro 2 all'ultimo audit) né archivio; nuove run solo su volumi distinti e dopo verifica backup.
- Il task immediato prima del go-live è verificare che il segnale **cambio trend** si presenti realmente a Claude nel modo previsto e che la funzione S25 venga abilitata solo nella run PAPER approvata. Non introdurre nuove strategie o cambiare i LONG/SHORT scores base senza richiesta.

**Obiettivo dell'utente:** preservare ciò che funzionava — soprattutto SHORT e consultazione Claude — aggiungendo soltanto più sensibilità ai cambi di trend e un'ulteriore opportunità LONG coerente con il mercato.