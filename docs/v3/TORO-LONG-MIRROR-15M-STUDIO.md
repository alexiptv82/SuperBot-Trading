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
`backend/tests/test_toro_short_immutable.py` (eseguito nel collaudo, vedi sotto).

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

## Evidenze della prima sessione (13 test sintetici, superate dal collaudo sotto)

Test locali isolati del nuovo modulo (NumPy/Pytest): **13/13 PASS** nel laboratorio di
questa sessione. Sono stati provati: trend UP -> candidato LONG, trend DOWN -> candidato
rimbalzo, UNKNOWN -> NO_TRADE, barre future/incomplete ignorate, storia insufficiente,
duplicati identici vs conflittuali, dati vecchi, OHLCV incoerente, due candele rosse,
nessuna istruzione di esecuzione.

**Non sono stati eseguiti**: suite completa del repository, test fingerprint contro
checkout GitHub, replay su Bitget/storico reale, valutazione di commissioni/slippage/funding,
test reale delle uscite e del ciclo di Toro. Nessuna CI GitHub Actions.

## Collaudo del 13 novembre 2026 (seconda sessione, sul commit `3818c0e`)

### 1. Inversione dei criteri: cosa è speculare e cosa è ipotesi nuova

Confronto riga per riga con `signals.read_symbol` e `signals.doji_pattern` (file congelati, invariati):

| Criterio SHORT originale | Specchio LONG nel prototipo | Esito |
|---|---|---|
| trend 4h DOWN (EMA50<EMA200, barre 4h chiuse) 20 p. | trend 4h UP 20 p.; UNKNOWN = NO_TRADE | speculare (trend fornito dal chiamante) |
| EMA20<EMA50 **1h** 15 p. | EMA20>EMA50 **15m** 15 p. | peso speculare, **timeframe nuovo** (finestra 5 h/12,5 h invece di 20 h/50 h) |
| chiusura < EMA50 **1h** 8 p. | chiusura > EMA50 **15m** 8 p. | peso speculare, timeframe nuovo |
| ROC 24 h < 0, fino a 12 p. (soglia 3%) | ROC 24 h > 0, fino a 12 p. (96 barre 15m = 24 h) | speculare |
| rottura minimi **20 h** 10 p. | rottura massimi **20 barre 15m = 5 h** 10 p. | peso speculare, **finestra 4 volte più corta** |
| RSI(14) **1h** 30–50 8 p.; RSI<22 −12 | RSI(14) **15m** 50–70 8 p.; RSI>78 −12 | speculare, timeframe nuovo (RSI su 3,5 h) |
| volume >1,3× media 24 h + candela rossa 4 p. | volume >1,3× media 6 h + candela verde 4 p. | peso speculare, **media su 24 barre 15m = 6 h** invece di 24 h |
| shooting star / bearish engulfing 8 p.; doji −5 | hammer / bullish engulfing 8 p.; doji −5 | speculare (ordine di classificazione corretto in questo collaudo, vedi D1) |
| stagionalità fino a 15 p. | assente | differenza dichiarata |
| lato = punteggio più alto fra LONG e SHORT | **nessun confronto con il punteggio SHORT** | ipotesi nuova: un LONG può risultare candidato anche se lo SHORT speculare avrebbe un punteggio più alto |
| — | due candele 15m verdi chiuse, EMA20 15m crescente, chiusura > EMA20 | conferme nuove (non esistono nell'originale) |
| soglia di ingresso in `brain.rules_decisions` | CONTINUATION: 4h UP e punteggio ≥ 60 | soglia nuova del prototipo |
| — | BOUNCE: 4h DOWN, volume >1,3, RSI 40–72, punteggio ≥ 30 | **ipotesi interamente nuova** (controtrend) |
| SL 1,2×ATR 1h (0,3%–3,5%), TP 1,8×SL | nessuna uscita nel prototipo | le uscite sono solo un'ipotesi del replay |

L'inversione dei segni è corretta per tutti gli otto criteri pesati. Le parti realmente speculari sono pesi, segni e
soglie; il timeframe 15m, le finestre accorciate, le conferme, le soglie 60/30, l'assenza del confronto con lo SHORT e
tutta la categoria BOUNCE sono **ipotesi sperimentali** e vanno validate come tali.

### 2. Difetti trovati e corretti (solo file nuovi)

- **D1 — pattern, precedenza diversa dall'originale.** `doji_pattern` controlla la *shooting star* prima
  dell'*engulfing*; il prototipo non la controllava, quindi una candela che l'originale legge come shooting star
  (segnale SHORT) riceveva +8 punti LONG come bullish engulfing. Corretto: la classificazione segue lo stesso ordine
  e la shooting star non dà punti LONG. Test `test_shooting_star_keeps_the_original_precedence_and_earns_no_long_points`
  (fallisce sul codice di `3818c0e`, passa dopo la correzione).
- **D2 — test della continuità che non provava la continuità.** `test_missing_recent_bar_never_approves_a_long`
  usa 110 barre: togliendone una, il rifiuto arriva per "storia insufficiente" e il controllo dei buchi non viene mai
  raggiunto. Aggiunto `test_gap_inside_the_used_window_is_rejected_even_with_long_history` (200 barre, buco recente →
  `storia_15m_interrotta`).
- Aggiunto `test_no_future_information_reaches_a_past_decision`: per tre istanti la decisione calcolata con le sole
  barre fino a *t* coincide con quella calcolata passando anche tutte le barre successive.

### 3. Verifiche senza difetti

Candela in formazione con prezzo anomalo o NaN: ignorata. Barra con data futura: ignorata. Righe in ordine casuale:
stessa decisione. Duplicati identici: innocui; duplicati in conflitto: NO_TRADE. Buco nelle ultime 110 barre:
NO_TRADE; buco più vecchio della finestra: non influisce. Dati vecchi di oltre una barra: NO_TRADE. OHLC incoerenti
anche fuori finestra: NO_TRADE (prudente). Metalli: NO_TRADE. Volume tutto a zero: nessun punto volume, nessun errore.
Identità dei quattro file del motore SHORT (`brain.py`, `signals.py`, `cli.py`, `engine.py`): blob Git identici a
`f8332c9` (verificati sia dal test sia con `git hash-object` sui due checkout). Nessun modulo esistente importa il
prototipo: non è collegato a `run_cycle`, `PaperAccount`, Claude o Brain.

**Limiti di interfaccia da risolvere prima di qualunque collegamento:** lo stato del trend 4h arriva come stringa
senza istante di riferimento (il chiamante deve garantire che sia aggiornato); EMA50 calcolata su sole 110 barre
(il peso residuo del primo valore è circa 1,4%); il runner attuale non è sincronizzato con la chiusura delle candele 15m.

### 4. Test eseguiti (laboratorio locale, nessuna GitHub Actions)

- Studio: `test_toro_long_mirror_15m.py` + `test_toro_short_immutable.py` → **17/17 PASS** (Python 3.11).
- Regressioni pertinenti (RC84 fasi 2, 2B, 2C, hardening, fase 3, S25, trend change, RC82/RC84 V3) → **404 PASS**.
- Suite completa, stesso comando della Fase 3 → **7080 passed, 1 failed, 9 skipped, 3 xfailed** (Python 3.13). Base Fase 3 `f8332c9`: 7063 passed + lo stesso
  unico fallimento di ambiente (`test_v3_rc84_import_paths::test_auth_and_profiles_before_the_subprocess_lock_tests_in_both_orders`,
  SQLAlchemy 2.0.28 con Python 3.13). Differenza = esattamente i 17 test dello studio.

### 5. Replay sintetico (NON dati reali)

Bitget e gli altri fornitori di dati sono bloccati dalla rete di questa sessione: **nessun replay su storico reale
15m è stato possibile e nessun risultato reale viene riportato.** Il replay
`deploy/scripts/replay_toro_long_mirror_15m.py` usa mercati sintetici: 3 regimi × 6 semi × 60 giorni (più 40 giorni
di riscaldamento per l'EMA200 4h). Decisione alla chiusura della candela, ingresso all'apertura della successiva,
trend 4h dal lettore RC84 invariato, stop 1,2×ATR 1h (0,3%–3,5%), TP 1,8×stop, massimo 24 h, stop prioritario se
nella stessa candela si toccano stop e target, commissioni 6 bp/lato, slippage 2 bp/lato, funding LONG 1 bp/8 h.
Controllo: 20 estrazioni di ingressi LONG casuali per mercato con le stesse uscite e gli stessi costi.
Rendimenti in % del nozionale, senza leva.

| Regime (sintetico) | Tipo | Operazioni | Vincenti | Media netta/op. | t | Controllo casuale media/op. |
|---|---|---|---|---|---|---|
| rialzo | CONTINUATION | 547 | 42,4% | +0,063% | 0,91 | +0,076% (tutti i tipi) |
| rialzo | BOUNCE | 18 | 33,3% | −0,206% | −0,55 | |
| ribasso con rimbalzi | CONTINUATION | 210 | 37,1% | −0,115% | −1,06 | −0,148% |
| ribasso con rimbalzi | BOUNCE | 225 | 39,6% | −0,032% | −0,30 | |
| laterale | CONTINUATION | 220 | 13,2% | −0,899% | −12,43 | −0,052% |
| laterale | BOUNCE | 238 | 28,6% | −0,395% | −4,11 | |

Letture (valide solo per questo generatore): in rialzo il prototipo **non batte ingressi casuali** (li supera in 3 semi
su 6); nei rimbalzi in ribasso perde meno del caso ma resta negativo; nel laterale perde molto più del caso, perché le
conferme di rottura 15m comprano i massimi locali di un mercato che torna indietro, e il trend 4h EMA50/200 non
riconosce il laterale (in quel regime ha prodotto 715 CONTINUATION e 439 BOUNCE). I costi pesano circa 0,17% per
operazione contro uno stop medio di circa 1,18%. Un generatore casuale non contiene strutture prevedibili oltre la
deriva: il replay prova la meccanica, l'assenza di lookahead e il peso dei costi; **non può dimostrare un vantaggio**.

### 6. Valutazione

Il prototipo è tecnicamente pulito come lettore di dati (candele chiuse, niente lookahead, continuità, duplicati,
NO_TRADE). Come strategia **non c'è alcuna evidenza di vantaggio**: i test sono sintetici e il replay sintetico non
mostra un vantaggio sugli ingressi casuali, con perdite marcate nel laterale. Merita un **backtest su storico reale
15m** (passo economico, necessario comunque) con i tre regimi separati e un filtro per il laterale come ipotesi da
provare; **non è pronto a ripartire** né in PAPER né tanto meno in live.

## Proposta futura Toro (NON attivata, nessuna impostazione cambiata)

Configurazione richiesta: solo LONG, 5 slot, massimo 200 USDT di margine per posizione, capitale PAPER 1.000 USDT,
valutazione su candele 15m, leva alta solo dopo verifica di rischio e liquidazione.

Configurazione attuale di Toro (`cli._make_bull_config`, invariata): 3 posizioni × 350, margine totale 1.050,
`kill_equity` 450, `daily_stop` 12%, guardrail margine minimo 150 / forzato 200, leva minima 10 / forzata 15, tipo medio.

Punti da decidere prima di attivare:

1. **5 × 200 = 1.000 = tutto il capitale.** Il motore limita ogni apertura anche a `cash × 0,95` e alle commissioni:
   la quinta posizione non avrebbe 200 USDT pieni. Valutare 5 × 180 o un totale massimo 900.
2. **Leva e liquidazione.** Regola del motore: distanza stop ≤ 0,75 × (1/leva − 0,005). Con lo stop medio del replay
   (1,18%) la leva massima compatibile è circa 48×; con 2,07% circa 30×; con lo stop massimo 3,5% circa 19×.
   Tetti per asset invariati: BTC/XAU/XAG 45×, ETH 30×, altri 25×.
3. **Perdita per stop con 200 USDT di margine** (stop 1,18% + 0,17% di costi): 10× ≈ 27 USDT, 20× ≈ 54 USDT,
   30× ≈ 81 USDT. Con cinque stop insieme: 135 / 270 / 405 USDT, cioè oltre lo `daily_stop` del 12% (120 USDT) già da
   10× e vicino al `kill_equity` 450 da 30×. Proposta: leva calcolata per posizione come il minimo fra tetto
   dell'asset, leva compatibile con la liquidazione e leva che limita la perdita per stop a circa il 2,5% del capitale
   (25 USDT ⇒ circa 9× con stop 1,18%); "alta leva" solo con stop stretti e dopo backtest reale.
4. Cinque slot sono un massimo, non un obiettivo: nessun ingresso forzato; la correlazione fra crypto rende i cinque
   stop simultanei uno scenario realistico.
5. Modalità `LONG_ONLY` di Toro sul modello di `DESK_HAWK_ENTRY_MODE`: uscite e protezioni delle posizioni esistenti
   sempre attive, solo PAPER, nessun effetto su Falco e Brain.
6. Cadenza 15m: il runner gira ogni 30 min (15 se c'è uno scalp aperto) e non è allineato alla chiusura delle candele;
   un'eventuale cadenza dedicata va misurata (costo API) senza alterare Falco.
7. Prompt e guardrail di Toro (TP ≥ 5%, tipo forzato medio, leva forzata 15) sono incoerenti con una strategia 15m con
   stop di circa 1%: vanno rivisti **solo** su decisione dell'utente.

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
# replay sintetico di studio (circa 40 s, nessuna rete, nessun ordine):
PYTHONPATH=backend python3 deploy/scripts/replay_toro_long_mirror_15m.py --days 60 --seeds 6 --json /tmp/replay_toro.json
```

**PORTO SICURO:** branch Fase3 `work/rc84-phase3-falco-short-only-20261112` /
`f8332c92...`, branch Fase2 frozen `dc98413...`, RC84 VPS `ab7e0b7...` e
i backup restano invariati. Nessun merge, deploy, unpause, reset o ordine LIVE.

## Backtest su storico REALE Bitget USDT-FUTURES (13 novembre 2026, sul commit `1de3b7d`)

**Verdetto: FAIL.** Nessun vantaggio misurabile su dati reali: il prototipo perde in tutti e tre i mercati, in
entrambi i periodi, con e senza le conferme 15m. Senza costi il risultato è circa zero; i costi lo rendono negativo.
Il portafoglio Toro proposto raggiunge la protezione dei 450 USDT in quasi tutte le combinazioni di leva e margine.
**Toro LONG Mirror 15m non merita di essere sperimentato in PAPER nella forma attuale.** Nessuna soglia è stata
cambiata per migliorare il risultato.

### Dati

- **Fonte:** endpoint pubblici ufficiali Bitget `GET /api/v2/mix/market/history-candles` (USDT-FUTURES, 15m e 4H nativi)
  e `history-fund-rate`, senza credenziali. La pagina `bitget.com/data-download` dichiara l'archivio delle candele
  futures, ma è un'applicazione JavaScript che non espone i file in modo scaricabile da riga di comando: è stato usato
  l'endpoint documentato, che è la stessa fonte di mercato (Bitget Futures). Script:
  `deploy/scripts/fetch_bitget_futures_history.py`; manifest con SHA-256 in
  `docs/v3/toro-long-mirror-15m-backtest/manifest-dati.json` (i CSV non sono nel repository: si rigenerano con lo script).
- **Periodo:** 12/04/2025 04:00 → 13/11/2026 07:00 UTC, BTCUSDT, ETHUSDT, SOLUSDT. Riscaldamento fino al 22/05/2025
  (EMA200 4h). **Periodo A (studio)** 22/05/2025 → 15/02/2026; **periodo B (valutazione)** 15/02/2026 → 13/11/2026;
  data di taglio fissata prima dei risultati.
- **Integrità** (`integrita-dati.json`): 55.692 candele 15m e 3.480 4H per mercato, esattamente quelle attese;
  0 buchi, 0 duplicati, 0 OHLCV invalidi, 0 volumi nulli, orari allineati; il 4H nativo coincide **esattamente**
  (scarto 0) con il 4H ricavato dalle 15m su tutte le 3.480 barre; solo candele chiuse. Nessuna interpolazione.
- **Difetto trovato e corretto nello scaricatore:** l'endpoint restituisce le candele con *chiusura* ≤ `endTime`; la
  prima versione paginava con `endTime = prima_apertura − 1` e perdeva una candela ogni 200 (277 buchi regolari,
  identici sui tre mercati). Corretto prima di ogni analisi e coperto dal test `test_pagination_keeps_every_candle`.
- **Funding:** l'endpoint pubblico restituisce solo gli ultimi 90 giorni (15/08–13/11/2026; media 0,45–0,61 bp/8h,
  minimo −1,35, massimo 1,0). Per tutto il periodo si usa la costante del motore PAPER (1 bp/8h), più prudente;
  sensibilità a 3 bp/8h.
- **Mercato nel campione:** esposizione LONG semplice A: BTC −37,7%, ETH −20,8%, SOL −50,3%; B: BTC −1,1%,
  ETH −7,1%, SOL −9,0%. Il campione **non contiene un rialzo prolungato**: i giorni classificati "rialzo" (regime
  ex-ante, rendimento 7 giorni ≥ +3%) sono 59–94 per mercato e periodo. È un limite del campione da tenere presente.

### Metodo (fissato prima dei risultati)

Decisione alla chiusura della candela 15m con sole candele chiuse; trend 4h dal lettore RC84 invariato sulle 4H
native chiuse; ingresso all'apertura della candela successiva. Uscite di studio uguali per tutte le varianti: stop
1,2×ATR 1h (0,3%–3,5%), take profit 1,8×stop, 24 h massimo, stop eseguito a min(stop, apertura) come `engine.on_bar`.
Costi: commissioni 6 bp/lato, slippage 2 bp/lato, funding 1 bp/8h. Varianti: **PROTOTIPO**; **SENZA_CONFERME** (stesso
punteggio e soglie, senza le tre conferme 15m nuove); **ORIGINALE_1H** (`signals.read_symbol` congelato, lato LONG,
soglia del runner 60 BTC/ETH e 70 SOL); **CASUALE** (stesso numero di ingressi, 50 estrazioni per mercato e periodo);
**ESPOSIZIONE** semplice. Script: `deploy/scripts/backtest_toro_long_mirror_15m.py`; risultati completi in
`docs/v3/toro-long-mirror-15m-backtest/risultati.json`.

### Risultati per operazione (rendimento netto in % del nozionale, senza leva)

| Periodo | Variante | Operazioni | Media netta | Senza costi (BTC / ETH / SOL) |
|---|---|---|---|---|
| A | PROTOTIPO | 990 | −0,171% | −0,018 / +0,025 / +0,022 |
| A | SENZA_CONFERME | 1.243 | −0,180% | |
| A | ORIGINALE_1H | 333 | −0,164% | |
| A | CASUALE | 49.500 | −0,207% | |
| B | PROTOTIPO | 921 | −0,177% | −0,022 / +0,001 / +0,015 |
| B | SENZA_CONFERME | 1.207 | −0,192% | |
| B | ORIGINALE_1H | 249 | −0,289% | |
| B | CASUALE | 46.050 | −0,213% | |

Dettaglio PROTOTIPO, periodo B (valutazione):

| Mercato | Operazioni | Vincenti | Media | Profit factor | Drawdown (somma %) | Casuali battuti |
|---|---|---|---|---|---|---|
| BTC | 295 | 35,3% | −0,194% | 0,64 | 57,3 | 58% |
| ETH | 309 | 35,9% | −0,167% | 0,75 | 51,7 | 82% |
| SOL | 317 | 34,1% | −0,170% | 0,78 | 60,0 | 84% |

Per tipo e regime (periodo B, PROTOTIPO): continuazione BTC −0,14%, ETH −0,11%, SOL −0,22%; rimbalzo BTC −0,24%,
ETH −0,22%, SOL −0,13%; regime rialzo BTC −0,14%, ETH −0,14%, **SOL +0,04% (t 0,24, non significativo)**; ribasso
−0,24%…−0,43%; laterale −0,16%…−0,20%. Nel periodo A tutti i sottoinsiemi sono negativi (il migliore: ETH
continuazione −0,03%, profit factor 0,96).

**Costi:** senza costi la media è fra −0,02% e +0,03% per operazione, cioè nessun vantaggio lordo; i costi base
(~0,17% per operazione con 6–7 ore di durata media) determinano interamente la perdita; con costi doppi −0,32%…−0,36%;
con funding 3 bp/8h −0,16%…−0,21%.

**Confronto con il caso:** il prototipo perde un po' meno degli ingressi casuali (−0,17% contro −0,21%) e batte fra il
58% e il 90% delle estrazioni casuali: le conferme filtrano qualche ingresso pessimo, ma non creano un risultato
positivo. Le conferme 15m riducono le operazioni di circa il 20–25% rispetto a SENZA_CONFERME con media simile.
L'algoritmo LONG originale 1h è anch'esso negativo (−0,16% in A, −0,29% in B).

### Portafoglio Toro simulato con `engine.PaperAccount` invariato

Limiti: capitale 1.000, massimo 5 posizioni, massimo 200 USDT per operazione, margine totale 1.000, protezione 450,
stop giornaliero 12%; leva richiesta 3/5/10/15/20/30 (limitata dal tetto dell'asset), margine 100 o 200.

- **PROTOTIPO, periodo B:** con 3× e 100 USDT l'equity finisce a 497 (−503) senza toccare la protezione; **tutte le
  altre combinazioni raggiungono la protezione dei 450 USDT** (equity finale 385–449, drawdown 55–68%).
  Periodo A: protezione raggiunta in tutte le 12 combinazioni.
- Le commissioni da sole valgono da circa 50 a 510 USDT a seconda della combinazione: con un vantaggio lordo nullo, la leva e il
  margine aumentano solo la velocità della perdita.
- Nessuna liquidazione con il prototipo (stop stretti); con l'originale 1h a 20–30× si verificano 1–2 liquidazioni.
- **Con tre mercati non si superano mai 3 posizioni insieme**: i 5 slot non sono raggiungibili con questa lista.

### Conclusione

1. Dati reali affidabili: sì (fonte ufficiale, integrità completa).
2. Vantaggio misurabile: **no**, né per le continuazioni né per i rimbalzi, in nessun mercato e in nessuno dei due periodi.
3. Mercati laterali: perdite in tutti i casi, come nel replay sintetico, ma non peggiori degli altri regimi su dati reali.
4. Leva: nessuna leva rende positivo un vantaggio lordo nullo; la leva alta anticipa la protezione dei 450 USDT.
5. Verdetto: **FAIL**. Non attivare Toro LONG Mirror 15m in PAPER. Limite dichiarato: il campione è prevalentemente
   ribassista/laterale; un'eventuale ripresa dello studio richiederebbe una nuova ipotesi, documentata prima di
   guardare i dati, non la modifica delle soglie attuali su questo stesso campione.
