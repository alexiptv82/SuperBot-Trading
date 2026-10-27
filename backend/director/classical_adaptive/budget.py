"""One durable, paced API allowance shared by the two Brain profiles.

Reserve conservatively before submitting a request; no refunds/retries after a
crash. This is an estimate using the existing configured model tariff, not a
provider billing reconciliation. Never reads classical bots' budget files.
"""
import math
import calendar
import hashlib
import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from director.ai_shadow.budget import worst_case_usd

DAY = 86400000


def baseline_from_spend(path):
    """Build from a copied old spend.jsonl; no keys/provider text is exported.

    Operator must verify the copy's provenance before activation. A checksum
    establishes byte integrity, not the authenticity of that attestation.
    """
    source=Path(path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size>16*1024*1024:
        raise ValueError("invalid_spend_source")
    raw=source.read_bytes();days={}
    if raw and not raw.endswith(b"\n"):raise ValueError("torn_spend_source")
    for line in raw.splitlines():
        row=json.loads(line)
        day=row.get("day");cost=row.get("cost")
        if not isinstance(day,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",day) or isinstance(cost,bool) or not isinstance(cost,(int,float)) or not math.isfinite(cost) or cost<0:
            raise ValueError("invalid_spend_record")
        time.strptime(day,"%Y-%m-%d")
        days[day]=days.get(day,0.)+cost
    return {"version":1,"mode":"paper","source_sha256":hashlib.sha256(raw).hexdigest(),"by_day":days}


class SharedBudget:
    def __init__(self, path, cfg, baseline=None):
        self.path, self.cfg = str(path), cfg
        if Path(path).is_symlink():raise ValueError("symlink_budget_ledger")
        # The old single Brain allowance is shared, not multiplied by two.
        if not (0 < cfg.daily_cap_usd <= .50 and 0 < cfg.monthly_cap_usd <= 12):
            raise ValueError("budget_increase_requires_separate_configuration_review")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS reservations (id TEXT PRIMARY KEY, profile TEXT NOT NULL, ts INTEGER NOT NULL, day TEXT NOT NULL, cost REAL NOT NULL CHECK(cost>=0))")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (id INTEGER PRIMARY KEY CHECK(id=1),baseline TEXT NOT NULL)")
            if db.execute("SELECT 1 FROM metadata").fetchone() is None:
                if db.execute("SELECT 1 FROM reservations").fetchone() or not isinstance(baseline,dict):
                    raise ValueError("verified_old_brain_spend_baseline_required")
                if set(baseline)!={"version","mode","source_sha256","by_day"} or baseline["version"]!=1 or baseline["mode"]!="paper" or not isinstance(baseline["source_sha256"],str) or not re.fullmatch(r"[a-f0-9]{64}",baseline["source_sha256"]) or not isinstance(baseline["by_day"],dict):
                    raise ValueError("invalid_spend_baseline")
                for day,cost in baseline["by_day"].items():
                    if not isinstance(day,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",day) or isinstance(cost,bool) or not isinstance(cost,(int,float)) or not math.isfinite(cost) or cost<0:
                        raise ValueError("invalid_spend_baseline")
                    stamp=int(calendar.timegm(time.strptime(day,"%Y-%m-%d"))*1000)
                    db.execute("INSERT INTO reservations VALUES (?,?,?,?,?)",("baseline:"+day,"legacy",stamp,day,cost))
                db.execute("INSERT INTO metadata VALUES (1,?)",(json.dumps(baseline,sort_keys=True,allow_nan=False),))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:yield db
        finally:db.close()

    def reserve(self, profile, now_ms, prompt_bytes, max_tokens):
        if profile not in ("hawk", "bull"):
            raise ValueError("unknown_profile")
        cfg = self.cfg
        # A token cannot consume less than a byte of ordinary UTF-8 input.
        # Include bounded protocol overhead, rather than assuming the old
        # 2.5 characters/token heuristic always holds for model/history text.
        estimator_chars=math.ceil((prompt_bytes+4096)*2.5)
        cost = math.ceil(worst_case_usd(cfg.model, now_ms, estimator_chars, max_tokens, cfg.cost_safety)*1e6)/1e6
        day = time.strftime("%Y-%m-%d", time.gmtime(now_ms/1000))
        # Each profile receives half the allowance, released over 24h. An
        # hourly-sized initial allowance permits an early call without using
        # the whole daily budget overnight. Never exceeds the hard daily cap.
        paced = cfg.daily_cap_usd * min(1., (now_ms % DAY + 3600000) / DAY)
        ident = f"{profile}:{now_ms//60000}"
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM reservations WHERE id=?", (ident,)).fetchone():
                return False, "already_reserved", 0.
            total = db.execute("SELECT COALESCE(SUM(cost),0) FROM reservations WHERE day=?", (day,)).fetchone()[0]
            own = db.execute("SELECT COALESCE(SUM(cost),0) FROM reservations WHERE day=? AND profile=?", (day,profile)).fetchone()[0]
            legacy = db.execute("SELECT COALESCE(SUM(cost),0) FROM reservations WHERE day=? AND profile='legacy'", (day,)).fetchone()[0]
            month = db.execute("SELECT COALESCE(SUM(cost),0) FROM reservations WHERE substr(day,1,7)=?", (day[:7],)).fetchone()[0]
            if total + cost > cfg.daily_cap_usd or month + cost > cfg.monthly_cap_usd:
                return False, "hard_budget_cap", 0.
            if own + cost > max(0.,paced-legacy)/2:
                return False, "paced_profile_allowance", 0.
            t=time.gmtime(now_ms/1000)
            month_fraction=(t.tm_mday-1+min(1.,(now_ms%DAY+3600000)/DAY))/calendar.monthrange(t.tm_year,t.tm_mon)[1]
            if month+cost>cfg.monthly_cap_usd*month_fraction:
                return False,"paced_monthly_allowance",0.
            db.execute("INSERT INTO reservations VALUES (?,?,?,?,?)", (ident,profile,now_ms,day,cost))
        return True, ident, cost

    def view(self,now_ms,profile):
        day=time.strftime("%Y-%m-%d",time.gmtime(now_ms/1000))
        with self.connect() as db:
            daily=db.execute("SELECT COALESCE(SUM(cost),0) FROM reservations WHERE day=?",(day,)).fetchone()[0]
            monthly=db.execute("SELECT COALESCE(SUM(cost),0) FROM reservations WHERE substr(day,1,7)=?",(day[:7],)).fetchone()[0]
            own,count=db.execute("SELECT COALESCE(SUM(cost),0),COUNT(*) FROM reservations WHERE day=? AND profile=?",(day,profile)).fetchone()
        return {"accounting":"conservative_reservations_not_provider_invoice","daily_reserved":daily,
                "monthly_reserved":monthly,"profile_reserved":own,"profile_calls":count,
                "shared_daily_cap":self.cfg.daily_cap_usd,"shared_monthly_cap":self.cfg.monthly_cap_usd}
