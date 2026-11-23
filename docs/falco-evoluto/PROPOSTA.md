# Falco Evoluto vs Brain Scalp — progetto tecnico consolidato (23/11/2026)

Ramo `claude/falco-evoluto-20261123`. Solo PAPER. Nulla installato, nessuna run creata sulla VPS, nessun mandato
approvato. Falco storico, Toro, Brain RC1, Arena e i loro dati restano invariati.

## 1. Architettura (riuso, nessun nuovo progetto)

Due run V3 indipendenti sullo stesso runner, stessa contabilita' (EventJournal), stessi costi (6 bp/lato + 2 bp
slippage), stesso servizio uscite, stessi 8 simboli di Brain. Cambia solo l'analista:

| | Falco Evoluto | Brain Scalp |
|---|---|---|
| Configurazione | `backend/v3/runner/runner_config_falco_evoluto_paper.json` | `runner_config_brain_scalp_paper.json` |
| Analista | regole (`backend/v3/falco_evoluto.py`), DeepSeek solo consulente | DeepSeek L5 (come RC1: scoreboard degli esiti e memoria nel prompt) |
| Capitale | 1.000 USDT | 2.000 USDT |
| Ciclo | 15 min (regole, costo AI quasi nullo) | 30 min |
| Budget AI | 0,20 USD/giorno | 0,75 USD/giorno |
| Leva | 15–45x (mai sotto 15x) | 15–45x |
| Margine per trade | 100–250 USDT | 250–450 USDT |
| Margine totale | 50 % (allineato, proposta 23/11) | 50 % (profilo B) |
| Equity minima | 800 (80 %, allineata, proposta 23/11) | 1.600 (80 %, profilo B) |

Comuni: rischio a stop per trade 4 % dell'equity, 20 % del margine effettivo, rischio aperto 10 %, rischio nella
stessa direzione 8 % (le 8 crypto sono correlate a BTC), 4 posizioni al massimo (mai obbligatorie), stop giornaliero
UTC 8 % (DailyLossGuard, avviso 5 %), uscite TP 3R / break-even da +1R / trailing da +1,5R a 1R / 24 h, Guardian 08:00
Europe/Rome. Il rischio autorizzato e' il MINORE fra tutti i limiti, incluso il tetto del Guardian; la leva viene
cercata dalla massima verso 15x, mai sotto; lo stop non viene mai stretto; se nulla quadra: NO_TRADE con il motivo.

**Conseguenza matematica da conoscere:** perdita a stop <= 20 % del margine significa leva x (stop + costi) <= 0,20.
A 15x lo stop massimo e' circa 1,17 % (con costi 0,16 %), a 45x circa 0,28 %. Sui simboli con ATR 1h alto lo stop di
Falco (1,2 x ATR) supera spesso questo limite: quei segnali diventano NO_TRADE. Con 4 % per trade e 10 % aperto, a
rischio pieno stanno 2 posizioni.

**Capacita' misurata (motore e RiskManager veri, `test_how_many_full_risk_positions_fit_under_the_aligned_limits`):**
con stop 0,3-1,0 % entrano 2 posizioni a rischio pieno (Falco: 40 USDT di rischio, circa 202-208 di margine; Brain:
80 USDT, circa 404-417). La terza e' rifiutata `below_min_margin`: il rischio residuo (10 % - 2 x 4 % = 2 %) chiede
circa 101 di margine (Falco) ma ne restano 96 sotto il 50 %. Con il vecchio 95 % di Falco entrava una terza
posizione a meta' rischio. **4 posizioni non sono raggiungibili** con 4 % per trade e 10 % aperto (2,5 trade pieni):
servirebbero, ad esempio, rischio per trade 2,5 % oppure rischio aperto 16 %. Nessun valore cambiato senza approvazione.

## 2. Smart Profit Guardian (`backend/v3/guardian.py`)

Deterministico, ricostruito a ogni giro dal journal della run e dalle chiusure da 1 minuto; nessun file di stato.
- Equity mark-to-market (commissioni di uscita stimate incluse), realizzato e non realizzato separati, picco di
  sessione, giveback, rischio aperto a stop, spesa AI di sessione (dal registro della run).
- Floor mobile: si arma a +8 % di sessione; floor = inizio + 75 % del picco positivo (giveback 25 %), solo crescente.
  Budget = equity - floor - rischio aperto. Il floor limita le NUOVE aperture: non e' una garanzia sul profitto finale
  ne' sulle posizioni aperte (gap, slippage, liquidazione).
- NORMAL (non armato) · SELECTIVE (budget >= 1R: tetto = min(R, 50 % del budget)) · PROTECTED (budget fra 0,25R e 1R:
  stesso tetto + confidenza >= 0,7 + nessun reingresso della stessa tesi) · LOCKED (budget < 0,25R; equity sotto il
  floor o perdita di sessione >= 8 %: bloccato fino alla sessione successiva; drawdown globale >= 20 %; prezzi mancanti;
  errore del Guardian). In LOCKED nessuna chiamata AI. Drawdown globale >= 10 %: R dimezzato.
- Sessione 08:00 Europe/Rome (23/25 h nei cambi d'ora); il cambio riabilita solo le nuove aperture, non chiude nulla e
  non azzera i limiti globali; una posizione a cavallo entra al suo valore di mercato del cambio.
- Ogni valutazione e' nel journal (`guardian_state`); un blocco e' una riga di errore del giro con il motivo.

Esempio Brain (2.000): +250 realizzati -> floor 2.187,50, budget 62,50 -> PROTECTED, nuova apertura <= 31,25 di
rischio. Con +600 -> budget 150 -> SELECTIVE. Proteggere il 75 % di un guadagno significa rischiare solo il 25 %:
dopo l'armamento il sistema rallenta di proposito.

## 3. Falco Evoluto (`backend/v3/falco_evoluto.py`)

SHORT originale di Falco con correzioni esplicite (EMA SMA-seeded, EMA200 4h solo con >= 220 candele: la run ne tiene
300; trend 1d solo da giorni UTC completi con EMA20 e pendenza; solo candele chiuse; niente stagionalita' non
verificata) e veto se 4h e 1d sono rialzisti. LONG indipendente (non S25): regime TREND_UP/EXPANSION, 4h, 1d e 1h
rialzisti, prezzo sopra EMA50 1h, RSI 50–70, volume >= media, nessun incrocio o pattern ribassista. NO_TRADE in
RANGE/UNCERTAIN/SHOCK/UNKNOWN e con segnali contrastanti. DeepSeek solo per conflitto, inversione 1h contraria o
EXPANSION: conferma o NO_TRADE, mai lato/leva/stop; AI giu' o budget finito -> NO_TRADE.

## 4. Uscite (`backend/v3/runner/exits.py`)

Politica per run nella configurazione (schema 2). Break-even con costi, trailing in R, protezione di quota: stesse
regole dei bracci pre-registrati del laboratorio (test di equivalenza). Il tipo di stop spostato e' nel journal
(`paper_close.stop_kind`). Nessuna chiusura a orario. Target netto: `gross_r_for_net_target` (proposta, non applicata):
3R lordi con stop 0,5 % valgono circa 2R netti; per 3R netti servirebbero circa 4,3R lordi.

## 5. Journal (perche', non solo cosa)

Motivo di ogni NO_TRADE e apertura (codici chiusi), fonte (regole SHORT/LONG, conferma AI), motivo preciso dei
rifiuti di rischio (`risk_reason`), stato e budget del Guardian, tesi e indice di reingresso (traccia delle decisioni),
tipo di uscita, chiusure manuali (`reason=manual`). Lo scoreboard degli esiti continua ad alimentare il prompt di
DeepSeek: e' contesto, non addestramento.

## 6. Confronto

`GET /api/v3/compare` (sola lettura, run da `V3_COMPARE_RUNS`) e pagina `/compare`: capitale, equity, P&L netto,
rendimento %, drawdown, profit factor, win rate, LONG/SHORT, Guardian (stato, sessione, picco, giveback, rischio
residuo, tetto), posizioni, chiusure manuali, stop protettivi, spesa AI, ultime decisioni con motivo.

## 7. Limiti aperti

1. E0 sugli storici: nessuno storico attestato raggiunge il campione minimo (30 trade e 10 sessioni per gruppo);
   l'anti-reingresso resta in osservazione (vincolante solo in PROTECTED). La misura vera arrivera' dal PAPER.
2. Chiusura manuale singola: FATTA (bridge con `V3_BRIDGE_EXTRA_RUNS`, rotte `/api/v3/compare/{nome}/close` e
   `close-result`, pulsante nella pagina di confronto, test end-to-end offline per entrambi i portafogli).
3. Chiusure parziali: richiedono un evento di chiusura parziale nel journal (fase successiva).
4. Costo DeepSeek di Brain Scalp a 30 min: stima circa 0,77 USD/giorno (una sola misura reale, 3.040 token): al limite
   del tetto 0,75; a tetto raggiunto le nuove aperture si fermano fino al giorno UTC successivo (uscite attive).
5. Rilascio (non eseguito): creare le due run in pausa con `prepare_paper_run`; 2 unita' per run (uscite + runner);
   unita' del bridge con le due run montate in scrittura e `V3_BRIDGE_EXTRA_RUNS`; container web con le due run in
   sola lettura e `V3_COMPARE_RUNS` (nomi `falco_evoluto` e `brain_scalp`); nuova build dell'interfaccia.
