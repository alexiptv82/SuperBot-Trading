# Checkpoint SuperBot V3: S1b benchmark + S2 terminale Brain
6 novembre 2026 | autore ChatGPT GPT-6 | PAPER, solo prova isolata, nessun deploy/merge/VPS.

Baseline: ZIP a5a0c14; 387 file originali byte-identici. PR #61 dashboard a9044b6759da327b44da04f9e7f51e211d44e03f e PR #57 runner e25c8dd8db88fd6994e3b7a75ecfdec5ff258421 ancora draft e separate.
Prerequisiti: file S0 trace.py e S1 evidence.py consegnati in precedenza non presenti nei due ZIP di questa sessione. S2 NON integrato con le loro versioni reali. Endpoint HTTP restituisce esplicitamente 503 se i moduli mancano.

S1b benchmark sintetico: 30 simboli, 3000 barre 15m + 800 barre 1h + 250 barre 4h, dataset riutilizzato per ogni simbolo. Calcolo L5 9878.813 ms totale, mediana 334.719 ms, p95 401.182 ms; lettura 300 eventi journal mediana 1.231 ms; verifica hash chain mediana 2.276 ms. Non comprende rete, DeepSeek, VPS. Gate raccomandato: riusare vista L5 gia calcolata per analista e osservazione, senza duplicarla.

S2 nuovi file isolati: backend/v3/supervisor/terminal.py; backend/v3/supervisor_http.py; backend/tests/test_v3_supervisor_terminal.py; frontend/src/components/SupervisorTerminal.js e .test.js; frontend/src/pages/Supervisor.js; benchmark e tool di verifica. GET /api/v3/brain/decision-timeline autenticata, read-only, no-store; schede conservative con evidenza registrata/assente/ambigua; filtro simbolo e motivo; candidati scartati distinti da NO_TRADE; finestra S0 limitata alle ultime 500 decisioni segnalata. Pagina mobile /supervisor separata. Patch opzionale di collegamento server/App non applicata.

TEST VERIFICATI: suite V3 4208 passed in 140.47s; S2+dashboard 36 passed in 0.55s; S2 da /tmp 20 passed in 0.30s; JSX 3 file senza errori; 8 check JS puri passati. Patch dry-run valida; 387/387 file a5 invariati.
NON ESEGUITI: Jest/React vero (mancano node_modules), S0+S1 end-to-end reali, CI unificata PR57+61, VPS/Bitget/DeepSeek, merge/deploy.

ARTEFATTI nel messaggio ChatGPT (non upload su GitHub):
SuperBot-V3-S1b-Benchmark-S2-Terminale-2026-11-06.zip SHA256 8374a58b2fef2d689fc8dc5b92b308cdb49fb7640e24c33785f959de1498b79e
RAPPORTO_SuperBot_V3_S1b_S2_2026-11-06.md SHA256 93d9ec35feaddbe4175b5a59b73b9add506668ab570fae2a92fd345c3d06b9d5

Prossimo gate: verificare sorgenti S0/S1 e SHA, integrare su branch isolato con PR #57/#61, ottimizzare vista L5 e performance del tracing, CI Jest/build CRA, mantenere stop/manual-close prioritari. Nessun avvio Brain o redeploy Falco/Toro senza OK esplicito. Rischi invariati 2% per trade, 5% open, 35% warn, 50% halt, floor 450 USDT; non adottare 43% equity dell'esempio.