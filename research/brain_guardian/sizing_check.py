import json, statistics as st
from pathlib import Path
from research.brain_guardian.experiment import SYMBOLS, VARIANTS, control_entries, load_bars
from research.brain_guardian.replay import Sizing, Variant, PortfolioGuard, EntryFilter, metrics, run_portfolio
bars = load_bars(Path(__import__("sys").argv[1]), SYMBOLS)
end = min(bs[-1].t for bs in bars.values()) - 25 * 3_600_000
SPLIT = 1793491200000
sizings = {"brain_4x_notional": Sizing(), "1x_notional": Sizing(max_position_margin_fraction=0.05,
                                                                 max_total_margin_fraction=0.15)}
common = Variant("common_candidate", filt=EntryFilter(min_stop_cost_mult=4.0),
                 guard=PortfolioGuard(hwm_drawdown_halt=0.10, daily_loss_halt=0.05))
out = {}
for per, (a, b, off) in {"in_sample": (1790812800000, SPLIT, 0), "out_of_sample": (SPLIT, end, 1000)}.items():
    for sname, sz in sizings.items():
        for v in (VARIANTS["A_baseline"], common):
            ms = [metrics(run_portfolio(control_entries(bars, a, b, off + s), bars, v, sizing=sz)) for s in range(1, 6)]
            k = f"{per}|{sname}|{v.name}"
            out[k] = {m: round(st.mean([x[m] for x in ms if x[m] is not None]), 3) for m in
                      ("trades", "net_pnl", "expectancy_r", "max_drawdown_pct", "worst_trade", "fees")}
            print(k, out[k])
Path(__import__("sys").argv[2]).write_text(json.dumps(out, indent=1))
