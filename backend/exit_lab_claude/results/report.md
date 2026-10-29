# Laboratorio uscite/entrate classici (Claude) - RAPPORTO

Solo PAPER, solo offline, nessun dato di produzione toccato. Le entrate sono le 353 REALI degli archivi dei classici; si simulano solo le uscite (e, nella famiglia 'rimbalzo', il momento d'ingresso).

- Candele: granularita' **1m**, SHA256 dati `f39ef20a857b565052c6a82753650c3cb93aeb2b921575c2368060c7b4ef2082`
- Entrate usate: **353** (escluse 4 senza dati d'ingresso, 0 senza copertura candele >= 95%)
- Lato: **338 SHORT, 15 LONG**. Con cosi' pochi LONG questo test NON dice nulla sui LONG.
- Scarto massimo tra distanza stop ricalcolata e `entry_r_dist` dell'archivio: 0.00%

## 1. Gate di fedelta' (fissato prima di vedere i risultati)

Sul sottoinsieme semplice (uscita reale SL o TP, nessuna chiusura parziale): n = 290.

- Concordanza del tipo di uscita sim/reale: **98.6%** (soglia >= 85%)
- Differenza di P&L netto aggregato: **1.0%** della somma dei |net| reali (soglia <= 10%); sim 481.2 USD vs reale 367.1 USD
- **Esito: PASSATO**

Matrice reale -> simulato (conteggi):

| reale \ sim | SL | TP | TIME | LIQ |
|---|---:|---:|---:|---:|
| SL | 166 | 4 | 0 | 0 |
| TP | 0 | 120 | 0 | 0 |

## 2. Le entrate hanno un vantaggio direzionale? (placebo: stesse entrate, lato opposto)

| fase | n | R medio reale-lato | R medio lato-opposto | quota TP lato reale | quota TP lato opposto |
|---|---:|---:|---:|---:|---:|
| golden | 89 | 0.551 | -0.694 | 60.7% | 15.7% |
| crisi | 53 | -0.189 | 0.034 | 32.1% | 43.4% |
| dopo | 211 | -0.189 | -0.105 | 34.6% | 36.0% |
| tutte | 353 | -0.003 | -0.232 | 40.8% | 32.0% |

Se il lato opposto rende quanto (o piu') del lato reale in una fase, in quella fase le entrate non mostravano vantaggio direzionale e nessuna regola di uscita puo' crearlo.

## 3. Dopo uno stop dell'originale, il prezzo andava dove previsto? (la tua tesi)

Per ogni stop della variante base: nelle 6 ore successive il prezzo tocca prima il TP originale ('TP_first': uno stop piu' largo avrebbe salvato il trade) o prima uno stop a 2x ('STOP2_first': avrebbe perso di piu')?

| fase | stop base | TP_first | STOP2_first | neither |
|---|---:|---:|---:|---:|
| golden | 34 | 6 | 18 | 10 |
| crisi | 31 | 6 | 16 | 9 |
| dopo | 134 | 4 | 57 | 73 |
| tutte | 199 | 16 | 91 | 92 |

## 4. Confronto varianti (tutte sulle stesse entrate, costi inclusi)

R = guadagno in multipli della perdita pianificata allo stop (1R). `[S]` = stesso nozionale dell'originale (il rischio cresce con lo stop largo); `[R]` = nozionale ridotto in modo che la perdita allo stop resti 1R. R medio e' PER SEGNALE (le entrate non eseguite contano 0). Delta = differenza dal base, con intervallo al 95% (bootstrap a blocchi di 12 ore, approssimato e probabilmente ottimista). Per 'rimbalzo' il delta e' R medio per trade ESEGUITO della variante meno R medio di TUTTI i segnali del base (il confronto sugli stessi segnali sarebbe distorto: dove il prezzo ritraccia contro, l'entrata immediata parte male per costruzione, circa -p R, anche senza alcun vantaggio reale); 'base su mancati' e' il risultato medio che la base avrebbe avuto sui segnali saltati. Le varianti [R] con stop largo riducono il nozionale e quindi il peso dei costi per 1R: un delta positivo con R medio negativo NON e' un vantaggio, e' solo trading piu' piccolo in un contesto in perdita.

### Solo uscite

| variante | eseguite | R medio | delta [IC95] | golden | crisi | dopo | win% | peggior R | maxDD R | USD | cand. |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|:--:|
| uscite SL x2.0 TP x1.0 [S] | 353 | 0.060 | 0.063 [-0.121, 0.291] | 0.632 | 0.196 | -0.215 | 55% | -2.47 | 63.5 | 1506 |  |
| uscite SL x2.0 TP x1.0 [R] | 353 | 0.036 | 0.038 [-0.140, 0.243] | 0.328 | 0.099 | -0.104 | 55% | -1.23 | 31.4 | 847 |  |
| uscite SL x2.0 TP x0.75 [R] | 353 | -0.002 | 0.000 [-0.212, 0.221] | 0.276 | -0.007 | -0.119 | 60% | -1.23 | 34.4 | 529 |  |
| uscite SL x1.0 TP x1.0 [S] | 353 | -0.003 | 0.000 [0.000, 0.000] | 0.551 | -0.189 | -0.189 | 42% | -1.45 | 69.5 | 420 |  |
| uscite SL x1.5 TP x1.0 [R] | 353 | -0.010 | -0.008 [-0.100, 0.108] | 0.426 | -0.057 | -0.183 | 50% | -1.31 | 55.9 | 331 |  |
| uscite SL x1.5 TP x1.0 [S] | 353 | -0.013 | -0.011 [-0.137, 0.147] | 0.646 | -0.085 | -0.273 | 50% | -1.96 | 83.6 | 550 |  |
| uscite SL x2.0 TP x0.75 [S] | 353 | -0.013 | -0.011 [-0.167, 0.199] | 0.524 | -0.011 | -0.240 | 60% | -2.47 | 69.2 | 932 |  |
| uscite SL x2.0 TP x1.5 [R] | 353 | -0.032 | -0.029 [-0.199, 0.174] | 0.390 | 0.155 | -0.257 | 45% | -1.23 | 63.8 | -151 |  |
| uscite SL x1.0 TP x0.75 [S] | 353 | -0.037 | -0.035 [-0.140, 0.088] | 0.495 | -0.289 | -0.198 | 48% | -1.45 | 71.6 | 193 |  |
| uscite SL x1.5 TP x0.75 [R] | 353 | -0.043 | -0.041 [-0.188, 0.104] | 0.352 | -0.157 | -0.181 | 55% | -1.31 | 57.6 | 126 |  |
| uscite SL x1.0 TP x1.5 [S] | 353 | -0.044 | -0.042 [-0.176, 0.118] | 0.698 | -0.115 | -0.340 | 34% | -1.45 | 102.6 | -322 |  |
| uscite SL x2.0 TP x1.5 [S] | 353 | -0.056 | -0.054 [-0.306, 0.271] | 0.783 | 0.339 | -0.510 | 45% | -2.47 | 125.1 | -111 |  |
| uscite SL x2.0 TP x0.5 [R] | 353 | -0.058 | -0.056 [-0.311, 0.188] | 0.179 | -0.144 | -0.137 | 67% | -1.23 | 41.1 | -61 |  |
| uscite SL x1.5 TP x0.75 [S] | 353 | -0.062 | -0.059 [-0.166, 0.082] | 0.533 | -0.235 | -0.270 | 55% | -1.96 | 85.9 | 257 |  |
| uscite SL x1.5 TP x1.5 [R] | 353 | -0.091 | -0.088 [-0.198, 0.050] | 0.523 | -0.028 | -0.366 | 39% | -1.31 | 98.4 | -771 |  |
| uscite SL x1.5 TP x0.5 [R] | 353 | -0.103 | -0.101 [-0.312, 0.100] | 0.220 | -0.299 | -0.190 | 62% | -1.31 | 61.6 | -423 |  |
| uscite SL x2.0 TP x0.5 [S] | 353 | -0.120 | -0.118 [-0.288, 0.091] | 0.346 | -0.280 | -0.276 | 67% | -2.47 | 82.4 | -134 |  |
| uscite SL x1.5 TP x1.5 [S] | 353 | -0.128 | -0.126 [-0.333, 0.145] | 0.801 | -0.036 | -0.544 | 39% | -1.96 | 146.3 | -983 |  |
| uscite SL x1.0 TP x0.5 [S] | 353 | -0.136 | -0.133 [-0.320, 0.070] | 0.296 | -0.379 | -0.256 | 54% | -1.45 | 83.2 | -717 |  |
| uscite SL x1.5 TP x0.5 [S] | 353 | -0.151 | -0.148 [-0.301, 0.026] | 0.337 | -0.446 | -0.283 | 62% | -1.96 | 91.7 | -541 |  |

### Due gambe (stop largo fissato all'inizio)

| variante | eseguite | R medio | delta [IC95] | golden | crisi | dopo | win% | peggior R | maxDD R | USD | cand. |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|:--:|
| 2 gambe pull x0.75 SL x2.0 TP x1.0 [R] | 353 | -0.013 | -0.011 [-0.234, 0.243] | 0.235 | 0.032 | -0.130 | 57% | -1.29 | 36.6 | 393 |  |
| 2 gambe pull x0.5 SL x2.0 TP x1.0 [R] | 353 | -0.016 | -0.013 [-0.240, 0.239] | 0.214 | 0.077 | -0.136 | 57% | -1.27 | 36.8 | 260 |  |
| 2 gambe pull x0.3 SL x2.0 TP x1.0 [R] | 353 | -0.016 | -0.014 [-0.231, 0.225] | 0.226 | 0.087 | -0.144 | 57% | -1.25 | 37.3 | 253 |  |
| 2 gambe pull x0.75 SL x2.0 TP x1.0 [S] | 353 | -0.027 | -0.024 [-0.205, 0.229] | 0.363 | 0.052 | -0.212 | 57% | -2.10 | 59.7 | 575 |  |
| 2 gambe pull x0.5 SL x2.0 TP x1.0 [S] | 353 | -0.030 | -0.027 [-0.211, 0.235] | 0.368 | 0.127 | -0.237 | 57% | -2.22 | 64.8 | 438 |  |
| 2 gambe pull x0.3 SL x2.0 TP x0.75 [R] | 353 | -0.030 | -0.028 [-0.278, 0.215] | 0.207 | -0.029 | -0.130 | 63% | -1.25 | 36.7 | 247 |  |
| 2 gambe pull x0.3 SL x2.0 TP x1.0 [S] | 353 | -0.034 | -0.032 [-0.211, 0.217] | 0.411 | 0.156 | -0.270 | 57% | -2.32 | 70.2 | 381 |  |
| 2 gambe pull x0.5 SL x2.0 TP x0.75 [R] | 353 | -0.037 | -0.034 [-0.289, 0.222] | 0.189 | -0.035 | -0.132 | 63% | -1.27 | 37.2 | 175 |  |
| 2 gambe pull x0.75 SL x2.0 TP x0.75 [R] | 353 | -0.043 | -0.041 [-0.292, 0.212] | 0.166 | -0.065 | -0.126 | 63% | -1.29 | 36.8 | 124 |  |
| 2 gambe pull x0.3 SL x2.0 TP x0.75 [S] | 353 | -0.059 | -0.057 [-0.242, 0.173] | 0.370 | -0.053 | -0.242 | 63% | -2.32 | 68.0 | 408 |  |
| 2 gambe pull x0.5 SL x2.0 TP x0.75 [S] | 353 | -0.068 | -0.066 [-0.264, 0.174] | 0.313 | -0.062 | -0.231 | 63% | -2.22 | 64.8 | 277 |  |
| 2 gambe pull x0.75 SL x2.0 TP x0.75 [S] | 353 | -0.072 | -0.070 [-0.269, 0.163] | 0.255 | -0.101 | -0.203 | 63% | -2.10 | 59.1 | 203 |  |
| 2 gambe pull x0.3 SL x1.5 TP x1.0 [R] | 353 | -0.080 | -0.077 [-0.208, 0.071] | 0.313 | -0.077 | -0.246 | 51% | -1.34 | 68.7 | -437 |  |
| 2 gambe pull x0.5 SL x1.5 TP x1.0 [R] | 353 | -0.084 | -0.081 [-0.227, 0.084] | 0.303 | -0.096 | -0.244 | 51% | -1.37 | 68.3 | -456 |  |
| 2 gambe pull x0.75 SL x1.5 TP x1.0 [R] | 353 | -0.084 | -0.081 [-0.219, 0.073] | 0.326 | -0.160 | -0.238 | 51% | -1.41 | 68.5 | -318 |  |
| 2 gambe pull x0.3 SL x1.5 TP x0.75 [R] | 353 | -0.088 | -0.086 [-0.272, 0.089] | 0.274 | -0.190 | -0.215 | 57% | -1.34 | 64.5 | -312 |  |
| 2 gambe pull x0.5 SL x1.5 TP x0.75 [R] | 353 | -0.089 | -0.086 [-0.279, 0.113] | 0.252 | -0.202 | -0.205 | 58% | -1.37 | 62.3 | -279 |  |
| 2 gambe pull x0.75 SL x1.5 TP x1.0 [S] | 353 | -0.091 | -0.088 [-0.200, 0.057] | 0.375 | -0.179 | -0.265 | 51% | -1.58 | 76.6 | -279 |  |
| 2 gambe pull x0.5 SL x1.5 TP x1.0 [S] | 353 | -0.101 | -0.098 [-0.204, 0.057] | 0.389 | -0.120 | -0.302 | 51% | -1.71 | 84.9 | -489 |  |
| 2 gambe pull x0.3 SL x1.5 TP x1.0 [S] | 353 | -0.105 | -0.103 [-0.202, 0.045] | 0.430 | -0.104 | -0.332 | 51% | -1.81 | 92.6 | -549 |  |
| 2 gambe pull x0.5 SL x1.5 TP x0.75 [S] | 353 | -0.108 | -0.105 [-0.268, 0.080] | 0.323 | -0.252 | -0.253 | 58% | -1.71 | 77.2 | -263 |  |
| 2 gambe pull x0.75 SL x1.5 TP x0.75 [R] | 353 | -0.108 | -0.106 [-0.287, 0.067] | 0.229 | -0.246 | -0.216 | 57% | -1.41 | 66.0 | -470 |  |
| 2 gambe pull x0.3 SL x1.5 TP x0.75 [S] | 353 | -0.117 | -0.114 [-0.249, 0.047] | 0.375 | -0.256 | -0.289 | 57% | -1.81 | 86.6 | -361 |  |
| 2 gambe pull x0.75 SL x1.5 TP x0.75 [S] | 353 | -0.118 | -0.116 [-0.274, 0.048] | 0.264 | -0.274 | -0.240 | 57% | -1.58 | 73.5 | -443 |  |

### Entrata su ritracciamento/rimbalzo

| variante | eseguite | R medio | delta [IC95] | golden | crisi | dopo | win% | peggior R | maxDD R | USD | base su mancati | cand. |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|:--:|
| entrata limit finestra 30m ritracc. x0.5 | 71 | -0.064 | -0.317 [-0.782, 0.103] | 0.106 | -0.306 | -0.075 | 32% | -1.46 | 32.6 | -389 | 0.169 |  |
| entrata bounce finestra 30m ritracc. x0.5 | 57 | -0.075 | -0.465 [-0.965, 0.086] | 0.081 | -0.358 | -0.071 | 26% | -1.46 | 35.7 | -640 | 0.105 |  |
| entrata limit finestra 60m ritracc. x0.3 | 210 | -0.130 | -0.217 [-0.477, 0.020] | 0.125 | -0.155 | -0.232 | 34% | -1.46 | 67.2 | -1184 | 0.685 |  |
| entrata bounce finestra 30m ritracc. x0.3 | 129 | -0.144 | -0.392 [-0.726, -0.137] | -0.065 | -0.248 | -0.151 | 29% | -1.46 | 52.5 | -1411 | 0.297 |  |
| entrata limit finestra 30m ritracc. x0.3 | 148 | -0.146 | -0.346 [-0.662, -0.068] | 0.019 | -0.218 | -0.197 | 30% | -1.46 | 58.6 | -1450 | 0.393 |  |
| entrata limit finestra 60m ritracc. x0.5 | 138 | -0.150 | -0.381 [-0.701, 0.048] | 0.096 | -0.399 | -0.191 | 30% | -1.46 | 61.9 | -1337 | 0.484 |  |
| entrata bounce finestra 60m ritracc. x0.3 | 181 | -0.153 | -0.297 [-0.507, -0.107] | 0.051 | -0.240 | -0.218 | 31% | -1.46 | 67.4 | -1390 | 0.459 |  |
| entrata bounce finestra 60m ritracc. x0.5 | 107 | -0.156 | -0.512 [-0.851, -0.148] | 0.038 | -0.416 | -0.173 | 23% | -1.46 | 60.3 | -1391 | 0.302 |  |
| entrata limit finestra 180m ritracc. x0.3 | 256 | -0.165 | -0.225 [-0.464, 0.006] | 0.088 | -0.043 | -0.302 | 34% | -1.46 | 78.9 | -1314 | 1.041 |  |
| entrata bounce finestra 180m ritracc. x0.3 | 247 | -0.169 | -0.239 [-0.471, -0.036] | 0.014 | -0.139 | -0.254 | 34% | -1.46 | 73.1 | -1526 | 0.982 |  |
| entrata limit finestra 180m ritracc. x0.5 | 210 | -0.192 | -0.321 [-0.614, 0.044] | 0.072 | -0.170 | -0.309 | 31% | -1.46 | 81.7 | -1638 | 0.914 |  |
| entrata bounce finestra 180m ritracc. x0.5 | 201 | -0.209 | -0.365 [-0.653, -0.013] | -0.029 | -0.132 | -0.305 | 28% | -1.46 | 79.5 | -1834 | 0.810 |  |

## 5. Candidate secondo la regola fissata in anticipo

Una variante e' candidata solo se: (1) R medio per segnale > 0 dopo costi; (2) estremo inferiore dell'IC95 del delta vs base > 0 (per 'rimbalzo': per trade eseguito contro tutti i segnali del base); (3) delta > 0 in almeno 2 fasi su 3; (4) i 3 migliori trade pesano < 50% dei guadagni.

Nessuna variante soddisfa la regola.

## 6. Limiti

- Solo entrate SHORT in pratica; periodo 12-26/10 e mercato specifico; campione piccolo e correlato tra simboli.
- Le uscite reali includevano chiusure decise da AI/regole, parziali e talvolta seconde gambe: qui sono sostituite da SL/TP/tempo (24h). Il gate di fedelta' misura quanto questo e' accettabile.
- Nella stessa candela: liquidazione > stop > TP (caso peggiore). Stop a gap eseguito all'apertura.
- Seconda gamba: TP ricalcolato sul prezzo medio, TTL 3h (Hawk) / 12h (Bull) come il motore; ipotesi non verificabile sui dati.
- Nessun effetto di mercato delle proprie operazioni, nessun limite di slot o di cassa tra posizioni contemporanee.
