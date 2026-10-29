# Prompt per ChatGPT — Brain Scalp: correzioni complete + analisi dati
Data: 29/10/2026 | Preparato da Claude (chat) per l'utente da consegnare a ChatGPT

---

## CHI SEI E COSA DEVI FARE

Sei ChatGPT, responsabile dell'implementazione del codice nel progetto **SuperBot Trading** (repository pubblico GitHub: `alexiptv82/SuperBot-Trading`).

Claude (chat) ha fatto l'analisi e la revisione del codice: ha trovato 13 bug e Claude Code ne ha trovati altri 4. Hai anche un'analisi quantitativa su dati reali Bitget (60 giorni, 17 simboli). Questo documento contiene TUTTO quello che devi fare.

**L'utente ti ha delegato l'intera implementazione.** Dopo ogni gruppo di correzioni, aspetta la conferma dell'utente prima di procedere al gruppo successivo.

---

## REGOLE INVIOLABILI (dal CLAUDE.md — non si discutono)

1. **Nessun redeploy** dei bot (Hawk, Bull) senza OK esplicito dell'utente.
2. **Niente live trading**: il Secret `DESK_MODE` resta `paper` finché l'utente non dice esplicitamente di passare a live.
3. **Nessuna modifica** a strategia, soglie, limiti di rischio, prompt AI senza decisione dell'utente.
4. Il "cervello" (`trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl` in `/opt/superbot-desk-data/{hawk,bull}/`) **non si cancella, non si azzera, non si modifica**: solo cresce.
5. Le **API key** di trading mai nel codice, solo nei GitHub Secrets.
6. **Mai toccare** HI-TV / `hitvprime` (nginx, DNS, container su Strasburgo).
7. Il repository è **pubblico**: nessun segreto, nessun importo o saldo reale di Bitget in codice, log, commit o diario.
8. **Mai** `git push --force`; non unire `work/backend-singapore-audit`; nessun push su `stable/*` e `v0.5`.
9. **Un solo autore alla volta per componente** (sei tu adesso per Brain Scalp).

### Regola aggiuntiva per questa sessione di lavoro (istruzione dell'utente)
- Non modificare `backend/director/brain_free/` né `backend/desk/`: i classici e Brain Free V2 non si toccano.
- Non fare deploy di nessun tipo (niente restart container, niente push su `rule-pool`).
- Non fare merge tra i due rami motore e app.
- Non toccare `main`, `stable/*`, `v0.5`, `rule-pool`.

---

## CONTESTO DEL PROGETTO

### Cos'è Brain Scalp
Sistema di scalping H24 AI-driven su futures Bitget, in PAPER (simulazione), completamente separato dai bot classici Hawk e Bull.

- **Brain Hawk**: 1000$ PAPER, 10 slot, margine per trade 100-250$
- **Brain Bull**: 1000$ PAPER, 3 slot, margine per trade 150-350$
- Timeframe: candele 1m e 5m
- AI (Claude API) come filtro di qualità dei segnali, non come generatore meccanico

### Branch di lavoro
- **Motore** (backend Python): `work/brain-scalp-dual-20261028`, HEAD commit `d96d171`
  - Base: Brain Free V2 `e0021488`
  - File chiave: `backend/director/brain_scalp/` (config, scanner, plans, engine, store, coordinator)
  - Riutilizza: `brain_free/execution.py` e `brain_free/config.py` (NON toccare questi)
- **App** (frontend/deploy): `work/brain-scalp-dual-app-20261028`, HEAD commit `320de78`
  - Base: `main` `2283bfb`

### Struttura file Brain Scalp
```
backend/director/brain_scalp/
├── config.py          ← parametri scalp (NON toccare brain_free/config.py)
├── scanner.py         ← genera segnali dai mercati
├── plans.py           ← valida e costruisce i piani di trading
├── engine.py          ← loop principale: tick, protezioni, aperture
├── store.py           ← persistenza SQLite WAL con flock
└── coordinator.py     ← orchestra Hawk + Bull, chiama AI
```

---

## ANALISI DEI DATI REALI — COSA DICONO I NUMERI

Prima di vedere i bug, leggi questa sezione: ti serve per capire *perché* certi bug sono critici.

### Dataset
17 simboli USDT-FUTURES Bitget, 86.400 candele 1m per simbolo, 60 giorni (2026-09-01 → 2026-10-28).
BTC e 8 altri esclusi durante il download per HTTP 429 (rate limit Bitget).

### Costi strutturali
Fee 0.06% + slippage 0.02% per lato = **0.16% round-trip**. Non negoziabile.

**Win rate minimo per non perdere (break-even):**
| R:R | Target | Stop | Win rate BE |
|-----|--------|------|-------------|
| 2:1 | 0.32%  | 0.16% | **38.7%** |
| 3:1 | 0.48%  | 0.16% | **28.6%** |
| 5:1 | 0.80%  | 0.16% | **20.0%** |

### Tassi di base reali (senza AI, ingressi casuali con ATR>0.20%)
| Simbolo | R:R 2:1 | R:R 3:1 | R:R 5:1 |
|---------|---------|---------|---------|
| INJ     | 35.2%   | 26.7%   | 15.4%   |
| AVAX    | 34.5%   | 25.6%   | 13.7%   |
| NEAR    | 34.0%   | 25.6%   | 14.5%   |
| UNI     | 33.9%   | 25.3%   | 14.3%   |
| FIL     | 33.8%   | 25.4%   | 14.1%   |
| ADA     | 33.7%   | 24.2%   | 11.2%   |
| DOT     | 32.2%   | 23.5%   | 12.2%   |
| ETH     | 31.4%   | 21.0%   | 9.2%    |

**Lettura critica**: tutti i simboli sono 4-8 punti percentuali SOTTO il break-even a R:R 2:1. Il mercato non è casuale positivo per lo scalp 1m a questi costi. L'AI DEVE aggiungere selezione qualitativa, non può essere neutra.

**Cosa deve fare l'AI per rendere il sistema profittevole:**
- Rifiutare ≥30% dei segnali proposti dallo scanner
- Di quelli rifiutati, almeno 2/3 devono essere futuri perdenti
- Per farlo, l'AI ha BISOGNO di informazione: ATR attuale, livelli di supporto/resistenza, direzione del trend recente, volume — senza questi non può filtrare meglio del caso

### Simboli da escludere / classificare
**Escludere XAU e XAG**: ATR medio 0.027-0.044%, barre viabili <0.3%. Strutturalmente inutilizzabili per scalp a 0.16% costi.

**Top tier** (alta volatilità, molte barre viabili HL>0.32%): NEAR (23.3%), INJ (12.2%), UNI (11.8%), FIL (9.9%), DOT (7.5%)
**Mid tier**: AVAX, ADA, DOGE, XRP, RUNE, LINK, BCH, SOL
**Low tier** (scalp difficile): ETH (1.0%), BNB (0.3%)

### Raccomandazione parametri target dai dati
- R:R minimo sensato: **3:1** con stop dinamico basato su ATR
- Stop = ATR_20 × 0.5, Target = ATR_20 × 1.5
- ATR filter: aprire solo quando ATR_20 > 0.20% (filtra ~80-90% delle barre di bassa volatilità)

⚠️ **ATTENZIONE**: Non implementare nuovi parametri adesso. Prima correggi i bug (Gruppi 1-5). I parametri si cambiano DOPO il primo replay pulito, con decisione esplicita dell'utente.

### Bug più importante per la profittabilità
Lo scanner NON passa ATR, livelli e volume all'AI. L'AI riceve sempre lo stesso tipo di segnale e non può differenziare. È il bug [I6/Code] nel Gruppo 4. Senza questa informazione, qualsiasi AI è cieca quanto un ingresso casuale.

---

## CORREZIONI DA FARE — ORDINE ESATTO

**Regola di lavoro**: una correzione per commit, messaggio chiaro, test che la verifica. Non raggruppare modifiche diverse nello stesso commit. Dopo ogni GRUPPO (non ogni singolo commit): aggiorna `STATO.md` e la voce di diario del giorno con `[skip ci]`, poi aspetta OK dell'utente.

---

### GRUPPO 1 — Fisica del tick (B3a, B3b, B3c, I4) — PRIORITÀ MASSIMA

Questi bug possono far crashare il motore o perdere protezioni attive. Correggili per primi.

---

#### B3a — equity() con price=None blocca l'intero tick
**File**: `backend/director/brain_free/execution.py` righe 26-32 (funzione `equity`)

**Problema**: se la quota ha `price=None` o non è un numero finito, `q['price'] - entry` solleva `TypeError` e blocca il tick intero — anche il wallet sano.

**ATTENZIONE**: `brain_free/execution.py` è condiviso con Brain Free V2 in produzione. Valuta se la correzione si applica anche lì (dovrebbe essere sicura: aggiunge un early return su dati invalidi). Se preferisci NON toccare `brain_free/`, sovrascrivi `equity()` in una sottoclasse Brain Scalp — la scelta è tua, comunicala all'utente.

**Correzione in execution.py (funzione equity):**
```python
import math

def equity(self, q, entry, side):
    price = q.get('price')
    if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        return None  # il chiamante deve gestire None
    # resto del codice originale invariato
    ...
```

**Aggiornare il chiamante in engine.py**: dove viene chiamata `equity()`, gestire `None`:
```python
eq = execution.equity(q, position['entry'], position['side'])
if eq is None:
    log_event('equity_unavailable', {'symbol': symbol, 'reason': 'invalid_quote'})
    continue  # salta questo simbolo, continua il tick
# usa eq normalmente
```

**Test da aggiungere**: `tick()` con quota `price=None` su simbolo aperto → nessuna eccezione, wallet continua, evento `equity_unavailable` registrato.

---

#### B3b — Orologio che torna indietro blocca le protezioni
**File**: `backend/director/brain_scalp/engine.py` riga ~59

**Problema**: `now < last_ms` solleva `backward_clock` PRIMA di chiamare `protect()`. Una posizione sotto lo stop non viene chiusa.

**Correzione:**
```python
now_original = now
if now < last_ms:
    now = last_ms  # avanza al minimo monotono
    log_event('clock_adjusted', {'delta_ms': last_ms - now_original})
# Le protezioni girano sempre, anche con clock aggiustato
protect(positions, markets, now)
# Le NUOVE aperture sono bloccate se il clock era indietro
opening_allowed = opening_allowed and (now_original >= last_ms - CLOCK_TOLERANCE_MS)
```
Dove `CLOCK_TOLERANCE_MS = 500` (tolleranza 0.5 secondi).

**Test**: posizione long con stop 99.8, quota 99.0 a `now` di 1 ms indietro → posizione chiusa allo stop, nessuna eccezione, evento `clock_adjusted` registrato.

---

#### B3c — Errore su Hawk ferma anche Bull
**File**: `backend/director/brain_scalp/coordinator.py` righe ~59-62

**Problema**: `BrainPair.tick` chiama Hawk poi Bull in sequenza senza `try/except`. Un crash su Hawk blocca Bull.

**Correzione:**
```python
for wallet_name, wallet in [('hawk', self.hawk), ('bull', self.bull)]:
    try:
        wallet.tick(markets, now)
    except Exception as e:
        log_event('wallet_tick_error', {
            'wallet': wallet_name,
            'error': str(e),
            'traceback': traceback.format_exc()
        })
        # continua con l'altro wallet
```

**Test**: Hawk riceve quota malformata → eccezione isolata, evento `wallet_tick_error` registrato, Bull viene tickato regolarmente.

---

#### I4 — Tolleranza 30s per l'ingresso: fill al prezzo sbagliato
**File**: `backend/director/brain_scalp/plans.py` riga ~72 e `backend/director/brain_free/config.py`

**Problema**: tolleranza 30 secondi per eseguire un ingresso — il fill avviene al prezzo di 30 secondi fa. Per uno scalp 1m è inaccettabile (il prezzo può muoversi oltre i costi in quel tempo).

**Correzione in `brain_scalp/config.py`** (NON toccare `brain_free/config.py`):
```python
ENTRY_PRICE_AGE_MS = 3000    # max 3 s per ingresso e trigger
PROTECT_PRICE_AGE_MS = 10000 # max 10 s per protezione (meno critico)
```

**In plans.py**: usare `config.ENTRY_PRICE_AGE_MS` per il controllo dell'ingresso:
```python
from . import config as scalp_config
# invece di price_age_ms ereditato da brain_free:
if quote_age_ms > scalp_config.ENTRY_PRICE_AGE_MS:
    return reject('quote_too_stale_for_entry', {
        'age_ms': quote_age_ms,
        'max_ms': scalp_config.ENTRY_PRICE_AGE_MS
    })
```

Registrare lo scarto fill a ogni apertura:
```python
log_event('entry_fill', {
    'symbol': symbol,
    'trigger_price': trigger_price,
    'fill_price': fill_price,
    'slippage_pct': abs(fill_price - trigger_price) / trigger_price * 100
})
```

**Test**: quota di 5 s → nessuna apertura, motivo `quote_too_stale_for_entry`; quota di 2 s → apertura OK, evento `entry_fill` registrato.

---

### GRUPPO 2 — Fisica dei piani (I2, I3, B2) — priorità alta

Aspetta OK dell'utente dopo il Gruppo 1 prima di iniziare questo.

---

#### I2 — Target che non copre i costi: trade destinato a perdere
**File**: `backend/director/brain_scalp/engine.py` righe ~108-116 e `plans.py` riga ~53

**Problema**: un piano con target così piccolo da non coprire i costi (0.16% round-trip) viene accettato. Il motore entra in trade che non possono essere profittevoli per costruzione.

**Correzione** (in engine.py, nella validazione del piano, PRIMA di accettarlo):
```python
cost_pct = (config.FEE_PCT + config.SLIPPAGE_PCT) * 2  # round-trip
net_at_target = abs(target_price - entry_price) / entry_price - cost_pct
min_net_pct = cost_pct  # target deve portare almeno 1× i costi di utile netto

if net_at_target < min_net_pct:
    return reject('target_below_costs', {
        'net_at_target_pct': round(net_at_target * 100, 4),
        'min_required_pct': round(min_net_pct * 100, 4),
        'costs_pct': round(cost_pct * 100, 4),
        'min_target_price': entry_price * (1 + (cost_pct * 2) * side_sign)
    })
```

Passare `min_target_price` e `costs_pct` all'AI nei rifiuti, così impara.

**Test**: piano con target 0.05% su trigger, costi 0.16% → rifiuto `target_below_costs`; piano con target 0.35% → OK.

---

#### I3 — Piano che supera il budget viene rifiutato invece di ridimensionato
**File**: `backend/director/brain_scalp/engine.py` righe ~112-116

**Problema**: quando il piano supera il budget di rischio disponibile, viene rifiutato secco. Sarebbe meglio ridimensionare leva e margine al massimo consentito, e rifiutare solo se non è possibile neanche così.

**Correzione:**
```python
orig_leverage = leverage
orig_margin = margin

# Prova a ridimensionare
while estimated_risk > remaining_risk_budget and leverage > 1:
    leverage = leverage - 1
    # ricalcola margine basato su rischio target
    margin = risk_trade_usd / ((stop_pct + cost_pct) * leverage)
    margin = max(wallet_spec.min_margin, min(margin, wallet_spec.max_margin))
    estimated_risk = margin * leverage * stop_pct + cost_pct * margin * leverage

if estimated_risk > remaining_risk_budget:
    return reject('below_min_margin_after_resize', {
        'orig_leverage': orig_leverage,
        'orig_margin': orig_margin,
        'remaining_budget': remaining_risk_budget
    })

# Piano ridimensionato: registra la modifica
if leverage != orig_leverage:
    log_event('plan_resized', {
        'symbol': symbol,
        'orig_leverage': orig_leverage,
        'new_leverage': leverage,
        'orig_margin': orig_margin,
        'new_margin': margin
    })
```

Includere gli ultimi 5 ridimensionamenti nel prompt AI successivo (così l'AI capisce i vincoli reali).

**Test**: piano 250$ a 45x con stop 2%, budget residuo 30$ → ridimensionato; se anche al minimo supera il budget → rifiuto `below_min_margin_after_resize`.

---

#### B2 — Buco di candela blocca il simbolo per sempre
**File**: il problema è in `brain_free/execution.py` righe ~200 e ~61, ma NON toccare quel file.

**Dove correggere**: nel `coordinator.py` Brain Scalp (o in un supervisore da creare), prima di chiamare il tick:

```python
# Prima del tick per ogni simbolo:
missing_gaps = detect_gaps_in_candle_series(candles_1m[symbol])
if missing_gaps:
    for gap in missing_gaps:
        try:
            backfill = fetch_candles_rest(
                symbol=symbol,
                start_ms=gap.start_ms,
                end_ms=gap.end_ms
            )
            if is_contiguous(backfill, gap):
                candles_1m[symbol] = merge_candles(candles_1m[symbol], backfill)
                log_event('gap_backfilled', {'symbol': symbol, 'gap': gap})
            else:
                log_event('gap_unresolvable', {'symbol': symbol, 'gap': gap})
                # lascia coverage_gaps: il simbolo resta bloccato finché non si risolve
        except Exception as e:
            log_event('gap_backfill_failed', {'symbol': symbol, 'error': str(e)})
```

Nota Code: anche un buco *dentro* la serie (stop di quel minuto non controllato) è coperto da questo backfill se avviene prima del tick.

**Test**: posizione aperta su un simbolo, feed riparte con una candela mancante → backfill OK → `coverage_gaps` non cresce → nuovo piano accettato.

---

### GRUPPO 3 — Stop giornaliero e protezione profitto (I5, I1) — priorità alta

Aspetta OK dell'utente dopo il Gruppo 2 prima di iniziare questo.

---

#### I5 — Stop giornaliero non latched + config_hash fisso
**File**: `backend/director/brain_scalp/engine.py` righe ~76-77 e `store.py` righe ~46, 70

**Problema A** (stop giornaliero): lo stop giornaliero si disattiva appena l'equity risale. Deve restare attivo per tutto il giorno UTC e riattivarsi il giorno dopo.

**Correzione stop giornaliero in engine.py:**
```python
def today_utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')

# Quando si raggiunge lo stop:
if daily_drawdown >= wallet_spec.daily_stop_pct:
    state['daily_stop_triggered'] = True
    state['daily_stop_day'] = today_utc()
    log_event('daily_stop_latched', {
        'drawdown_pct': daily_drawdown,
        'limit_pct': wallet_spec.daily_stop_pct,
        'day': today_utc()
    })

# Nella verifica aperture, ogni tick:
if state.get('daily_stop_triggered') and state.get('daily_stop_day') == today_utc():
    opening_allowed = False
    block_reason = 'daily_stop_latched'
# Al cambio di giorno UTC: sblocco automatico
elif state.get('daily_stop_day') != today_utc():
    state['daily_stop_triggered'] = False  # nuovo giorno, si azzera
```

**Problema B** (config_hash): è una stringa fissa, non dipende dai parametri reali. Se i parametri cambiano (es. `max_margin` da 250 a 300), il motore non lo rileva e usa il vecchio stato.

**Correzione config_hash in store.py:**
```python
import hashlib, json

def wallet_spec_digest(spec):
    """Hash deterministico dei parametri chiave del wallet."""
    d = {k: getattr(spec, k) for k in [
        'slots', 'min_margin', 'max_margin', 'max_margin_total',
        'risk_trade_usd', 'risk_portfolio_usd',
        'daily_stop_pct', 'kill_equity'
    ]}
    return hashlib.sha256(
        json.dumps(d, sort_keys=True).encode()
    ).hexdigest()[:16]

# All'avvio, confrontare con il digest salvato:
saved_digest = state.get('config_hash')
current_digest = wallet_spec_digest(wallet_spec)
if saved_digest and saved_digest != current_digest:
    raise RuntimeError(
        f"Config cambiata senza migrazione dello stato! "
        f"Salvato: {saved_digest}, Attuale: {current_digest}. "
        f"Azzerare manualmente lo stato o aggiornare config_hash."
    )
state['config_hash'] = current_digest
```

**Test**: equity scende sotto lo stop → stop latched → equity risale → aperture ancora bloccate → mezzanotte UTC → aperture sbloccate.

---

#### I1 — Protezione profitto incompleta
**File**: `backend/director/brain_scalp/engine.py` righe ~90-91

**Problema**: il giveback esce solo se `net > 0`. Un ritorno brusco da profitto (+5$) a perdita (-2$) non viene protetto. Mancano break-even automatico e trailing.

**Correzione in tre passi (in quest'ordine):**

*Passo 1 — Break-even netto automatico:*
```python
# Dopo che peak_net >= protect_after_usd (la posizione è entrata in profitto):
if peak_net >= protect_after_usd and not position.get('breakeven_set'):
    entry_cost_pct = config.FEE_PCT + config.SLIPPAGE_PCT
    if position['side'] == 'long':
        breakeven_price = position['entry'] * (1 + entry_cost_pct)
    else:
        breakeven_price = position['entry'] * (1 - entry_cost_pct)
    
    # Sposta stop a breakeven solo se non è già oltre
    current_stop = position.get('stop_price')
    if position['side'] == 'long' and (current_stop is None or breakeven_price > current_stop):
        position['stop_price'] = breakeven_price
        position['breakeven_set'] = True
        log_event('breakeven_set', {'symbol': symbol, 'breakeven': breakeven_price})
    elif position['side'] == 'short' and (current_stop is None or breakeven_price < current_stop):
        position['stop_price'] = breakeven_price
        position['breakeven_set'] = True
        log_event('breakeven_set', {'symbol': symbol, 'breakeven': breakeven_price})
```

*Passo 2 — Giveback anche se net ≤ 0:*
```python
# Rimuovere la condizione `net > 0` dalla guardia del giveback.
# Il giveback scatta se siamo scesi dal picco di oltre il 35%, INDIPENDENTEMENTE dal segno di net:
if peak_net >= protect_after_usd and net <= peak_net * 0.65:
    close(position, reason='giveback', meta={
        'peak_net': peak_net,
        'current_net': net,
        'giveback_pct': (peak_net - net) / abs(peak_net) if peak_net != 0 else 0
    })
```

*Passo 3 — Schema del piano: aggiungere campi opzionali:*
```python
# In plans.py, schema del piano (tutti opzionali, default None):
{
    # ...campi esistenti...
    'breakeven_after_usd': None,  # float | None — se None usa protect_after_usd
    'trail_bps': None,            # int | None — trailing in basis points (es. 10 = 0.10%)
    'scale_out': None,            # list | None — uscita parziale per livelli
                                  #   formato: [{'net_usd': float, 'fraction': float}]
    'invalidate_price': None      # float | None — chiude se attraversato PRIMA del trigger
}
```

Il motore valuta `invalidate_price` a ogni tick: se attraversato prima del trigger → annulla il piano; dopo l'ingresso → chiude la posizione.

**Test**: posizione con picco +3.5$, poi quota che porta net a -2$ → giveback; con break-even attivo, lo stop impedisce che net scenda sotto -costi_ingresso.

---

### GRUPPO 4 — Risposta AI e bug trovati da Code (I6, 3 bug Code) — importante per la profittabilità

Aspetta OK dell'utente dopo il Gruppo 3 prima di iniziare questo.

---

#### I6 — Risposta AI malformata fa perdere piani validi
**File**: `backend/director/brain_scalp/coordinator.py` righe ~35, 43 e `plans.py` righe ~40-44

**Problema**: un solo piano malformato in una risposta AI fa rifiutare l'intera risposta; `symbol` non hashable solleva `TypeError` fuori dal try; `created_ms` e `plan_id` vengono dal modello AI (non sicuro).

**Correzione:**
```python
# In coordinator.py, processare piano per piano:
accepted_plans = []
rejected_plans = []

for raw_plan in ai_response.get('plans', []):
    try:
        plan = validate_plan(raw_plan)
        # Timestamp e ID li assegna il motore, non il modello
        plan['created_ms'] = now_ms()
        plan['plan_id'] = generate_plan_id()
        accepted_plans.append(plan)
    except Exception as e:
        rejected_plans.append({'raw': raw_plan, 'error': str(e)})
        log_event('ai_plan_rejected', {'raw': raw_plan, 'error': str(e)})

# Procedere con i piani accettati anche se alcuni sono stati rifiutati
for plan in accepted_plans:
    submit_plan(plan)

log_event('ai_response_processed', {
    'accepted': len(accepted_plans),
    'rejected': len(rejected_plans)
})
```

---

#### [Code] Piano con prezzo già sopra il trigger: ingresso immediato al prezzo sbagliato
**File**: `backend/director/brain_scalp/engine.py` (validazione del piano al trigger)

**Problema trovato da Code**: "compra quando supera 100" con prezzo già a 101.2 → il motore apre subito a 101.2, stop finisce a 1.70% invece dello 0.5% pianificato.

**Correzione** (alla ricezione del piano, prima di accettarlo):
```python
MAX_ENTRY_OVERSHOOT = 0.0005  # 0.05% oltre il trigger è tollerabile (fee)

if plan['side'] == 'long':
    if current_price > plan['trigger_price'] * (1 + MAX_ENTRY_OVERSHOOT):
        return reject('trigger_already_breached', {
            'trigger': plan['trigger_price'],
            'current': current_price,
            'overshoot_pct': round(
                (current_price - plan['trigger_price']) / plan['trigger_price'] * 100, 4
            )
        })
elif plan['side'] == 'short':
    if current_price < plan['trigger_price'] * (1 - MAX_ENTRY_OVERSHOOT):
        return reject('trigger_already_breached', {
            'trigger': plan['trigger_price'],
            'current': current_price,
            'overshoot_pct': round(
                (plan['trigger_price'] - current_price) / plan['trigger_price'] * 100, 4
            )
        })
```

**Test**: piano long "compra sopra 100" con prezzo a 101.2 → rifiuto `trigger_already_breached`.

---

#### [Code] Stop dentro il rumore: perdita certa
**File**: `backend/director/brain_scalp/engine.py` (validazione stop)

**Problema trovato da Code**: stop allo 0.04% con costi 0.16% → se scatta lo stop, la perdita effettiva è 4.5× lo stop nominale. Il motore accetta questi piani.

**Correzione** (nella validazione del piano):
```python
stop_pct = abs(plan['trigger_price'] - plan['stop_price']) / plan['trigger_price']
cost_pct = (config.FEE_PCT + config.SLIPPAGE_PCT) * 2  # round-trip

if stop_pct < cost_pct:
    return reject('stop_inside_noise', {
        'stop_pct': round(stop_pct * 100, 4),
        'cost_pct': round(cost_pct * 100, 4),
        'ratio': round(cost_pct / stop_pct, 2),
        'min_stop_pct': round(cost_pct * 100, 4)
    })
```

**Test**: piano con stop 0.04%, costi 0.16% → rifiuto `stop_inside_noise`.

---

#### [Code] Stop giornaliero accetta piani durante il blocco
**File**: `backend/director/brain_scalp/engine.py` (funzione `submit`)

**Problema trovato da Code**: durante lo stop giornaliero il wallet accetta piani e prenota slot/margine. Il blocco è solo sulle aperture effettive, non sulla prenotazione.

**Correzione** (in `submit()`, prima di prenotare qualsiasi risorsa):
```python
def submit(self, plan, state):
    # Controllo opening_allowed PRIMA di prenotare slot e margine
    if not state.get('opening_allowed', True):
        return reject('opening_not_allowed', {
            'reason': state.get('block_reason', 'unknown'),
            'block_since': state.get('block_since_ms')
        })
    
    # Solo qui prenotare slot e margine
    # ...
```

**Test**: stop giornaliero attivo → `submit()` con piano valido → rifiuto `opening_not_allowed`, nessun slot prenotato.

---

### GRUPPO 5 — Osservabilità (I9, I7) — importante per valutare i test

Aspetta OK dell'utente dopo il Gruppo 4 prima di iniziare questo.

---

#### I9 — state['metrics'] non viene mai aggiornato
**File**: `backend/director/brain_scalp/engine.py` righe ~131-134

**Problema**: il campo `metrics` nel state non viene mai aggiornato durante il tick. Le dashboard mostrano dati vuoti o stantii.

**Correzione** (alla fine di ogni tick, prima di salvare lo state):
```python
state['metrics'] = {
    'ts_ms': now,
    'opening_allowed': opening_allowed,
    'block_reason': block_reason or None,
    'slots_used': len(positions),
    'slots_free': wallet_spec.slots - len(positions),
    'margin_used': sum(p['margin'] for p in positions.values()),
    'margin_available': wallet_spec.max_margin_total - sum(p['margin'] for p in positions.values()),
    'equity': equity_now,
    'pnl_realized_usd': state.get('pnl_realized_usd', 0),
    'fee_paid_usd': state.get('fee_paid_usd', 0),
    'trades_today': state.get('trades_today', 0),
    'long_count': sum(1 for p in positions.values() if p['side'] == 'long'),
    'short_count': sum(1 for p in positions.values() if p['side'] == 'short'),
    'avg_duration_min': avg_duration_min,
    'minutes_at_zero_positions': state.get('minutes_at_zero_positions', 0),
}
```

---

#### I7 — PWA indisponibile con writer fermo
**File**: `backend/director/brain_scalp/` (worker/writer) e `brain_scalp_view.py`

**Problema**: se il writer SQLite si ferma, la PWA smette di aggiornarsi. Il mount SQLite in sola lettura non funziona bene in certi setup.

**Correzione** — snapshot JSON atomico ogni 5 secondi:
```python
import os, json

SNAPSHOT_PATH = '/opt/superbot-desk-data/brain_scalp_snapshot.json'

def write_snapshot(hawk_state, bull_state):
    """Snapshot atomico: scrivi su .tmp poi rename (atomico su Linux)."""
    snapshot = {
        'ts_ms': now_ms(),
        'hawk': {
            'metrics': hawk_state.get('metrics', {}),
            'positions': list(hawk_state.get('positions', {}).values()),
            'state_summary': {
                'opening_allowed': hawk_state.get('opening_allowed'),
                'block_reason': hawk_state.get('block_reason'),
                'equity': hawk_state.get('equity')
            }
        },
        'bull': {
            'metrics': bull_state.get('metrics', {}),
            'positions': list(bull_state.get('positions', {}).values()),
            'state_summary': {
                'opening_allowed': bull_state.get('opening_allowed'),
                'block_reason': bull_state.get('block_reason'),
                'equity': bull_state.get('equity')
            }
        }
    }
    tmp_path = SNAPSHOT_PATH + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(snapshot, f)
    os.replace(tmp_path, SNAPSHOT_PATH)  # atomico su Linux

# Nel loop principale del worker:
SNAPSHOT_INTERVAL_S = 5
last_snapshot = 0
while True:
    # ...tick...
    if time.time() - last_snapshot >= SNAPSHOT_INTERVAL_S:
        write_snapshot(hawk_state, bull_state)
        last_snapshot = time.time()
```

La PWA legge lo snapshot JSON invece del SQLite direttamente. Funziona anche con writer fermo (il JSON è già scritto) e con mount in sola lettura.

---

### GRUPPO 6 — Incoerenze di capitale (I8) — IN ATTESA DI DECISIONE DELL'UTENTE

**⚠️ NON IMPLEMENTARE** questo gruppo finché l'utente non sceglie un'opzione.

**Problema**: le configurazioni di Hawk e Bull hanno margini che, al massimo utilizzo, superano il capitale disponibile (1000$).

Presenta all'utente queste tre opzioni e aspetta la risposta:

**Opzione A (margini minimi più bassi)**:
- Hawk: `min_margin = 90$` (invece di 100$) → 10 slot × 90$ = 900$ + fee, entra nel budget
- Bull: `max_margin = 316$` (invece di 350$) → 3 slot × 316$ = 948$, entra nel budget

**Opzione B (budget totale fisso)**:
- Entrambi: `max_margin_total = 980$` (budget complessivo per slot)
- La logica di allocazione si adatta ai margini dei piani attivi

**Opzione C (comportamento dichiarato, nessuna modifica)**:
- Accettare che Hawk usi al massimo 9 slot a taglia minima quando il budget è esaurito
- Bull può avere due posizioni grandi e una media
- Aggiornare solo la documentazione/commenti per dichiararlo esplicitamente

---

### REPLAY — cosa fare con l'harness

**Situazione attuale**: i dati sono pronti (17 simboli × 86.400 candele 1m), l'harness Python è nel file `replay.py` dello zip `replay-input-60d-2026-10-28.zip`. Il replay precedente si è fermato dopo 45 minuti senza output.

**Perché si è fermato**: nessun checkpoint → nessun output intermedio → non si sa dove era arrivato. Non è un crash.

**Modifica da fare all'harness** (puramente tecnica, nessun cambio di strategia):
```python
# In replay.py, nel loop principale:
import json, os

CHECKPOINT_PATH = 'replay_checkpoint.json'

def save_checkpoint(series_idx, series_results_so_far):
    tmp = CHECKPOINT_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump({'series_idx': series_idx, 'results': series_results_so_far}, f)
    os.replace(tmp, CHECKPOINT_PATH)

def load_checkpoint():
    if os.path.exists(CHECKPOINT_PATH):
        with open(CHECKPOINT_PATH) as f:
            return json.load(f)
    return None

# All'inizio del loop per le serie:
checkpoint = load_checkpoint()
start_series = checkpoint['series_idx'] + 1 if checkpoint else 0
results_so_far = checkpoint['results'] if checkpoint else []

for series_idx in range(start_series, N_SERIES):
    result = run_series(series_idx, ...)
    results_so_far.append(result)
    save_checkpoint(series_idx, results_so_far)
    print(f"Serie {series_idx+1}/{N_SERIES} completata: {result['summary']}")
```

**Procedura per il prossimo replay** (eseguire dall'utente dal suo PC Windows):
1. Attendere che i Gruppi 1-3 siano corretti e la CI sia verde
2. Modificare `replay.py` con il checkpoint come sopra
3. Eseguire SOLO il periodo DEV (11 giorni, i primi 11 giorni del dataset) per misurare la velocità
4. Se è ragionevole (< 10 minuti), procedere con VAL poi TEST
5. **TEST si esegue UNA SOLA VOLTA** — mai iterare sui parametri contro TEST

---

## ORDINE DI LAVORO COMPLETO

| Step | Azione | Chi | Quando |
|------|--------|-----|--------|
| 1 | Gruppo 1 (B3a, B3b, B3c, I4) | ChatGPT | Adesso |
| 2 | CI verde + conferma utente | Utente | Dopo step 1 |
| 3 | Gruppo 2 (I2, I3, B2) | ChatGPT | Dopo step 2 |
| 4 | CI verde + conferma utente | Utente | Dopo step 3 |
| 5 | Gruppo 3 (I5, I1) | ChatGPT | Dopo step 4 |
| 6 | CI verde + conferma utente | Utente | Dopo step 5 |
| 7 | Gruppo 4 (I6, 3 bug Code) | ChatGPT | Dopo step 6 |
| 8 | CI verde | — | Dopo step 7 |
| 9 | Gruppo 5 (I9, I7) | ChatGPT | Dopo step 8 |
| 10 | Aggiungi checkpoint a replay.py | ChatGPT | Dopo step 9 |
| 11 | Utente sceglie opzione A/B/C per I8 | Utente | Quando vuole |
| 12 | Gruppo 6 (I8) | ChatGPT | Dopo step 11 |
| 13 | Replay DEV (11 giorni) | Utente dal PC | Dopo step 9 |

**Dopo ogni gruppo**: aggiorna `STATO.md` e la voce di diario del giorno con commit `[skip ci]`, poi aspetta OK dell'utente.

---

## COSA NON FARE

- ❌ Non modificare `brain_free/execution.py` né `brain_free/config.py` — le correzioni B3 e I4 vanno nel codice scalp, non nel codice condiviso con Brain Free V2 in produzione (eccezione: la correzione B3a può toccare `execution.py` se lo ritieni sicuro, ma comunicalo prima)
- ❌ Non aggiungere la connessione AI al loop prima di aver completato i Gruppi 1-3 e i relativi test
- ❌ Non fare deploy (niente restart container, niente push su `rule-pool`) senza OK esplicito dell'utente
- ❌ Non cambiare parametri di strategia (target%, stop%, min_margin, max_margin, slots) — questo spetta all'utente dopo i dati del replay
- ❌ Non fare `git push --force`
- ❌ Non unire i rami motore e app
- ❌ Non toccare i bot classici (`backend/desk/`)
- ❌ Non toccare HI-TV / `hitvprime`
- ❌ Non inserire API key, saldi o importi reali nei commit
- ❌ Non eseguire il replay — lo esegue l'utente dal suo PC Windows

---

## RIEPILOGO: I 5 BUG PIÙ CRITICI (priorità assoluta)

1. **B3b** — Orologio indietro blocca le protezioni → posizioni in perdita non vengono chiuse
2. **B3a** — `equity()` con `price=None` → crash del motore su dati sporchi
3. **[Code] Stop dentro il rumore** — stop 0.04% con costi 0.16% → perdita certa
4. **I5** — Stop giornaliero non latched → limite di perdita giornaliero non funziona
5. **[Code] Trigger già attraversato** — ingresso immediato a prezzo sbagliato

Il bug più importante per la **profittabilità** (non per la sicurezza) è **I6 + Code scanner**: lo scanner non passa ATR/livelli/volume all'AI e ripete lo stesso segnale 5×. L'AI è cieca. Questo è nel Gruppo 4, ma tienilo presente perché è la radice del problema di qualità dei segnali.

---

*Documento preparato da Claude (chat) il 29/10/2026.*
*Repository: alexiptv82/SuperBot-Trading (pubblico)*
*Ramo motore: work/brain-scalp-dual-20261028 @ d96d171*
*Ramo app: work/brain-scalp-dual-app-20261028 @ 320de78*
