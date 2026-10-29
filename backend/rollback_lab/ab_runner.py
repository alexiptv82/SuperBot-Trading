"""A/B laboratory: historical scorer + OHLC engine, using one common bar feed.
No exchange orders, no VPS access, no deployment. These are not AI-live replicas.
"""
import argparse
import hashlib
from datetime import datetime,timezone
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"deploy/scripts"))
import desk_backtest as bt

OLD="a0afc63fccc16b0081bc6fdd49768506b9242f89"
BAR=bt.BAR

def historic(repo,tmp,source,name):
    content=subprocess.check_output(["git","show",OLD+":"+source],cwd=repo,timeout=30)
    dest=tmp/(name+".py")
    dest.write_bytes(content)
    spec=importlib.util.spec_from_file_location(name,dest)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

def prepare(repo,tmp):
    oldsea=historic(repo,tmp,"backend/desk/seasonal.py","old_seasonal")
    oldsig=historic(repo,tmp,"backend/desk/signals.py","old_signals")
    oldeng=historic(repo,tmp,"backend/desk/engine.py","old_engine")
    class OldAdapter:
        @staticmethod
        def read_symbol(symbol,win,now_ms,**unused):
            oldsig.get_seasonal=oldsea.get_seasonal
            return oldsig.read_symbol(symbol,win,now_ms)
    original_modern=bt.sig_mod
    class ModernAdapter:
        @staticmethod
        def read_symbol(symbol,win,now_ms,btc_return_3d=None,**kwargs):
            return original_modern.read_symbol(symbol,win,now_ms,**kwargs)
    bt.sig_old=OldAdapter
    bt.sig_mod=ModernAdapter
    bt.sea_v1_compat=oldsea.get_seasonal
    original_rules=bt.rules_decisions
    def compatible_rules(readings,positions,opened,entry_score,**unused):
        return original_rules(readings,positions,opened,entry_score)
    bt.rules_decisions=compatible_rules
    # The current regime utility expects modern Position tracking fields.
    # In this no-regime experiment, R values only populate diagnostic pos_info.
    original_peak=bt.rg.peak_price
    original_unit=bt.rg.r_unit
    bt.rg.peak_price=lambda pos: (original_peak(pos) if hasattr(pos,"px_hi")
                                  else float(pos.entry))
    bt.rg.r_unit=lambda pos: (original_unit(pos) if hasattr(pos,"r_dist")
                              else abs(float(pos.entry)-float(pos.sl)))
    return oldeng

def variants(old_engine,portfolio):
    L=(dict(start_equity=1000.,max_margin_trade=100.,max_margin_total=1000.,
            max_open=10,daily_stop=.12,kill_equity=450.)
       if portfolio=="hawk" else
       dict(start_equity=1000.,max_margin_trade=350.,max_margin_total=1050.,
            max_open=3,daily_stop=.12,kill_equity=450.))
    bt.HAWK_LIMITS=L
    bt.HAWK_MIN_MARGIN=50. if portfolio=="hawk" else 150.
    bt.HAWK_FORCED_MARGIN=60. if portfolio=="hawk" else 200.
    bt.HAWK_MIN_LEV=10
    bt.HAWK_FORCED_LEV=15
    bt.tier=lambda sym: 60 if sym in bt.TIER_AB else 70
    source=bt.Variant
    class PairVariant(source):
        def __init__(self,name,params):
            super().__init__(name,params)
            if name.endswith("@exit_old"):
                self.acc=old_engine.PaperAccount(old_engine.Limits(**L),name)
            else:
                self.acc=bt.PaperAccount(bt.Limits(**L),name)
    bt.Variant=PairVariant
    names=["base@old@v1@nd4@exit_old","base@old@v1@nd4@exit_new",
           "base@full@exit_old","base@full@exit_new"]
    return {n:None for n in names}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--days",type=int,default=7)
    ap.add_argument("--portfolio",choices=["hawk","bull"],default="hawk")
    ap.add_argument("--synthetic",action="store_true")
    ap.add_argument("--cache",default="lab-cache")
    ap.add_argument("--symbols",default="BTC,ETH,SOL,ADA,DOGE")
    ap.add_argument("--step",type=int,default=4)
    ap.add_argument("--end-ms",type=int,default=0)
    ap.add_argument("--output",default="lab-result.json")
    args=ap.parse_args()
    if not 2<=args.days<=35 or not 1<=args.step<=8: raise SystemExit("unsupported_period")
    repo=Path(__file__).resolve().parents[2]
    end_ms=args.end_ms or (int(time.time()*1000)//bt.DAY*bt.DAY)
    symbols=args.symbols.split(",")
    if "BTC" not in symbols or any(s not in bt.SYMBOLS for s in symbols):
        raise SystemExit("invalid_universe")
    if args.synthetic:
        # Synthetic smoke also needs >=200 closed 4h bars for the modern scorer.
        data=bt.synthetic_data(max(args.days,37),end_ms)
        data={s:data[s] for s in symbols}
    else:
        data=bt.load_data(symbols,args.days,args.cache,end_ms)
    if not data or "BTC" not in data: raise SystemExit("no_market_data")
    with tempfile.TemporaryDirectory(prefix="classic-ab-") as root:
        old_engine=prepare(repo,Path(root))
        v=variants(old_engine,args.portfolio)
        results=bt.replay(data,v,end_ms-args.days*bt.DAY,end_ms,args.step)
        report=[bt.summarize(item,end_ms-args.days*bt.DAY,end_ms) for item in results.values()]
    windows={}
    for label,start,end in [("golden","2026-10-12","2026-10-16"),
                            ("first_crisis","2026-10-16","2026-10-20"),
                            ("later","2026-10-20","2026-10-25"),
                            ("recent","2026-10-25","2026-10-29")]:
        lo=int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()*1000)
        hi=int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp()*1000)
        if lo<end_ms-args.days*bt.DAY or hi>end_ms: continue
        rows=[]
        for name,run in results.items():
            trades=[t for t in bt.trades_of(run) if lo <= (t.get("close_ms") or 0) < hi]
            winning=[t for t in trades if t["net"]>0]
            losing=[t for t in trades if t["net"]<=0]
            rows.append({"variant":name,"n":len(trades),"net":round(sum(t["net"] for t in trades),2),
                         "wr":round(100*len(winning)/len(trades),2) if trades else None,
                         "profit_factor":round(sum(t["net"] for t in winning)/-sum(t["net"] for t in losing),3)
                         if losing and sum(t["net"] for t in losing)<0 else None,
                         "long":sum(t["side"]==1 for t in trades),
                         "short":sum(t["side"]==-1 for t in trades)})
        windows[label]=rows
    source_hash=hashlib.sha256()
    for symbol in sorted(data):
        source_hash.update(symbol.encode("ascii"))
        for tf in ("a15","a4","ad"):
            source_hash.update(data[symbol][tf].tobytes())
    out={"type":"BACKTEST_NOT_REAL_EXECUTION","portfolio":args.portfolio,
         "data":"synthetic" if args.synthetic else "Bitget_public_15m_4h_1d",
         "source_sha":OLD,"new_sha":"dc16e0169932c3885908625ce5be321a33b09a0f",
         "days":args.days,"step_bars":args.step,"symbols":list(data),
         "market_data_sha256":source_hash.hexdigest(),"periods":windows,
         "warnings":["No Claude/DeepSeek decision replay","No DCA or split","15m intrabar path unknown",
         "Old/new scorer and OHLC engine comparison only; not full production versions",
         "No optimization or forecast; inspect holdouts separately"],"variants":report}
    Path(args.output).write_text(json.dumps(out,indent=2)+"\n")
    bt.print_table(report,"AB classici - non operativo")
    print("LAB_ONLY_NO_DEPLOY")
if __name__=="__main__": main()
