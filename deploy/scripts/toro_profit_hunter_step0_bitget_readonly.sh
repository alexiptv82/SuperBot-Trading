#!/usr/bin/env bash
# Toro Profit Hunter entry-only Bitget STEP0. No service/unit changes; no orders.
# User-approved PAPER research. 5 symbols, 365 days, closed 1H and 4H.
set -Eeuo pipefail
umask 077
PIN=18ac3971c76269341c61b041394fbdb10f8bdb97
FIX=ab7e0b7d991b8f4bd714fccfec23b09a936e6717
REPO=https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading
ROOT=$(mktemp -d /tmp/toro-step0-readonly-XXXXXXXX)
trap 'rm -rf "$ROOT"' EXIT
OUT=/opt/superbot-toro-research/step0-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$ROOT/backend/desk" "$ROOT/backend/tests" "$ROOT/backend/v3/lab_tools" "$ROOT/deploy/scripts" "$OUT"
touch "$ROOT/backend/desk/__init__.py"
download(){
  local ref=$1 path=$2 sha=$3
  curl -fLsS --max-time 45 "$REPO/$ref/$path" -o "$ROOT/$path"
  if [[ "$(git hash-object "$ROOT/$path")" != "$sha" ]]; then
     echo "TORO_STEP0 RESULT=BLOCK pin_mismatch=$path"
     exit 2
  fi
}
download "$PIN" backend/desk/toro_profit_hunter.py 9367edec67a0d40d9019629eda906752ea6c3a65
download "$PIN" backend/tests/test_toro_profit_hunter_v1.py b136c649e60a8cddb30d7a2042ebd2827b5f75e3
download "$PIN" backend/tests/test_toro_profit_hunter_step0.py 8b17ee3e970b5993e226e3d9646043b2859dcc1f
download "$PIN" deploy/scripts/toro_profit_hunter_step0.py 4adf5716672117a4a7e0a5e58614e8ca0ec85a36
download "$FIX" backend/v3/lab_tools/fetch_candles.py 150aec1d3427af926bd02a074bac4212615c4cdb
PY=/opt/superbot-v3-rc70-stage/.venv/bin/python3
if [[ ! -x "$PY" ]]; then PY=python3; fi
PYTHONPATH="$ROOT/backend:$ROOT" PYTHONDONTWRITEBYTECODE=1 "$PY" -m unittest discover \
  -s "$ROOT/backend/tests" -p 'test_toro_profit_hunter*.py' -q
echo "TORO_STEP0 TESTS=PASS count=19 stage_unchanged=1"
export PYTHONPATH="$ROOT/backend:$ROOT" PYTHONDONTWRITEBYTECODE=1
"$PY" - "$OUT" "$PIN" "$FIX" <<'PYCODE'
from __future__ import annotations
import json, sys, time, hashlib
from pathlib import Path
from backend.v3.lab_tools.fetch_candles import fetch_rows, write_csv
from deploy.scripts.toro_profit_hunter_step0 import load_csv, backtest
from desk.toro_profit_hunter import HOUR, FOUR_HOURS

out=Path(sys.argv[1]); pin,fix=sys.argv[2:]
start_at=int(time.time()*1000)
# Both feeds end at the same last CLOSED 4H boundary (UTC), avoiding mixed as-of.
end=(start_at//FOUR_HOURS)*FOUR_HOURS
start=end-365*24*HOUR
symbols=('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','XRPUSDT')
manifest={'asof_closed_ms':end, 'window_start_ms':start, 'history_days':365,
          'symbols':symbols, 'candidate_pin':pin, 'bitget_fetch_pin':fix,
          'read_only':True, 'source':'Bitget public USDT-FUTURES history-candles',
          'files':{},'results':{},'failures':[]}
for sym in symbols:
    paths={}
    for tf in (HOUR,FOUR_HOURS):
        label=f'{tf//MINUTE}m'
        dest=out/f'{sym}_{label}.csv'
        expected=(end-start)//tf
        print(f'TORO_STEP0 FETCH symbol={sym} tf={label} expected={expected}',flush=True)
        stats={}
        try:
            rows=fetch_rows(sym,start,end,candle_ms=tf,
                            window_bars=200,max_requests=300,stats=stats)
            sha=write_csv(dest,rows)
            n=len(rows)
            first=min(rows) if rows else None
            last=max(rows) if rows else None
            fresh=(last is not None and last>=end-2*tf)
            enough=n>=expected*0.85 and first is not None and first<=start+7*24*HOUR
            metadata={'rows':n,'expected':expected,'first_open_ms':first,
                      'last_open_ms':last,'sha256':sha,'fresh':fresh,
                      'coverage_ok':enough,'invalid_rows':len(stats.get('invalid_ts',set()))}
            manifest['files'][f'{sym}_{label}']=metadata
            print(f'TORO_STEP0 DATA symbol={sym} tf={label} rows={n}/{expected} fresh={int(fresh)} coverage={int(enough)} sha256={sha}',flush=True)
            if not fresh or not enough:
                manifest['failures'].append(f'{sym}_{label}:incomplete_or_stale')
            paths[label]=dest
        except Exception as e:
            manifest['failures'].append(f'{sym}_{label}:{type(e).__name__}:{str(e)[:130]}')
            print(f'TORO_STEP0 FETCH_ERROR symbol={sym} tf={label} type={type(e).__name__}',flush=True)
    if (f'{sym}_60m' not in manifest['files'] or
        f'{sym}_240m' not in manifest['files'] or
        not manifest['files'][f'{sym}_60m']['coverage_ok'] or
        not manifest['files'][f'{sym}_240m']['coverage_ok'] or
        not manifest['files'][f'{sym}_60m']['fresh'] or
        not manifest['files'][f'{sym}_240m']['fresh']):
        print(f'TORO_STEP0 NOT_EVALUABLE symbol={sym} reason=data_gate',flush=True)
        continue
    try:
        h,_=load_csv(paths['60m'])
        f,_=load_csv(paths['240m'])
        report=backtest(h,f,sym,seeds=1000,cost_fraction=0.001)
        manifest['results'][sym]=report
        for w, result in report['windows'].items():
            fmt=lambda v: "NA" if v is None else f"{v:.6f}"
            print(f"TORO_STEP0 WINDOW symbol={sym} hours={w} signals={result['signals']} "
                  f"avg_gross={fmt(result['avg_gross'])} avg_net={fmt(result['avg_net'])} "
                  f"null_percentile={fmt(result['share_of_matched_random_beaten'])} "
                  f"matched={int(result['matched'])}",flush=True)
    except Exception as e:
        manifest['failures'].append(f'{sym}:replay:{type(e).__name__}:{str(e)[:130]}')
        print(f'TORO_STEP0 REPLAY_ERROR symbol={sym} type={type(e).__name__}',flush=True)
manifest['elapsed_s']=round((int(time.time()*1000)-start_at)/1000,2)
dest=out/'report_step0.json'
dest.write_text(json.dumps(manifest,indent=2,ensure_ascii=False,sort_keys=True)+'\n')
print(f'TORO_STEP0 REPORT={dest}',flush=True)
# This is never an auto-approval. We inspect trade counts, OOS and confidence.
complete=len(manifest['results'])==len(symbols) and not manifest['failures']
print(f'TORO_STEP0 RESULT={"DATA_READY_FOR_HUMAN_REVIEW" if complete else "INCOMPLETE_NOT_EVALUABLE"} '
      f'symbols_evaluated={len(manifest["results"])}/{len(symbols)} '
      f'failed_gates={len(manifest["failures"])} '
      f'paper_trades=0 no_bot_changes=1',flush=True)
sys.exit(0 if complete else 2)
PYCODE
