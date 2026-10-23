"""Read-only Capital V1 dashboard adapter + guarded PAPER withdrawal queue.

The app NEVER edits account cash, vault or ledger; only the bot may do that.
If the capability is absent or the portfolio is not reconciled, fail closed.
Do not expose a writable balance endpoint.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import tempfile
import time

EVENT_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
REQUEST_FILE = "vault_transfer_request.json"


class CapitalUnavailable(ValueError):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def read_json(path):
    try:
        with open(path, encoding="utf8") as f:
            x = json.load(f)
        return x if isinstance(x, dict) else {}
    except (ValueError, OSError):
        return {}


def money(value):
    try:
        if isinstance(value, bool):
            raise ValueError("boolean")
        n = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError) as e:
        raise CapitalUnavailable("invalid_amount", "Importo non valido") from e
    if not n.is_finite():
        raise CapitalUnavailable("invalid_amount", "Importo non valido")
    return n


def _core(data_dir):
    root=Path(data_dir)
    state=read_json(root/"state_v2.json")
    hb=read_json(root/"heartbeat.json")
    capital=state.get("capital") or {}
    if not isinstance(capital, dict) or capital.get("schema_version") != 1:
        return state, hb, {}, False
    ready=(capital.get("status")=="READY" and hb.get("capital_v1") is True)
    return state, hb, capital, ready


def status(data_dir, portfolio):
    if portfolio not in ("hawk","bull"):
        raise CapitalUnavailable("invalid_portfolio","Portafoglio non valido")
    state,hb,capital,ready=_core(data_dir)
    if not ready:
        return {"available":False,"portfolio":portfolio,"message":"Gestione capitale V1 non ancora attiva sul bot PAPER.","version":hb.get("version")}
    day=capital.get("day") or {}
    vault=capital.get("vault") or {}
    acc=state.get("main") or {}
    for val in (vault.get("balance"), day.get("day_budget"), day.get("equity_at_boundary")):
        money(val)
    pending=sum((money(x.get("remaining",0)) for x in vault.get("pending",[])),Decimal("0"))
    vault_balance=money(vault["balance"])
    budget=money(day["day_budget"])
    if min(pending,vault_balance,budget)<0 or budget>1000:
        raise CapitalUnavailable("invalid_state","Contabilità non riconciliata")
    actual=money(acc.get("cash",0))+sum((money(x.get("total_margin",0)) for x in
                                         (acc.get("positions") or {}).values()),Decimal("0"))
    unrealized=money((capital.get("valuation") or {}).get("unrealized",0))
    # Only the bot may declare valuation fresh. For open positions this must
    # also be a recent timestamp; an old 30-minute candle is not "live".
    val=capital.get("valuation") or {}
    has_positions=bool(acc.get("positions"))
    try:
        age_ms=int(time.time()*1000)-int(val.get("valuation_ms",0))
    except (ValueError,TypeError):
        age_ms=999999999
    is_fresh=(not has_positions) or (val.get("fresh") is True and 0<=age_ms<=120000)
    equity=actual+unrealized if is_fresh else None
    return {"available":True,"portfolio":portfolio,"ready":True,
            "version":hb.get("version"),"revision":capital.get("revision"),
            "utc_day":day.get("utc_day"),"day_budget":str(budget),
            "day_reference_equity":str(money(day["equity_at_boundary"])),
            "operating_equity":str(equity) if equity is not None else None,
            "operating_cash":str(money(acc.get("cash",0))),
            "margin_used":str(actual-money(acc.get("cash",0))),
            "vault_balance":str(vault_balance),"pending":str(pending),
            "total_equity":str(equity+vault_balance) if equity is not None else None,
            "daily_stop_pct":"20", "position_cap_pct":"10" if portfolio=="hawk" else "25",
            "kill_equity":"450","valuation_fresh":is_fresh,
            "stop_latched":bool(day.get("stop_latched",False)),
            "can_withdraw":is_fresh and hb.get("exec_mode")=="paper"}


def queue_manual_withdraw(data_dir, portfolio, body):
    state,hb,capital,ready=_core(data_dir)
    if portfolio not in ("hawk","bull") or not ready or hb.get("exec_mode")!="paper":
        raise CapitalUnavailable("not_ready","Prelievi disabilitati: bot PAPER V1 non pronto")
    if os.environ.get("DESK_MODE","paper").lower()!="paper":
        raise CapitalUnavailable("not_paper","Operazione consentita solo in PAPER")
    if not isinstance(body,dict):
        raise CapitalUnavailable("invalid_request","Richiesta non valida")
    event_id=body.get("idempotency_key")
    if not isinstance(event_id,str) or not EVENT_RE.fullmatch(event_id):
        raise CapitalUnavailable("invalid_request","ID richiesta non valido")
    amount=money(body.get("amount"))
    if amount<=0 or amount != amount.quantize(Decimal("0.01")):
        raise CapitalUnavailable("invalid_amount","Importo positivo con massimo due decimali")
    if not isinstance(body.get("expected_revision"),int) or isinstance(body.get("expected_revision"),bool):
        raise CapitalUnavailable("invalid_revision","Revisione obbligatoria")
    vault=capital.get("vault") or {}
    receipts=capital.get("receipts") or {}
    if event_id in receipts:
        rec=receipts[event_id]
        if money(rec.get("amount"))!=amount:
            raise CapitalUnavailable("id_reused","ID già usato con un altro importo")
        return {"queued":False,"status":rec.get("status","completed"),"idempotency_key":event_id}
    request={"kind":"manual_vault_withdraw","portfolio":portfolio,
             "idempotency_key":event_id,"amount":str(amount),
             "expected_revision":body["expected_revision"]}
    path=Path(data_dir)/REQUEST_FILE
    if path.exists():
        old=read_json(path)
        if old==request:
            return {"queued":True,"status":"pending","idempotency_key":event_id}
        raise CapitalUnavailable("busy","Esiste già un trasferimento in attesa")
    if body["expected_revision"]!=capital.get("revision"):
        raise CapitalUnavailable("stale_revision","Saldo cambiato: aggiorna la pagina")
    if money(vault.get("balance",0))<amount:
        raise CapitalUnavailable("insufficient_vault","Saldo salvadanaio insufficiente")
    # Atomic no-overwrite creation. A concurrent request cannot replace another.
    root=Path(data_dir)
    fd,tmp=tempfile.mkstemp(prefix=".vault-req-",dir=root)
    try:
        with os.fdopen(fd,"w",encoding="utf8") as f:
            json.dump(request,f,sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.link(tmp,path)  # O_EXCL semantics: link creation fails if target exists
        except FileExistsError as e:
            raise CapitalUnavailable("busy","Esiste già un trasferimento in attesa") from e
        dir_fd=os.open(str(root),os.O_RDONLY)
        try:os.fsync(dir_fd)
        finally:os.close(dir_fd)
    finally:
        os.unlink(tmp)
    return {"queued":True,"status":"pending","idempotency_key":event_id}


def transfer_status(data_dir, event_id):
    if not isinstance(event_id,str) or not EVENT_RE.fullmatch(event_id):
        raise CapitalUnavailable("invalid_request","ID non valido")
    state,hb,capital,ready=_core(data_dir)
    if not ready:
        raise CapitalUnavailable("not_ready","Bot V1 non pronto")
    receipt=(capital.get("receipts") or {}).get(event_id)
    if receipt:
        return {"idempotency_key":event_id,"status":receipt.get("status","unknown"),
                "reason":receipt.get("reason","")}
    pending=read_json(Path(data_dir)/REQUEST_FILE)
    if pending.get("idempotency_key")==event_id:
        return {"idempotency_key":event_id,"status":"pending"}
    raise CapitalUnavailable("not_found","Trasferimento non trovato")
