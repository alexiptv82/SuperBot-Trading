# SuperBot — Toro LONG Mirror 15m, fase ricerca isolata

**Data:** 13 novembre 2026  
**Base immutabile:** `f8332c92cc2bc4edee3ea7363f71f15a0a37a816` (Fase 3 Falco SHORT_ONLY).  
**Ramo isolato:** `work/toro-long-mirror-15m-20261113`.  
**STATO: STUDIO OFFLINE / SOLO SEGNALI, NON una strategia eseguibile.**  
Nessun collegamento a `cli.run_cycle`, `PaperAccount`, unit systemd, API di trading o servizi Brain.

## Direttiva dell'utente

- **Falco:** soltanto SHORT in PAPER (flag SHORT_ONLY già approvato tecnicamente, non attivato), con
  strategia SHORT originale rigorosamente congelata e nessuna modifica ai suoi parametri, scoring,
  entrate, uscite, ordini, leva, stop/TP o cadenza.
- **Toro:** proposta futura LONG_ONLY, 5 slot, max 200 USDT per apertura, 1.000 USDT PAPER,
  alta leva da **valutare**, non da abilitare ora. Deve riconoscere sia i rialzi strutturali sia
  i **rimbalzi** su candele di 15m.
- **Brain:** continua LONG/SHORT/NO_TRADE in maniera autonoma, codice inalterato.
- Nuove aperture LONG su Toro non devono essere attivate prima di backtest/replay, taratura
  del rischio, revisione indipendente e approvazione esplicita.

## Origine esatta della strategia SHORT, verificata nel codice

File approvati e **immutabili** durante questo studio:
`backend/desk/brain.py`, `backend/desk/signals.py`, `backend/desk/cli.py`,
`backend/desk/engine.py`; le SHA Git blob congelate sono verificate nel test
`backend/tests/test_toro_short_immutable.py` (il test NON è stato ancora eseguito nell'intero repository).

Lo scoring esistente in `signals.read_symbol` è già per lato LONG/SHORT:
- Trend EMA50/200 4H nativo: 20 punti lato di trend; UNKNOWN non autorizza aperture.
- EMA20/50 1H: 15 punti al lato concorde.
- Chiusura 1H vs EMA50: 8 punti al lato concorde.
- ROC 24H: fino a 12 punti sul segno del momentum.
- Breakout massimo/minimo precedente: 10 punti.
- RSI 1H: 8 punti nella fascia direzionale.
- Volume forte + candela concorde: 4 punti.
- Pattern hammer/bullish engulfing o shooting star/bearish engulfing: 8 punti.
- Penalità doji, RSI estremo; bonus stagionale (fino a 15) già presente nel motore originale.
- ATR e SL/TP nel motore originale NON vengono modificati.

`brain.rules_decisions` usa il punteggio/lato fornito da `read_symbol`; un'apertura
dipende anche da soglie, cooldown, claim, pausa, trend 4H verificabile e limiti del conto.
**Il successo storico degli SHORT non dimostra il successo di un algoritmo inverso.**

## Prototipo LONG speculare su 15 minuti

`backend/desk/long_mirror_15m.py` è un modulo **puro** che non chiama servizi, non registra
ordini, non imposta margini, TP, stop, leva o uscite. Esamina esclusivamente candele
**15m chiuse**, ordinate, coerenti e continue, e uno stato di trend 4H già verificato.

Riproduce in lettura i pesi direzionali principali degli SHORT in forma LONG: 4H 20, EMA20/50 15,
prezzo/EMA50 8, momentum 24H 12, breakout 10, RSI 8, volume 4, pattern 8; RSI estremo
e doji penalizzano. Il pilot NON riproduce il bonus stagionale e **non è una copia identica**
del comportamento SHORT: usa il timeframe 15m invece di 1H e conferma due candele verdi CHIUSE,
EMA20 crescente e chiusura sopra EMA20. I pesi e i parametri del motore originale non cambiano.

Risultati possibili:
- `LONG_CONTINUATION_CANDIDATE`: trend 4H UP, segnali LONG 15m e punteggio di studio >=60.
- `LONG_BOUNCE_CANDIDATE`: trend 4H DOWN ma rimbalzo 15m con volume, RSI e conferme
  aggiuntive. **È una ipotesi controtrend, NON la prova di inversione della tendenza.**
- `NO_TRADE`: mancano dati, il trend 4H è UNKNOWN, serie non integra, candela incompleta,
  segnali insufficienti o calendario metalli non verificato.

**Tutti i risultati sono etichette di studio.** Nemmeno un `LONG_*_CANDIDATE`
autorizza ordini. Nessun TP/SL/R:R viene suggerito prima di validazione indipendente.

## Evidenze attuali

Test locali isolati del nuovo modulo (NumPy/Pytest): **13/13 PASS** nel laboratorio di
questa sessione. Sono stati provati: trend UP -> candidato LONG, trend DOWN -> candidato
rimbalzo, UNKNOWN -> NO_TRADE, barre future/incomplete ignorate, storia insufficiente,
duplicati identici vs conflittuali, dati vecchi, OHLCV incoerente, due candele rosse,
nessuna istruzione di esecuzione.

**Non sono stati eseguiti**: suite completa del repository, test fingerprint contro
checkout GitHub, replay su Bitget/storico reale, valutazione di commissioni/slippage/funding,
test reale delle uscite e del ciclo di Toro. Nessuna CI GitHub Actions.

## Decisioni future, non autorizzate/implementate

1. Backtest comparativo su dati 15m crypto reali, spezzati per trend UP/DOWN/laterale.
   Calcolare costi round-trip, holding, frequenza, PnL netto, MAE/MFE, drawdown,
   falsi segnali e overfitting. Separare `CONTINUATION` vs `BOUNCE`.
2. Verificare segnali a fronte di chiusure 15m e presenza di stop/protezione
   contemporaneamente. **Il ciclo attuale è 30m normalmente, 15m se scalp aperto,
   e non è sincronizzato alla chiusura delle candele**. Non aumentare la frequenza
   del runner globale senza misurare costo API e senza alterare Falco.
3. Progettare una modalità PAPER `LONG_ONLY` per Toro che non blocchi le uscite di
   eventuali SHORT preesistenti e che impedisca DCA/split SHORT residui.
4. Passare Toro da 3 slot × 350 a **5 slot × max 200** e correggere eventuale incoerenza
   di prompt/guardrail in **Toro soltanto**. Rischio e equity floor 450 invariati finché
   l'utente non approva il piano; cinque slot da 200 non significa cinque ingressi forzati.
5. Leva 20–50x **non implementata**: limiti correnti in engine BTC/XAU/XAG 45x,
   ETH 30x, altre 25x; i TP scalp molto stretti rischiano di non coprire le fee.
   Non modificare le protezioni degli SHORT.
6. Calendario XAU/XAG non verificato: nel prototipo, NO_TRADE sui metalli.
7. Mantenere S25 inattiva per nuove aperture. Brain totalmente separato.
8. Audit esplicito dei rischi `POLICY_SHADOW`: TP assente, R:R, leva/margine forzati.
9. Revisione indipendente della modalità LONG + PASS dei test; poi autorizzazione
   separata per qualunque collegamento al runner o modifica VPS.

### Comandi per collaudo locale (da eseguire nel checkout del ramo)

```sh
PYTHONPATH=backend python3 -m pytest -q backend/tests/test_toro_long_mirror_15m.py backend/tests/test_toro_short_immutable.py
# test funzionali a regression:
PYTHONPATH=.:backend python3 -m pytest -q backend/tests/test_desk_rc84_phase3_short_only.py backend/tests/test_desk_rc84_phase3_collaudo.py
```

**PORTO SICURO:** branch Fase3 `work/rc84-phase3-falco-short-only-20261112` /
`f8332c92...`, branch Fase2 frozen `dc98413...`, RC84 VPS `ab7e0b7...` e
i backup restano invariati. Nessun merge, deploy, unpause, reset o ordine LIVE.
