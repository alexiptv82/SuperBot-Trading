# Diario Claude — 26 ottobre 2026 (turno sera)

## Contesto: diagnosi performance e fix segnali

L'utente ha segnalato che Bull ha perso molto oggi: ha aperto solo SHORT in una giornata
di rimbalzo. Ha anche segnalato che un portafoglio si è fermato per limite di perdita
giornaliero. L'utente sospettava che il fix dei LONG non fosse completamente operativo.

## Diagnosi

### Causa principale: formula stagionale moltiplicativa invertita

In `seasonal.py` la formula originale era:
```python
effective = monthly_bias * cycle_mult
```
Con ottobre 2026 a mese 30 dal halving (`cycle_mult = -1.0`, fase "bear market"):
```
22% × (-1.0) = -22 → short_bonus = 5
```
Il sistema dava **5 SHORT** a BTC in ottobre, il mese storicamente **più bullish** (+22%).

Combinato con il P1 fix (RSI 30-50 → +8 SHORT), il totale era fino a **13 SHORT** di
bias nella scoring — sufficiente a superare la soglia di confidence su segnali neutri.

### Causa secondaria: daily loss limit inattivo in paper mode

```python
def _daily_loss_exceeded(acc) -> bool:
    if not LIVE._live:
        return False   # ← bypass totale in paper
```
Il daily stop non funzionava mai in paper, consentendo perdite illimitate nella sessione.

### Analisi report 4 AI esterne

L'utente ha raccolto report da DeepSeek, Kimi 3, Grok 4.7 e ChatGPT 6.
Tutti e 4 hanno identificato il problema della formula moltiplicativa.
Punti di sintesi adottati:
- Formula additiva pesata (ChatGPT 6): `0.60 × monthly + 0.40 × cycle`
- Curva smooth interpolata (Grok 4.7): mese 30 = −0.40 invece di −1.0
- market_factor (Grok): se BTC va contro il prior, riduce/azzera il bonus
- DailyGuard + open risk cap (DeepSeek + Kimi): blocca la 2a posizione Bull

## Implementazione (branch `ccr-999de027-0stnyt`, commit `767bee0`)

### `backend/desk/seasonal.py` — riscrittura formula

Nuovi meccanismi:
1. **Formula additiva**: `effective = 0.60 × tanh(monthly/22) + 0.40 × smooth_cycle(months)`
2. **Curva ciclo smoothed** (`_CYCLE_ANCHORS`): interpolazione lineare su 12 ancore.
   Mese 30 = −0.40 (era −1.0); mai un singolo valore -1.0 che inverte tutto.
3. **market_factor**: se `btc_return_3d` va >3% contro il prior → bonus azzerato;
   >1.5% → dimezzato.
4. Retrocompatibile: `get_seasonal(symbol, now_ms)` invariato.

Risultato ottobre 2026: **5 LONG** (era 5 SHORT) — swing di 10 punti sul segnale.

### `backend/desk/signals.py` — passaggio market_factor

`read_symbol(symbol, arr15, now_ms, btc_return_3d=None)` — parametro opzionale.
`get_seasonal(symbol, now_ms, btc_return_3d=btc_return_3d)` — attiva il market_factor.

### `backend/desk/cli.py` — guardrail Bull + daily stop paper

1. **`_daily_loss_exceeded`**: rimosso bypass paper mode.
   Usa `_PAPER_DAILY_LOSS_LIMIT = start_equity × daily_loss_pct` in paper.
2. **`_open_sl_risk(acc)`**: calcola perdita stimata SL aggregata delle posizioni aperte.
3. **`BULL_MAX_OPEN_RISK_USD = 160$`** (env `DESK_BULL_MAX_OPEN_RISK`):
   blocca la 2a apertura Bull se open_risk + planned_risk > 160$.
   ($350 × 15x × 3% SL ≈ $157.50 → 1 posizione piena già vicina alla soglia.)
4. **VETO_BULL_SHORT**: nessun nuovo SHORT su Bull se BTC +2% nelle 24h.
5. **`_btc_return_3d`** e **`_btc_ret_24h`** calcolati da candele BTC in `run_cycle`.

## Verifica sintattica e test formula

```
python -m py_compile backend/desk/seasonal.py  → OK
python -m py_compile backend/desk/signals.py   → OK
python -m py_compile backend/desk/cli.py       → OK

BTC ottobre 2026: long_bonus=5, short_bonus=0 (era short_bonus=5)
BTC oct + BTC -4% 3gg: long_bonus=0, short_bonus=0 (market_factor attivo)
```

## Stato dopo implementazione

- Branch: `ccr-999de027-0stnyt`, commit `767bee0`
- **NON deployato**: richiede OK esplicito utente (Regola 1)
- Nessuna modifica a engine.py, brain.py, prompt Claude
- Nessuna modifica a soglie R:R, confidence, leverage

## Task ancora aperti

Vedi STATO.md per lista aggiornata. Il punto successivo logico è il deploy del fix
(Regola 1: nessun redeploy senza OK utente).
