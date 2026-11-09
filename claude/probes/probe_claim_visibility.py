"""Sonda sola lettura: un claim PAPER pendente e' visibile in overview Falco? (dati sintetici in tmp)."""
import json, os, sys, tempfile, time
d = tempfile.mkdtemp()
import desk.cli as cli
from desk.engine import PaperAccount
cli.DATA_DIR = d; cli.STATE_FILE = os.path.join(d, "state_v2.json")
now = time.time(); now_ms = int(now * 1000)
acc = PaperAccount(cli.PORTFOLIO.limits, "main")
acc.open("BTC", 1, 60, 10, 100.0, 98.0, 110.0, now_ms - 3_600_000, {"BTC": 100.0})
state = {"main": acc.to_dict(), "run_no": 1}
cli.save_state(state, cli.STATE_FILE)
cli.append_trade_history = lambda *a, **k: None          # storico non scrivibile
cli.notify_close = lambda *a: None
rec, why = cli._close_for_user(state, acc, "BTC", 101.0, now_ms, notice=("x", "y"))
cli.save_account(acc, state)
cli._commit_paper_closes(state)
cli.write_heartbeat(state)
disk = json.load(open(cli.STATE_FILE))
print("claim pendenti su disco:", len(disk.get("paper_close_claims") or []))
print("HB paper_close_claims:", json.load(open(os.path.join(d, "heartbeat.json"))).get("paper_close_claims"))
import v3_api
c = v3_api._classic("falco", d, now)
print("overview falco: open_positions=", c["open_positions"], "closed_trades=", len(c["closed_trades"]),
      "realized_pnl=", c["realized_pnl"], "cash=", c["cash"], "equity=", c["equity"])
keys = json.dumps(c)
print("claim/riconciliazione esposti nell'overview:", any(k in keys for k in ("claim", "riconcil", "pending_close")))
print("netto della chiusura in sospeso:", rec["net"])
