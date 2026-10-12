"""Test della lettura dei portafogli desk (desk_view) e del collegamento HTTP (desk_api).

Niente rete, niente bot: si costruiscono a mano i file che il bot scrive (stesso formato di
backend/desk/engine.py sul ramo del bot) e si controllano i numeri che l'app mostrera'.
"""
import asyncio
import json
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import desk_view as dv  # noqa: E402

NOW = 1_800_000_000.0
DAY = "2027-01-15"


def _pos(symbol="BTC", side=1, entry=100.0, qty=10.0, margin=100.0, lev=10, **kw):
    p = {"id": 1, "symbol": symbol, "side": side, "margin": margin, "leverage": lev, "entry": entry,
         "qty": qty, "sl": entry * 0.95, "tp": entry * 1.05, "open_ms": int(NOW * 1000) - 3_600_000,
         "liq": entry * 0.9, "confidence": 80, "reason": "test", "source": "claude",
         "total_margin": margin, "trade_type": "medio", "dca_count": 0, "dca_levels": []}
    p.update(kw)
    return p


def _closed(i, net, symbol="BTC", ttype="medio", why="take profit", side=1, close_ms=None, **kw):
    close_ms = close_ms or (int(NOW * 1000) - (100 - i) * 3_600_000)
    rec = {"id": i, "symbol": symbol, "side": side, "margin": 100.0, "leverage": 10, "entry": 100.0,
           "exit": 101.0, "open_ms": close_ms - 3_600_000, "close_ms": close_ms, "net": net,
           "gross": net + 1, "fees": 1.0, "funding": 0.0, "why": why, "confidence": 80,
           "reason": "motivo ingresso", "source": "claude", "account": "main", "trade_type": ttype,
           "dca_count": 0}
    rec.update(kw)
    return rec


def _write_state(d, positions=None, cash=1000.0, closed=None, **extra):
    acc = {"name": "main", "cash": cash, "positions": positions or {}, "closed": closed or [],
           "next_id": 5, "day": DAY, "day_start_equity": 1000.0,
           "limits": {"start_equity": 1000.0, "max_open": 10, "max_margin_trade": 100.0,
                      "kill_equity": 450.0, "daily_stop": 0.12}}
    state = {"main": acc, "budget": {"day": "2027-01-15", "spent": 0.25, "calls": 3}}
    state.update(extra)
    with open(os.path.join(d, "state_v2.json"), "w") as f:
        json.dump(state, f)


def _write_history(d, recs, extra_lines=()):
    with open(os.path.join(d, "trade_history.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
        for line in extra_lines:
            f.write(line + "\n")


def _write_hb(d, age=5, **kw):
    hb = {"ts": NOW - age, "mode": "running", "cycles": 7, "last_ok": True, "last_error": "",
          "next_cycle_ms": int(NOW * 1000) + 600_000, "version": "abc1234", "daily_cap_usd": 0.7}
    hb.update(kw)
    with open(os.path.join(d, "heartbeat.json"), "w") as f:
        json.dump(hb, f)


# ── stato ────────────────────────────────────────────────────────────────────
def test_status_without_state_is_unavailable_not_an_error():
    with tempfile.TemporaryDirectory() as d:
        st = dv.build_status(d, "hawk", now=NOW)
        assert st["available"] is False and "message" in st


def test_status_equity_uses_live_price_and_includes_margin():
    with tempfile.TemporaryDirectory() as d:
        # BTC long: entry 100, qty 10 (notional 1000 a 10x), margine 100 -> cassa 900
        _write_state(d, {"BTC": _pos()}, cash=900.0, last_prices={"BTC": 101.0})
        _write_hb(d)
        st = dv.build_status(d, "hawk", prices={"BTC": 102.0}, now=NOW)
        p = st["positions"][0]
        assert p["price"] == 102.0 and p["price_source"] == "live"
        assert p["pnl"] == 20.0 and p["pnl_pct"] == 20.0
        assert st["margin_used"] == 100.0 and st["unrealized_pnl"] == 20.0
        assert st["equity"] == 1020.0, "equity = cassa + margine + P&L non realizzato"
        assert st["pnl_total"] == 20.0 and st["pnl_total_pct"] == 2.0
        # senza prezzo live si usa l'ultimo del bot, poi l'ingresso
        st2 = dv.build_status(d, "hawk", prices={}, now=NOW)
        assert st2["positions"][0]["price_source"] == "bot" and st2["equity"] == 1010.0
        os.remove(os.path.join(d, "state_v2.json"))
        _write_state(d, {"BTC": _pos()}, cash=900.0)
        st3 = dv.build_status(d, "hawk", now=NOW)
        assert st3["positions"][0]["price_source"] == "entry" and st3["equity"] == 1000.0


def test_status_short_position_pnl_sign():
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {"ETH": _pos("ETH", side=-1, entry=100.0, qty=10.0)}, cash=900.0)
        st = dv.build_status(d, "bull", prices={"ETH": 98.0}, now=NOW)
        assert st["positions"][0]["pnl"] == 20.0, "short guadagna se il prezzo scende"


def test_status_mode_follows_pause_flag_and_positions():
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {"BTC": _pos()}, cash=900.0)
        assert dv.build_status(d, "hawk", now=NOW)["bot_mode"] == "running"
        open(os.path.join(d, "pause.flag"), "w").close()
        st = dv.build_status(d, "hawk", now=NOW)
        assert st["bot_mode"] == "draining" and st["paused"] is True and st["draining"] is True
        assert st["can_reset"] is False and "aperte" in st["reset_blocked_reason"]
        _write_state(d, {}, cash=1003.0)
        st = dv.build_status(d, "hawk", now=NOW)
        assert st["bot_mode"] == "paused" and st["can_reset"] is True


def test_status_online_depends_on_heartbeat():
    with tempfile.TemporaryDirectory() as d:
        _write_state(d)
        _write_hb(d, age=30)
        st = dv.build_status(d, "hawk", now=NOW)
        assert st["bot_online"] is True and st["version"] == "abc1234"
        assert st["cycle"]["next_cycle_ms"] and st["cycle"]["last_ok"] is True
        _write_hb(d, age=900)
        assert dv.build_status(d, "hawk", now=NOW)["bot_online"] is False


def test_status_halt_and_stale_budget():
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {}, cash=400.0)
        assert dv.build_status(d, "hawk", now=NOW)["halt"] == "capitale sotto la soglia minima"
        _write_state(d, {}, cash=850.0)   # -15% sul giorno
        assert dv.build_status(d, "hawk", now=NOW)["halt"] == "stop giornaliero raggiunto"
        _write_state(d, {}, cash=1000.0)
        st = dv.build_status(d, "hawk", now=NOW)
        assert st["halt"] is None and st["budget_spent_usd"] == 0.25
        # il budget salvato e' di ieri: oggi non e' stato speso nulla
        later = NOW + 2 * 86400
        assert dv.build_status(d, "hawk", now=later)["budget_spent_usd"] == 0.0


# ── trade chiusi ─────────────────────────────────────────────────────────────
def test_history_skips_garbage_and_legacy_lines():
    with tempfile.TemporaryDirectory() as d:
        _write_history(d, [_closed(1, 5.0)],
                       extra_lines=[json.dumps([{"symbol": "X", "net": 0}]), "{rotto", "", json.dumps({"symbol": "Y"})])
        recs = dv.read_history(d)
        assert len(recs) == 1 and recs[0]["id"] == 1


def test_trades_are_newest_first_with_correct_field_mapping():
    with tempfile.TemporaryDirectory() as d:
        _write_history(d, [_closed(1, 5.0, why="take profit"), _closed(2, -3.0, why="stop loss", ttype="scalp")])
        tr = dv.build_trades(d, 100)
        assert [t["id"] for t in tr] == [2, 1]
        t = tr[0]
        assert t["pnl"] == -3.0 and t["leverage"] == 10 and t["trade_type"] == "scalp"
        assert t["close_reason"] == "stop loss", "il motivo di CHIUSURA e' why, non il motivo d'ingresso"
        assert t["entry_reason"] == "motivo ingresso"
        assert t["entry_price"] == 100.0 and t["exit_price"] == 101.0 and t["gross_pnl"] == -2.0


def test_trades_accept_legacy_field_names():
    with tempfile.TemporaryDirectory() as d:
        legacy = {"id": 9, "symbol": "SOL", "side": -1, "lev": 12, "type": "scalp", "margin": 50.0,
                  "entry": 10.0, "exit": 9.0, "net": 4.0, "gross": 5.0, "fees": 1.0,
                  "reason": "ex-formato", "open_ms": 1, "close_ms": 2}
        _write_history(d, [legacy])
        t = dv.build_trades(d, 10)[0]
        assert t["leverage"] == 12 and t["trade_type"] == "scalp" and t["close_reason"] == "ex-formato"


def test_trades_fall_back_to_state_when_history_is_missing():
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, closed=[_closed(1, 2.0)])
        assert len(dv.build_trades(d, 10)) == 1


# ── performance ──────────────────────────────────────────────────────────────
def test_performance_numbers():
    with tempfile.TemporaryDirectory() as d:
        recs = [_closed(1, 10.0, "BTC", "medio", "take profit"),
                _closed(2, -4.0, "ETH", "scalp", "stop loss", side=-1),
                _closed(3, -6.0, "ETH", "scalp", "stop loss", side=-1),
                _closed(4, 2.0, "BTC", "medio", "chiusura Claude")]
        _write_history(d, recs)
        _write_state(d)
        p = dv.build_performance(d, "hawk")
        assert p["available"] and p["total_trades"] == 4 and p["winning_trades"] == 2
        assert p["win_rate"] == 50.0 and p["total_pnl"] == 2.0 and p["total_fees"] == 4.0
        assert p["profit_factor"] == 1.2 and p["best_trade"] == 10.0 and p["worst_trade"] == -6.0
        assert p["avg_win"] == 6.0 and p["avg_loss"] == -5.0
        assert p["max_drawdown"] == 10.0, "da +10 a 0 (-4,-6): calo di 10"
        assert p["equity_curve"][-1]["equity"] == 1002.0 and p["equity_curve"][0]["equity"] == 1010.0
        assert set(p["by_type"]) == {"medio", "scalp"} and p["by_type"]["scalp"]["net_pnl"] == -10.0
        assert p["by_symbol"]["ETH"]["win_rate"] == 0 and p["by_reason"]["stop loss"]["trades"] == 2
        assert p["by_side"]["short"]["trades"] == 2
        assert p["avg_hold_hours"] == 1.0


def test_performance_empty():
    with tempfile.TemporaryDirectory() as d:
        p = dv.build_performance(d, "bull")
        assert p["available"] is False and p["total_trades"] == 0 and p["by_symbol"] == {}


# ── diario ───────────────────────────────────────────────────────────────────
def test_diary_groups_by_utc_day_newest_first():
    with tempfile.TemporaryDirectory() as d:
        day1 = 1_800_000_000_000          # 2027-01-15
        day2 = day1 + 86_400_000
        _write_history(d, [_closed(1, 5.0, close_ms=day1), _closed(2, -2.0, close_ms=day1 + 1000),
                           _closed(3, 7.0, "ETH", close_ms=day2)])
        di = dv.build_diary(d)
        assert [x["day"] for x in di["days"]] == ["2027-01-16", "2027-01-15"]
        d15 = di["days"][1]
        assert d15["total_trades"] == 2 and d15["wins"] == 1 and d15["losses"] == 1 and d15["total_pnl"] == 3.0
        assert d15["trades"][0]["leverage"] == 10 and d15["trades"][0]["trade_type"] == "medio"
        assert di["total_closed"] == 3


# ── run archiviate ───────────────────────────────────────────────────────────
def test_runs_lists_archive_newest_first_and_current():
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, run_no=3, run_started_ms=123)
        _write_history(d, [_closed(1, 5.0)])
        for name, ended, net in (("20270101-000000", 100, 12.5), ("20270102-000000", 200, -3.0)):
            os.makedirs(os.path.join(d, "archive", name))
            with open(os.path.join(d, "archive", name, "summary.json"), "w") as f:
                json.dump({"run_no": 1, "ended_ms": ended, "net_total": net, "trades": 4,
                           "params": {"limits": {"max_margin_trade": 100}}}, f)
        os.makedirs(os.path.join(d, "archive", "vuota"))   # cartella senza riepilogo: ignorata
        r = dv.list_runs(d, "hawk")
        assert [a["net_total"] for a in r["archived"]] == [-3.0, 12.5]
        assert r["archived"][0]["archive"] == "20270102-000000"
        assert r["current"]["run_no"] == 3 and r["current"]["trades"] == 1 and r["current"]["started_ms"] == 123
        assert r["current"]["params"]["limits"]["max_open"] == 10   # senza heartbeat: i limiti dello stato
        _write_hb(d, params={"limits": {"max_open": 7}, "entry_score_tier_c": 72, "code_version": "abc1234"})
        r = dv.list_runs(d, "hawk", status=dv.build_status(d, "hawk", now=NOW))
        assert r["current"]["params"]["entry_score_tier_c"] == 72, "con heartbeat: i parametri veri del bot"


# ── comandi ──────────────────────────────────────────────────────────────────
def test_pause_and_resume_flags():
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {"BTC": _pos()}, cash=900.0)
        r = dv.command_pause(d)
        assert os.path.exists(os.path.join(d, "pause.flag"))
        assert r["bot_mode"] == "draining" and r["open_positions"] == 1 and "lascia finire" in r["message"]
        r = dv.command_resume(d)
        assert not os.path.exists(os.path.join(d, "pause.flag")) and r["bot_mode"] == "running"
        dv.command_resume(d)   # idempotente
        _write_state(d, {}, cash=1000.0)
        assert dv.command_pause(d)["bot_mode"] == "paused"


def test_close_all_only_queues_when_positions_exist():
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {}, cash=1000.0)
        assert dv.command_close_all(d)["queued"] is False
        assert not os.path.exists(os.path.join(d, "reset.flag"))
        _write_state(d, {"BTC": _pos(), "ETH": _pos("ETH")}, cash=800.0)
        r = dv.command_close_all(d)
        assert r["queued"] is True and r["positions_found"] == 2 and os.path.exists(os.path.join(d, "reset.flag"))


def test_reset_budget_flag_is_budget_only():
    with tempfile.TemporaryDirectory() as d:
        dv.command_reset_budget(d)
        assert open(os.path.join(d, "budget_reset.flag")).read() == "budget_only"


def test_reset_portfolio_rules():
    with tempfile.TemporaryDirectory() as d:
        ok, code, r = dv.command_reset_portfolio(d)
        assert (ok, code) == (False, 404)
        _write_state(d, {}, cash=1000.0)
        ok, code, r = dv.command_reset_portfolio(d)
        assert (ok, code) == (False, 409) and "pausa" in r["message"], "non in pausa: rifiutato"
        open(os.path.join(d, "pause.flag"), "w").close()
        _write_state(d, {"BTC": _pos()}, cash=900.0)
        ok, code, r = dv.command_reset_portfolio(d)
        assert (ok, code) == (False, 409) and "1 posizioni aperte" in r["message"]
        assert not os.path.exists(os.path.join(d, "reset_portfolio.flag"))
        _write_state(d, {}, cash=1000.0)
        ok, code, r = dv.command_reset_portfolio(d, clear_lessons=True)
        assert (ok, code) == (True, 200) and r["queued"] is True
        assert json.load(open(os.path.join(d, "reset_portfolio.flag"))) == {"clear_lessons": True}
        ok, code, r = dv.command_reset_portfolio(d)   # gia' richiesto: non si accoda due volte
        assert ok and "già richiesto" in r["message"]
        assert dv.build_status(d, "hawk", now=NOW)["reset_pending"] is True


# ── collegamento HTTP (con un FastAPI finto se quello vero non c'e') ──────────
def _import_desk_api():
    try:
        import fastapi  # noqa: F401
    except ImportError:
        mod = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code=500, detail=""):
                self.status_code, self.detail = status_code, detail

        class _Route:
            def __init__(self, path, methods, endpoint):
                self.path, self.methods, self.endpoint = path, methods, endpoint

        class APIRouter:
            def __init__(self):
                self.routes = []

            def _reg(self, path, method):
                def deco(fn):
                    self.routes.append(_Route(path, {method}, fn))
                    return fn
                return deco

            def get(self, path, **kw):
                return self._reg(path, "GET")

            def post(self, path, **kw):
                return self._reg(path, "POST")

        mod.APIRouter, mod.HTTPException = APIRouter, HTTPException
        mod.Depends = lambda f: f
        mod.Request = object
        sys.modules["fastapi"] = mod
    import desk_api
    return desk_api


def _handler(router, path, method="GET"):
    for r in router.routes:
        if r.path == path and method in r.methods:
            return r.endpoint
    raise AssertionError(f"rotta mancante: {method} {path}")


def test_router_has_all_routes_for_both_portfolios_and_status_works():
    api = _import_desk_api()
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {"BTC": _pos()}, cash=900.0)
        calls = []

        async def fake_ticker(sym):
            calls.append(sym)
            return {"symbol": sym, "price": 110.0}

        api._ticker_cache.clear()
        router = api.make_router("hawk", d, lambda: None, fake_ticker)
        for path, m in [("/status", "GET"), ("/trades", "GET"), ("/performance", "GET"), ("/diary", "GET"),
                        ("/runs", "GET"), ("/logs", "GET"), ("/health", "GET"), ("/pause", "POST"),
                        ("/resume", "POST"), ("/close-all", "POST"), ("/reset-budget", "POST"),
                        ("/reset-portfolio", "POST")]:
            _handler(router, path, m)
        st = asyncio.run(_handler(router, "/status")(session=None))
        assert st["positions"][0]["price"] == 110.0 and st["positions"][0]["price_source"] == "live"
        assert st["equity"] == 1000.0 + 100.0
        n = len(calls)
        asyncio.run(_handler(router, "/status")(session=None))
        assert len(calls) == n, "il prezzo appena letto non si richiede di nuovo (cache 20s)"


def test_router_status_survives_exchange_errors():
    api = _import_desk_api()
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {"BTC": _pos()}, cash=900.0, last_prices={"BTC": 103.0})

        async def broken(sym):
            raise RuntimeError("exchange giu'")

        api._ticker_cache.clear()
        router = api.make_router("bull", d, lambda: None, broken)
        st = asyncio.run(_handler(router, "/status")(session=None))
        assert st["available"] and st["positions"][0]["price_source"] == "bot"


def test_router_reset_portfolio_conflict_is_http_409():
    api = _import_desk_api()
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {}, cash=1000.0)
        router = api.make_router("hawk", d, lambda: None, None)

        class Req:
            async def json(self):
                return {"clear_lessons": False}
        try:
            asyncio.run(_handler(router, "/reset-portfolio", "POST")(request=Req(), session=None))
            raise AssertionError("doveva rifiutare: bot non in pausa")
        except Exception as e:
            assert getattr(e, "status_code", None) == 409 and "pausa" in str(getattr(e, "detail", ""))
        open(os.path.join(d, "pause.flag"), "w").close()
        out = asyncio.run(_handler(router, "/reset-portfolio", "POST")(request=Req(), session=None))
        assert out["queued"] is True


def test_router_pause_resume_roundtrip():
    api = _import_desk_api()
    with tempfile.TemporaryDirectory() as d:
        _write_state(d, {"BTC": _pos()}, cash=900.0)
        router = api.make_router("hawk", d, lambda: None, None)
        out = asyncio.run(_handler(router, "/pause", "POST")(session=None))
        assert out["paused"] is True and out["bot_mode"] == "draining"
        out = asyncio.run(_handler(router, "/resume", "POST")(session=None))
        assert out["paused"] is False
