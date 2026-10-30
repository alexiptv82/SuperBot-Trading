# Fase STRUTTURALE - lettore di regime v2 (nessun rendimento dei trade usato)

Esecuzione: 2026-10-30 07:09 UTC | config `1c7dee868ad5` | iterazione strutturale n. 1 | 26 simboli, 1330756 barre 15m

- S0a occupazione mercato (max <= 60%): massimo 62% -> **FALLITO**
- S0b quota ALIGNED sui trade, solo istanti e lati (8%-60%): market short 18% / long 15%; symbol short 25% / long 23%; combined short 13% / long 9% -> **OK**
- S0d stabilita' (mediana >= 8 barre): 6 barre 15m (minimo 8) -> **FALLITO**
- **Accettazione strutturale (S0a, S0b, S0d, D1, D2, D3 tutti veri): NO -> serve una correzione dichiarata (E2) oppure si procede e si dichiara il lettore come non idoneo**
- Stabilita': durata mediana di uno stato di mercato 6 barre 15m (quartili 3-15); per simbolo, mediana delle mediane 5 (quartili 3-12).
- Rilevamento svolte BTC+ETH: D1 **FALSO**, D2 **FALSO**, D3 **VERO** | {"median_lag_v2": 45.0, "median_lag_ema": 64.0, "ratio": 0.703, "lift_v2": 1.122, "lift_ema": 1.027, "flips_per_day_v2": 1.36, "detect_rate_v2": 0.799, "detect_rate_placebo_p95": 0.603, "n_turns_both": 109, "n_turns": 194}

| stato di mercato | quota barre |
|---|---:|
| SHOCK | 0% |
| DOWN_CLEAN | 7% |
| DOWN_CHOP | 9% |
| TURNING_UP | 4% |
| RANGE | 62% |
| TURNING_DOWN | 3% |
| UP_CHOP | 8% |
| UP_CLEAN | 6% |
| EMERGING_DOWN | 0% |
| EMERGING_UP | 0% |

| simbolo | svolte | rilevate v2 (placebo p95) | rilevate EMA | ritardo mediano v2 / EMA | cambi/giorno v2 | lift v2 |
|---|---:|---|---:|---|---:|---:|
| BTC | 99 | 78% (60%) | 56% | +44.0 / +68.0 | 1.40 | +1.16 |
| ETH | 95 | 82% (61%) | 72% | +49.0 / +60.0 | 1.32 | +1.08 |

Occupazione per simbolo (primi 6): 
- BTC: DOWN_CLEAN 7%, DOWN_CHOP 8%, TURNING_UP 5%, RANGE 55%, TURNING_DOWN 5%, UP_CHOP 9%, UP_CLEAN 8%
- ETH: DOWN_CLEAN 8%, DOWN_CHOP 7%, TURNING_UP 4%, RANGE 57%, TURNING_DOWN 5%, UP_CHOP 8%, UP_CLEAN 9%
- BNB: DOWN_CLEAN 6%, DOWN_CHOP 8%, TURNING_UP 5%, RANGE 55%, TURNING_DOWN 6%, UP_CHOP 9%, UP_CLEAN 8%
- XRP: DOWN_CLEAN 8%, DOWN_CHOP 9%, TURNING_UP 6%, RANGE 55%, TURNING_DOWN 5%, UP_CHOP 7%, UP_CLEAN 7%
- SOL: DOWN_CLEAN 8%, DOWN_CHOP 9%, TURNING_UP 5%, RANGE 53%, TURNING_DOWN 5%, UP_CHOP 9%, UP_CLEAN 8%
- ADA: DOWN_CLEAN 9%, DOWN_CHOP 10%, TURNING_UP 6%, RANGE 54%, TURNING_DOWN 4%, UP_CHOP 7%, UP_CLEAN 7%
