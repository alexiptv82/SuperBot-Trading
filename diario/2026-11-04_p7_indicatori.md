# 2026-11-04 (pomeriggio) — P7: indicatori a barre chiuse (PR #47, bozza)

**Claude Sonnet 5.5 — coordinatore tecnico** · modulo: codice di Grok (Modalità B: consegna come testo, applicata invariata) · funzioni pure, nessun collegamento col Brain, col journal, coi prompt, con soglie o limiti

`backend/v3/features/indicators.py`: EMA/RMA, true range, ATR, RSI, MACD, Bollinger, Donchian, ADX su barre **chiuse**, `Decimal` a 60 cifre in contesto locale, nessun look-ahead (il valore alla posizione `i` dipende solo dalle barre `0..i`). Servono a etichettare a posteriori i segnali delle schede della biblioteca L0 e ad alimentare expectancy/walk-forward (P4–P6).

## Cosa ho trovato
Le **formule di Grok sono giuste**: ogni valore di ogni serie coincide con un oracolo `Fraction` in forma chiusa (algoritmi diversi dal modulo), con `backend/strategy_lab.py` e con pandas. Tre difetti, tutti corretti in un commit separato (contratto invariato):
1. **Eccezione grezza** `decimal.Overflow` da prezzi ≥ `1E+999999` in 9 funzioni su 10 (contratto: `ValueError("numeric_out_of_range")`).
2. **Valori sbagliati in silenzio**: `Underflow` non intercettato (il contesto ereditava i trap di `DefaultContext`); a prezzi minuscoli quasi tutte le funzioni restituivano zeri come se fossero risultati validi, e `bollinger` già da `1E-600000` bande a larghezza zero. Ora `_CTX` fissa tutto e ogni funzione converte `ArithmeticError`.
3. **`adx` O(N²)**: 24 s per 4000 barre → 0,045 s (20 000 barre: 0,22 s). Sullo storico previsto (~245 000 barre a 15m su 7 anni) erano ore.
Più la consegna: 8 test, mutanti/oracolo/confronto col laboratorio "NON ESEGUITO".

## Verifica
- Suite V3 **1647 → 2260 passed** (+613: 605 miei + 8 di Grok), 3 xfailed; 3 failed per `fastapi` mancante, invariati. Passa dalla radice e da `cd /tmp`.
- Oracolo su 61 dataset validi con guardie; vettori calcolati a parte; non-lookahead su tutte le 19 serie con meta-test; scale estreme per invarianza di scala (corretto o errore tipizzato, mai eccezione grezza né valore sbagliato; sul modulo originale falliscono); validazione esaustiva con ordine degli errori; contesto ambientale; forma; purezza AST; confronto col laboratorio e con pandas (tolleranza 1e-9).
- **Mutazione 199/223** su una copia del repo (nessun mutante mai nell'albero di lavoro): i 24 sopravvissuti sono equivalenti (3 su `donchian` che non fa aritmetica, 2 ridondanti su `true_range`, `I10`, `M11`, 17 `_nz` irraggiungibili: strumentando `_nz`, `-0` arriva solo da `ema`/`rma`). 10 sopravvissuti della prima passata erano buchi nei miei test, corretti. **I soli 8 test di Grok: 28/223.**

## Limiti
Primi valori di EMA/RMA dipendono dall'inizializzazione col primo dato; i buchi nelle barre si rifiutano (il caricatore dello storico deve spezzare i dati); `volume` validato ma non usato; prezzi fra `1E-100000` e `1E+100000` supportati, oltre risultato corretto oppure `numeric_out_of_range`; nessun dato reale usato.

## Prossimo
- **Grok — P7b** (`v3/features/levels.py`: supertrend, percentile dell'ATR, VWAP di sessione, range d'apertura, livelli di swing): prompt pronto `claude/prompt-grok-p7b-livelli-2026-11-04.md`. Con P7 + P7b le 12 schede "solo candele" diventano calcolabili.
- In attesa di Grok: **P6** walk-forward (`learning/walkforward.py`).
- Poi: P8 regime (parametri obbligatori), rilevatori delle schede, laboratorio su storico BTC/ETH in CI.
- Decisioni dell'utente ancora aperte (non bloccano): politica di esplorazione del Brain in PAPER; tocchi ambigui stop/target (`stop_first` consigliato); L1 (`strategy_id` nel journal) e L4 (short-list nel prompt) richiedono OK esplicito; backup F0 e import dei trade legacy.

⛔ Nessun merge/deploy · `DESK_MODE=paper` · Hawk/Bull non toccati · cervello intatto.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012yPu2eVVWT2jkKwTyuh3So
