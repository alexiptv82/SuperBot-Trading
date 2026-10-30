# Fase GRIGLIA (E3) - solo metriche strutturali, nessun rendimento dei trade

Regola di scelta (fissata prima): S0a, S0b, S0d e D1, D2, D3 tutti veri; la piu' vicina a v2.0, poi ritardo D1 piu' basso. **Scelta: NESSUNA -> lettore non idoneo, il laboratorio si ferma**

| configurazione | S0a (max stato) | S0b | S0d (durata mediana) | D1 (ritardo v2/EMA) | D2 (lift; cambi/giorno) | D3 (rilevate vs placebo p95) | tutti |
|---|---|:-:|---|---|---|---|:-:|
| c2_w60_k25_d20 (v2.0) | no (62%) | si | no (6) | no (+0.70) | no (+1.12; 1.36) | si (80% vs 60%) | **no** |
| c2_w60_k25_d30 | no (62%) | si | si (10) | no (+0.80) | no (+1.07; 0.92) | si (77% vs 58%) | **no** |
| c2_w60_k15_d20 | si (43%) | si | no (6) | no (+0.56) | si (+1.15; 1.99) | si (94% vs 74%) | **no** |
| c2_w60_k15_d30 | si (43%) | si | si (9) | no (+0.67) | no (+1.08; 1.36) | si (91% vs 73%) | **no** |
| c2_w30_k25_d20 | no (61%) | si | si (8) | no (+0.71) | no (+1.07; 1.22) | si (81% vs 61%) | **no** |
| c2_w30_k25_d30 | no (61%) | si | si (12) | no (+0.77) | no (+1.08; 0.75) | si (80% vs 59%) | **no** |
| c2_w30_k15_d20 | si (42%) | si | si (8) | no (+0.59) | no (+1.09; 1.78) | si (96% vs 78%) | **no** |
| c2_w30_k15_d30 | si (42%) | si | si (14) | no (+0.68) | no (+1.07; 1.11) | si (94% vs 75%) | **no** |
| c4_w60_k25_d20 | no (63%) | no | si (16) | no (+0.73) | no (+0.98; 0.86) | si (82% vs 64%) | **no** |
| c4_w60_k25_d30 | no (62%) | si | si (16) | no (+0.80) | no (+1.02; 0.54) | si (80% vs 57%) | **no** |
| c4_w60_k15_d20 | si (44%) | si | si (16) | no (+0.55) | no (+1.03; 1.25) | si (96% vs 76%) | **no** |
| c4_w60_k15_d30 | si (43%) | si | si (16) | no (+0.70) | no (+1.04; 0.78) | si (93% vs 70%) | **no** |
| c4_w30_k25_d20 | no (62%) | si | si (16) | no (+0.73) | no (+1.00; 0.87) | si (84% vs 64%) | **no** |
| c4_w30_k25_d30 | no (61%) | si | si (16) | no (+0.80) | no (+1.04; 0.55) | si (80% vs 58%) | **no** |
| c4_w30_k15_d20 | si (43%) | si | si (16) | no (+0.59) | no (+1.01; 1.27) | si (96% vs 78%) | **no** |
| c4_w30_k15_d30 | si (43%) | si | si (16) | no (+0.72) | no (+1.06; 0.83) | si (94% vs 72%) | **no** |
