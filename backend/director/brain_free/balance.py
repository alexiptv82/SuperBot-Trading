"""Read-only DeepSeek credit check; never authorizes trades or logs credentials.

The API can return multiple currencies. Never compare CNY to a USD threshold.
Network/parse failures are observational only, never a trading gate.
"""
from decimal import Decimal, InvalidOperation
import json
import os
import urllib.request

BALANCE_URL = "https://api.deepseek.com/user/balance"


def low_balance_threshold(raw=None):
    """USD threshold from environment; no GitHub secret is required."""
    if raw is None:
        raw = os.getenv("DEEPSEEK_LOW_BALANCE_USD", "2.0")
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or not Decimal("0") < value <= Decimal("100000"):
            raise ValueError("invalid_low_balance_threshold")
        return value
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid_low_balance_threshold") from exc


def check_balance(api_key, opener=urllib.request.urlopen, timeout=8):
    """Return a small sanitized status; no raw API payload, key or headers."""
    if not api_key:
        return {"status": "missing_key"}
    req = urllib.request.Request(
        BALANCE_URL,
        headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with opener(req, timeout=timeout) as response:
            payload = json.loads(response.read(65537))
        if not isinstance(payload, dict) or type(payload.get("is_available")) is not bool:
            raise ValueError("invalid_balance_response")
        rows = payload.get("balance_infos")
        if not isinstance(rows, list) or len(rows) > 20:
            raise ValueError("invalid_balance_rows")
        usd = []
        for row in rows:
            if not isinstance(row, dict) or row.get("currency") not in ("USD", "CNY"):
                raise ValueError("invalid_balance_currency")
            if row["currency"] != "USD":
                continue
            amount = Decimal(str(row.get("total_balance")))
            if not amount.is_finite() or not Decimal(0) <= amount <= Decimal("1000000000"):
                raise ValueError("invalid_balance_amount")
            usd.append(amount)
        if len(usd) > 1:
            raise ValueError("duplicate_usd_balance")
        return {
            "status": "ok",
            "is_available": payload["is_available"],
            "usd_balance": usd[0] if usd else None,
        }
    except Exception:
        # Includes HTTP errors, timeouts and invalid JSON: none disables trading.
        return {"status": "unavailable"}


def unavailable_message(status):
    """Operator-facing provider attribution, with safe bounded fallbacks."""
    reasons = {
        "balance": "credito esaurito (balance)",
        "rate": "limite di chiamate (rate limit)",
        "auth": "chiave API non valida (auth)",
        "missing_key": "chiave API mancante (missing_key)",
        "provider_http": "errore HTTP del provider (provider_http)",
        "provider_network_or_format": "errore di rete o formato (provider_network_or_format)",
        "provider_failed": "chiamata al provider non riuscita (provider_failed)",
    }
    reason = reasons.get(status)
    if reason is None:
        safe = str(status)[:64]
        safe = "".join(c for c in safe if c.isascii() and (c.isalnum() or c in "_-"))
        reason = safe or "errore sconosciuto"
    return "[BRAIN] DeepSeek non disponibile: " + reason + ". Stop locali attivi, nessun fallback alle regole."


def credit_alert(result, threshold):
    """Return operator notice or None; unknown currency never becomes USD."""
    if not isinstance(result, dict) or result.get("status") != "ok":
        return None
    if result.get("is_available") is False:
        return "[BRAIN] ⚠️ Credito DeepSeek non disponibile: account senza credito utilizzabile. Ricaricare per riprendere le analisi AI."
    balance = result.get("usd_balance")
    if isinstance(balance, Decimal) and balance < threshold:
        return "[BRAIN] ⚠️ Credito DeepSeek basso: $" + format(balance, ".2f") + " rimasti. Ricaricare per non fermare il Brain."
    return None
