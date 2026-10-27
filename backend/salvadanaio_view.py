"""Read-only projection of the PAPER vault-only policy from one state snapshot."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def _amount(value):
    if isinstance(value, bool):
        raise ValueError("invalid money")
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError("invalid money")
    return n


def build_view(state, heartbeat, now):
    unavailable = {"available": False, "label": "Salvadanaio",
                   "message": "Salvadanaio non ancora attivo sul bot PAPER."}
    hb = heartbeat or {}
    cap = state.get("capital") or {}
    if hb.get("exec_mode") != "paper" or cap.get("policy") != "salvadanaio-only-v1":
        return unavailable
    try:
        vault = cap["vault"]
        balance = _amount(vault["balance"])
        pending = sum((_amount(x["remaining"]) for x in vault.get("pending", [])), Decimal(0))
        if min(balance, pending) < 0:
            raise ValueError("negative vault")
        daily = {}
        for row in cap.get("deposits", []):
            day = row["utc_day"]
            datetime.strptime(day, "%Y-%m-%d")
            amount = _amount(row["amount"])
            if amount < 0 or row["kind"] not in ("rollover", "pending_settled"):
                raise ValueError("invalid vault deposit")
            daily[day] = daily.get(day, Decimal(0)) + amount
        today = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
        deposits = [{"utc_day": day, "amount": str(value)} for day, value in sorted(daily.items(), reverse=True)]
        return {"available": True, "label": "Salvadanaio", "paper": True,
                "balance": str(balance), "pending": str(pending),
                "deposited_today": str(daily.get(today, Decimal(0))),
                "today_utc": today, "days": deposits[:60], "day_count": len(deposits),
                "status": cap.get("status"), "ready": cap.get("status") == "READY",
                "bot_online": hb.get("age_s", float("inf")) < 300,
                "message": "Accantonamenti netti sopra 1.000 $. Dopo perdite resta il residuo; nessun reintegro."}
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return {**unavailable, "message": "Contabilità del Salvadanaio non leggibile: verifica necessaria."}
