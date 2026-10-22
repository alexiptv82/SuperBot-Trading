import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/scripts/regime_trade_analysis.py"
spec = importlib.util.spec_from_file_location("regime_trade_analysis", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _open(run, ident, ts, side, roc):
    return {"ev":"open", "run_no":run, "id":ident, "ts":ts, "side":side,
            "features":{"btc_roc24h":roc}}


def _close(run, ident, ts, r, partial=False):
    return {"ev":"close", "run_no":run, "id":ident, "ts":ts, "net_r":r, "partial":partial}


def test_sums_partial_closes_and_uses_entry_features():
    events=[_open(4,1,1_792_000_000_000,-1,-.02), _close(4,1,1_792_000_100_000,.25,True),
            _close(4,1,1_792_000_200_000,.50,False)]
    trades, skipped=mod.build_trades(events,"hawk")
    assert len(trades)==1
    assert trades[0]["r"]==.75 and trades[0]["side"]=="short" and trades[0]["regime"]=="down"
    assert trades[0]["partials"]==1


def test_same_id_in_different_run_is_not_merged():
    events=[_open(3,1,1_792_000_000_000,1,.02), _close(3,1,1_792_000_100_000,.4),
            _open(4,1,1_792_000_000_000,-1,-.02), _close(4,1,1_792_000_100_000,-.2)]
    trades,_=mod.build_trades(events,"hawk")
    assert len(trades)==2
    assert sorted(t["r"] for t in trades)==[-.2,.4]


def test_final_close_required_and_missing_regime_excluded():
    events=[_open(1,1,1_792_000_000_000,1,None), _close(1,1,1_792_000_100_000,.3),
            _open(1,2,1_792_000_000_000,1,.02), _close(1,2,1_792_000_100_000,.3,True)]
    trades, skipped=mod.build_trades(events,"bull")
    assert trades==[]
    assert skipped["missing_entry_btc_roc24h"]==1
    assert skipped["no_unique_final_close"]==1


def test_regime_cutoffs_are_asymmetric_only_at_strict_edges():
    assert mod.classify_regime(-.01001)=="down"
    assert mod.classify_regime(-.01)=="flat"
    assert mod.classify_regime(.01)=="flat"
    assert mod.classify_regime(.01001)=="up"
    assert mod.classify_regime(float("nan")) is None


def test_malformed_or_unterminated_snapshot_fails_closed():
    for data in (b'{"ev":"open"}', b'{bad}\n', b'{"ev":"open","ev":"close"}\n', b'\n'):
        try:
            mod.parse_snapshot(data)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid snapshot accepted")


def test_cluster_interval_suppressed_for_few_days():
    rows=[{"r":.1,"day":"2026-10-20"},{"r":.2,"day":"2026-10-21"}]
    assert mod.summarize(rows)["cluster_bootstrap95"] is None


def test_report_contains_aggregates_not_position_values():
    events=[_open(1,1,1_792_000_000_000,1,.02), _close(1,1,1_792_000_100_000,.3)]
    report=mod.analyze({"hawk":events},{"hawk":"a"*64})
    encoded=json.dumps(report)
    sensitive={"symbol", "entry", "exit", "id", "price", "net", "cash", "margin"}
    def walk(x):
        if isinstance(x, dict):
            assert not (sensitive & set(x))
            for value in x.values(): walk(value)
        elif isinstance(x, list):
            for value in x: walk(value)
    walk(report)
    assert report["groups"]["hawk/up/long"]["n"]==1
