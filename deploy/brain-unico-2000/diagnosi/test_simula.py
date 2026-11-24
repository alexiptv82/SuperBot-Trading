"""Simulatore delle proposte: imbuto fedele (proposte, approvate, eseguibili, eseguite) e risultato reale separato."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simula_bloccate as sb  # noqa: E402

T = 1_795_526_131_745


def _ev():
    def cons(seq, sym, t, code, fopen):
        return {"seq": seq, "id": f"c{seq}", "kind": "ai_consultation", "t": t, "payload": {
            "scope": "entry", "symbol": sym, "regime": "TREND_DOWN", "code": code, "triggers": ["uncertainty"],
            "deepseek": {"side": -1, "stop_price": "101", "confidence": 0.58, "reasons": [], "uncertain": True},
            "claude": {"status": "ok", "verdict": "CONFIRM" if fopen else "CONTEST", "confidence": 0.6},
            "final": {"open": fopen, "side": -1 if fopen else None, "stop_price": None}}}

    def dec(seq, sym, t, status, did, wrote_after_s):
        return [{"seq": seq, "id": did, "kind": "brain_decision", "t": t,
                 "payload": {"symbol": sym, "status": status, "kind": "OPEN" if status == "APPROVED" else "NO_TRADE"}},
                {"seq": seq + 1, "id": f"s{seq}", "kind": "brain_decision_snapshot_v2", "t": t,
                 "payload": {"decision_event_id": did, "capture_wall_ms": t + 1000,
                             "write_wall_ms": t + wrote_after_s * 1000}}]
    ev = [cons(1, "ICPUSDT", T, "claude_confirmed", True), *dec(2, "ICPUSDT", T, "APPROVED", "d-icp", 383),
          cons(4, "BTCUSDT", T + 9e5, "claude_stop_adopted", True), *dec(5, "BTCUSDT", int(T + 9e5), "APPROVED", "d-btc", 39),
          cons(7, "SUIUSDT", T + 9e5, "claude_contested", False), *dec(8, "SUIUSDT", int(T + 9e5), "DRAFT", "d-sui", 30)]
    ev[3]["t"] = ev[4]["t"] = int(T + 9e5)
    ev += [{"seq": 20 + i, "id": f"o{i}", "kind": "paper_open", "t": int(T + 9e5) + 39_000,
            "payload": {"decision_event_id": "d-btc", "leg": leg}} for i, leg in enumerate(("tp1", "runner"))]
    ev += [{"seq": 30 + i, "id": f"x{i}", "kind": "paper_close", "t": int(T + 2e6), "payload": {
        "decision_event_id": "d-btc", "gross_pnl": g, "fees": f, "realized_pnl": n}}
        for i, (g, f, n) in enumerate((("-2.68", "3.18", "-5.86"), ("-4.98", "5.91", "-10.89")))]
    for e in ev:
        e["t"] = int(e["t"])
    return ev


def test_funnel_counts_distinct_trades_and_excludes_stale_approvals():
    ev = _ev()
    props = sb.proposals(ev)
    f = sb.funnel(props)
    assert (f["proposte"], f["approvate"], f["eseguibili_dopo_controllo"], f["eseguite"]) == (3, 2, 1, 1)
    assert f["scadute_certe_fra_le_approvate"] == [["ICPUSDT", 383]] or f["scadute_certe_fra_le_approvate"] == [("ICPUSDT", 383)]
    by = {p["symbol"]: p for p in props}
    assert sb.decide(by["ICPUSDT"], "S0")[0] is False and sb.decide(by["ICPUSDT"], "S4")[2] == "decision_stale"
    assert sb.decide(by["BTCUSDT"], "S0")[0] is True and sb.decide(by["SUIUSDT"], "S0")[0] is False
    assert sb.decide(by["SUIUSDT"], "S4")[0] is True                       # controfattuale, mai "reale"


def test_real_result_comes_only_from_the_journal():
    r = sb.real_result(_ev())
    assert (r["trade_distinti"], r["chiusure"]) == (1, 2) and r["netto"] == "-16.75"
