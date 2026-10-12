#!/bin/bash
# Verifica end-to-end dei bot desk e delle API dell'app. NON stampa mai token o password.
# Prova anche Pausa/Riprendi sul portafoglio Bull con i comandi veri (e lo lascia SEMPRE in funzione).
OUT=/tmp/diag_e2e.txt
exec > "$OUT" 2>&1
API=http://127.0.0.1:8002
BULL_DIR=/opt/superbot-desk-data/bull
echo "=== ORA UTC: $(date -u) ==="
echo "--- container:"; docker ps --format '{{.Names}} | {{.Status}}' | cut -c1-120

hb() {  # riassunto del heartbeat di un portafoglio
  python3 - "$1" <<'PY'
import json, sys, time
try:
    h = json.load(open(f"/opt/superbot-desk-data/{sys.argv[1]}/heartbeat.json"))
    nxt = (h.get("next_cycle_ms") or 0) / 1000 - time.time()
    print({"mode": h.get("mode"), "pause_requested": h.get("pause_requested"), "open": h.get("open_positions"),
           "cycles": h.get("cycles"), "last_ok": h.get("last_ok"), "last_error": (h.get("last_error") or "")[:80],
           "version": h.get("version"), "age_s": round(time.time() - h["ts"]), "next_in_min": round(nxt / 60, 1)})
except Exception as e:
    print("heartbeat illeggibile:", e)
PY
}

for P in hawk bull; do
  echo; echo "########## $P ##########"
  echo "--- volume:"; ls -la /opt/superbot-desk-data/$P | awk '{print $5, $9}' | tail -n +2 | head -20
  echo "--- heartbeat:"; hb $P
  echo "--- versione nel container:"; docker exec superbot-desk-$P printenv DESK_CODE_VERSION
  echo "--- healthcheck (exit 0 = sano):"; docker exec superbot-desk-$P python -m desk.healthcheck; echo "exit=$?"
  echo "--- docker health:"; docker inspect --format '{{.State.Health.Status}}' superbot-desk-$P
  echo "--- ultimi log:"; docker logs --tail 22 superbot-desk-$P 2>&1 | cut -c1-190
done

echo; echo "########## API (sessione creata nel container, token mai stampato) ##########"
TOKEN=$(docker exec superbot python3 -c "import sys; sys.path.insert(0,'/app/backend'); from auth import create_session_token; print(create_session_token('full'))" 2>/dev/null | tail -1)
if [ -z "$TOKEN" ]; then echo "ERRORE: impossibile creare la sessione di prova"; else
  call() { curl -s -m 25 -H "Authorization: Bearer $TOKEN" "$@"; }
  summ() { python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception as e:
    print('RISPOSTA NON JSON:', e); sys.exit()
keys = sys.argv[1].split(',')
if isinstance(d, list):
    print('lista di', len(d), 'elementi; primo:', {k: d[0].get(k) for k in keys} if d else None)
else:
    print({k: d.get(k) for k in keys if k in d} or str(d)[:300])
" "$1"; }
  for P in "" "/bull"; do
    echo; echo "=== /api/desk$P ==="
    echo -n "status:      "; call $API/api/desk$P/status | summ available,bot_mode,paused,draining,bot_online,equity,cash,margin_used,unrealized_pnl,pnl_total,open_positions,total_closed,version,halt,run_no,can_reset,budget_spent_usd,budget_daily_cap_usd
    echo -n "  cycle:     "; call $API/api/desk$P/status | python3 -c "import sys,json; print(json.load(sys.stdin).get('cycle'))"
    echo -n "  posizioni: "; call $API/api/desk$P/status | python3 -c "
import sys,json
d=json.load(sys.stdin)
print([(p['symbol'],p['side'],p['pnl'],p['price_source']) for p in d.get('positions',[])])"
    echo -n "trades:      "; call "$API/api/desk$P/trades?limit=100" | summ symbol,pnl,leverage,trade_type,close_reason,entry_price,exit_price
    echo -n "performance: "; call $API/api/desk$P/performance | summ available,total_trades,win_rate,total_pnl,profit_factor,max_drawdown
    echo -n "diary:       "; call $API/api/desk$P/diary | summ total_closed
    echo -n "runs:        "; call $API/api/desk$P/runs | python3 -c "import sys,json; d=json.load(sys.stdin); print('run attuale', d['current']['run_no'], 'archiviate', len(d['archived']))"
    echo -n "logs:        "; call $API/api/desk$P/logs | summ available
    echo -n "reset-portfolio con bot in funzione (atteso 409): "; call -o /dev/null -w "%{http_code}" -X POST -H 'Content-Type: application/json' -d '{}' $API/api/desk$P/reset-portfolio; echo
  done
  echo; echo -n "prezzi (simboli con prezzo): "; call $API/api/desk/prices | python3 -c "import sys,json; d=json.load(sys.stdin); print(sum(1 for v in d.values() if isinstance(v,dict) and v.get('price')), '/', len(d))"
  echo -n "senza token (atteso 401): "; curl -s -o /dev/null -w "%{http_code}" -m 15 $API/api/desk/status; echo
  echo -n "senza token health (atteso 200): "; curl -s -o /dev/null -w "%{http_code}" -m 15 $API/api/desk/bull/health; echo

  echo; echo "########## PROVA COMANDI VERI su Bull: Pausa -> Riprendi ##########"
  echo "prima:"; echo -n "  server: "; call $API/api/desk/bull/status | summ bot_mode,paused,open_positions; echo -n "  bot:    "; hb bull
  echo ">> POST /pause"; call -X POST $API/api/desk/bull/pause | summ paused,bot_mode,open_positions,message
  ls -la $BULL_DIR/pause.flag | awk '{print "  pause.flag presente:", $9}'
  sleep 20
  echo "dopo 20s in pausa:"; echo -n "  server: "; call $API/api/desk/bull/status | summ bot_mode,paused,open_positions; echo -n "  bot:    "; hb bull
  docker logs --since 30s superbot-desk-bull 2>&1 | grep -E "PAUSA|MODO|AVVIO|OPEN|CLOSE|SKIP" | cut -c1-170 | tail -8
  echo ">> POST /resume"; call -X POST $API/api/desk/bull/resume | summ paused,bot_mode,message
  sleep 25
  echo "dopo 25s dalla ripresa:"; echo -n "  server: "; call $API/api/desk/bull/status | summ bot_mode,paused,open_positions; echo -n "  bot:    "; hb bull
  docker logs --since 40s superbot-desk-bull 2>&1 | grep -E "PAUSA|MODO|AVVIO|DESK V2\] candles|OPEN|CLOSE|SLEEP" | cut -c1-170 | tail -8
  # rete di sicurezza: Bull deve restare in funzione
  rm -f $BULL_DIR/pause.flag
  [ -e $BULL_DIR/pause.flag ] && echo "ATTENZIONE: pause.flag ancora presente" || echo "pause.flag assente: Bull in funzione"
fi

echo; echo "########## SITO PUBBLICO ##########"
echo -n "home: "; curl -s -o /dev/null -w "%{http_code}" -m 20 https://superbot-trading.duckdns.org/; echo
echo -n "api health: "; curl -s -m 20 https://superbot-trading.duckdns.org/api/health; echo
echo -n "status senza token (atteso 401): "; curl -s -o /dev/null -w "%{http_code}" -m 20 https://superbot-trading.duckdns.org/api/desk/status; echo
JS=$(curl -s -m 20 https://superbot-trading.duckdns.org/ | grep -o 'static/js/main\.[a-z0-9]*\.js' | head -1)
echo "bundle: $JS"
for S in "Pausa in corso" "Azzera portafoglio" "Chiudi subito tutte" "Run #"; do
  echo -n "  contiene \"$S\": "; curl -s -m 30 https://superbot-trading.duckdns.org/$JS | grep -c "$S"
done
echo; echo "FINE"
