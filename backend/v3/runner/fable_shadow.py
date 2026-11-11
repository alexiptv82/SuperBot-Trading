"""Optional, PAPER-ONLY Fable 5.2 shadow adviser for Brain V3.

DeepSeek remains the ONLY decision-making analyst. Fable opinions are stored
separately and never fed into the decision, risk manager or execution path.

Enabled solely by TWO explicit runtime environment gates. No changes to
runner_config.json, the hashed risk mandate, or the existing budget.db.
The 5 USD UTC-month budget uses conservative reservations committed BEFORE
each API request, so restarts, future Brain run IDs and concurrent attempts cannot overspend
this module's shared monthly allowance based on the published token tariff.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
import time
from typing import Callable, Mapping, Optional

from backend.v3.brain_f2.analyst import Analyst
from backend.v3.brain_f2.contracts import BrainDecision, DecisionKind, MarketContext, OpenProposal
from backend.v3.brain_f3.providers import Transport, TransportResponse

MODEL = "claude-fable-5-2"
INPUT_USD_PER_MTOK = 8
OUTPUT_USD_PER_MTOK = 40
MONTHLY_CAP_MICRO = 5_000_000
MAX_TOKENS = 1536
MAX_PAYLOAD_BYTES = 6400
MAX_PER_DAY = 2
SAME_SYMBOL_COOLDOWN_MS = 6 * 60 * 60 * 1000
PROMPT = (
    "You are an independent risk critic for a simulated PAPER-only crypto bot. "
    "The principal DeepSeek recommendation is NOT your command. "
    "Review trend reversals, leverage and stop distance using ONLY the short data provided. "
    "Return a compact JSON object with EXACT keys assessment, risk_code, summary. "
    "assessment: support|caution|uncertain. "
    "risk_code: trend_reversal|leverage|stop_distance|liquidity|insufficient_data|none. "
    "summary: one factual sentence max 130 characters, no personal details. "
    "Do not issue orders, change stops, or claim certainty/profit."
)
ASSESSMENTS = frozenset({"support", "caution", "uncertain"})
REASONS = frozenset({
    "trend_reversal", "leverage", "stop_distance", "liquidity",
    "insufficient_data", "none",
})
log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _utc_parts(now_ms: int) -> tuple[str, str]:
    d = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc)
    return d.strftime("%Y-%m"), d.strftime("%Y-%m-%d")


def _usage_cost_micro(body: Mapping) -> Optional[int]:
    usage = body.get("usage")
    if type(usage) is not dict:
        return None
    inp = usage.get("input_tokens")
    out = usage.get("output_tokens")
    if not (type(inp) is int and type(out) is int and 0 <= inp <= 100_000
            and 0 <= out <= MAX_TOKENS):
        return None
    # No caching or fast mode requested. If a provider supplies cache token
    # categories, record an upper-bound billed estimate rather than a low figure.
    cached = usage.get("cache_read_input_tokens", 0)
    created = usage.get("cache_creation_input_tokens", 0)
    if type(cached) is not int or cached < 0 or type(created) is not int or created < 0:
        return None
    return (inp + cached + created) * INPUT_USD_PER_MTOK + out * OUTPUT_USD_PER_MTOK


def _read_opinion(body: Mapping) -> Optional[tuple[str, str, str]]:
    blocks = body.get("content")
    if type(blocks) is not list:
        return None
    texts = [b.get("text") for b in blocks if type(b) is dict and b.get("type") == "text"]
    if len(texts) != 1 or type(texts[0]) is not str or len(texts[0]) > 2048:
        return None
    try:
        opinion = json.loads(
            texts[0],
            object_pairs_hook=lambda pairs: _unique(pairs),
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, TypeError):
        return None
    if type(opinion) is not dict or set(opinion) != {"assessment", "risk_code", "summary"}:
        return None
    assessment, reason, summary = (
        opinion["assessment"], opinion["risk_code"], opinion["summary"]
    )
    if (assessment not in ASSESSMENTS or reason not in REASONS
            or type(summary) is not str or not 1 <= len(summary) <= 130
            or any(ord(ch) < 32 for ch in summary)):
        return None
    return assessment, reason, summary


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


class FableLedger:
    """One writer/many readers, atomic reservations in a private SQLite file.

    Reserved units are never refunded, even on API timeout, giving conservative
    month-level protection. Results are appended once, not rewritten.
    """

    def __init__(self, path: Path, run_id: str, clock_ms: Callable[[], int] = _now_ms):
        if not path.is_absolute() or not run_id or not callable(clock_ms):
            raise ValueError("invalid_fable_ledger")
        if path.is_symlink():
            raise ValueError("symlink_ledger")
        self.run_id, self.clock_ms = run_id, clock_ms
        self._lock = threading.RLock()
        if path.parent.is_symlink():
            raise ValueError("symlink_budget_directory")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if (path.parent.stat().st_mode & 0o077):
            raise ValueError("budget_directory_not_private")
        if path.exists():
            if not path.is_file() or (path.stat().st_mode & 0o077):
                raise ValueError("budget_file_not_private")
        else:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                         getattr(os, "O_NOFOLLOW", 0), 0o600)
            os.close(fd)
        self._db = sqlite3.connect(str(path), timeout=15, isolation_level=None,
                                   check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""CREATE TABLE IF NOT EXISTS fable_observations(
            run_id TEXT NOT NULL, symbol TEXT NOT NULL, market_ms INTEGER NOT NULL,
            regime TEXT NOT NULL,
            PRIMARY KEY(run_id, symbol, market_ms))""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS fable_reservations(
            request_id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
            month TEXT NOT NULL, day TEXT NOT NULL, created_ms INTEGER NOT NULL,
            symbol TEXT NOT NULL, trigger TEXT NOT NULL, reserved_micro INTEGER NOT NULL)""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS fable_results(
            request_id TEXT PRIMARY KEY, completed_ms INTEGER NOT NULL,
            actual_micro INTEGER, status TEXT NOT NULL,
            assessment TEXT, risk_code TEXT, summary TEXT)""")
        os.chmod(path, 0o600)

    def eligible_and_reserve(
        self, *, symbol: str, market_ms: int, regime: str, decision: BrainDecision,
        reserve_micro: int, request_id: str,
    ) -> Optional[str]:
        if not isinstance(decision, BrainDecision) or not isinstance(regime, str):
            return None
        now = self.clock_ms()  # wall clock, NEVER caller-supplied market timestamp for budget
        month, day = _utc_parts(now)
        if not (type(reserve_micro) is int and 0 < reserve_micro <= MONTHLY_CAP_MICRO):
            return None
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                prev = self._db.execute(
                    "SELECT regime FROM fable_observations "
                    "WHERE run_id=? AND symbol=? ORDER BY market_ms DESC LIMIT 1",
                    (self.run_id, symbol),
                ).fetchone()
                self._db.execute(
                    "INSERT OR IGNORE INTO fable_observations VALUES (?,?,?,?)",
                    (self.run_id, symbol, market_ms, regime),
                )
                trend_changed = prev is not None and prev[0] != regime
                proposal = decision.proposal
                trigger = None
                if trend_changed:
                    trigger = "trend_transition"
                elif decision.kind == DecisionKind.OPEN and isinstance(proposal, OpenProposal):
                    if regime == "VOLATILE":
                        trigger = "volatile_open"
                    elif proposal.leverage >= 40:
                        trigger = "high_leverage"
                    elif proposal.confidence <= 0.62:
                        trigger = "low_confidence"
                if trigger is None:
                    self._db.execute("COMMIT")
                    return None
                spent = self._db.execute(
                    "SELECT COALESCE(SUM(reserved_micro),0) FROM fable_reservations "
                    "WHERE month=?",
                    (month,),
                ).fetchone()[0]
                if spent + reserve_micro > MONTHLY_CAP_MICRO:
                    self._db.execute("COMMIT")
                    return None
                day_count = self._db.execute(
                    "SELECT COUNT(*) FROM fable_reservations WHERE day=?",
                    (day,),
                ).fetchone()[0]
                if day_count >= MAX_PER_DAY:
                    self._db.execute("COMMIT")
                    return None
                last = self._db.execute(
                    "SELECT MAX(created_ms) FROM fable_reservations "
                    "WHERE symbol=?",
                    (symbol,),
                ).fetchone()[0]
                if last is not None and now - last < SAME_SYMBOL_COOLDOWN_MS:
                    self._db.execute("COMMIT")
                    return None
                try:
                    self._db.execute(
                        "INSERT INTO fable_reservations VALUES (?,?,?,?,?,?,?,?)",
                        (request_id, self.run_id, month, day, now, symbol, trigger, reserve_micro),
                    )
                except sqlite3.IntegrityError:
                    self._db.execute("COMMIT")
                    return None
                self._db.execute("COMMIT")
                return trigger
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def record(self, request_id: str, *, actual_micro: Optional[int], status: str,
               opinion: Optional[tuple[str, str, str]] = None) -> None:
        if status not in ("ok", "invalid_response", "provider_error"):
            raise ValueError("invalid_status")
        # Never store raw provider response or user credentials.
        fields = opinion or (None, None, None)
        with self._lock:
            self._db.execute(
                "INSERT INTO fable_results VALUES (?,?,?,?,?,?,?)",
                (request_id, self.clock_ms(), actual_micro, status, *fields),
            )

    def monthly_reserved_micro(self) -> int:
        month, _ = _utc_parts(self.clock_ms())
        with self._lock:
            return int(self._db.execute(
                "SELECT COALESCE(SUM(reserved_micro),0) "
                "FROM fable_reservations WHERE month=?",
                (month,),
            ).fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._db.close()


class FableShadowAdviser:
    """Invoked only after a DeepSeek result; no authority over that result."""

    def __init__(self, *, ledger: FableLedger, transport: Transport,
                 enabled: bool = False):
        self.ledger, self.transport, self.enabled = ledger, transport, enabled

    def observe(self, context: MarketContext, decision: BrainDecision) -> None:
        if self.enabled is not True:
            return
        if (not isinstance(context, MarketContext) or not isinstance(decision, BrainDecision)
                or not isinstance(context.symbol, str)
                or not isinstance(context.timestamp_ms, int)):
            return
        proposal = decision.proposal if isinstance(decision.proposal, OpenProposal) else None
        case = {
            "symbol": context.symbol,
            "regime": context.regime,
            "price": str(context.price),
            "decision": decision.kind.value,
            "side": proposal.side if proposal else None,
            "leverage": proposal.leverage if proposal else None,
            "confidence": round(proposal.confidence, 3) if proposal else None,
            "entry": str(proposal.entry_price) if proposal else None,
            "stop": str(proposal.stop_price) if proposal else None,
            "market_ms": context.timestamp_ms,
        }
        # No private history, keys, free-form peer signals or raw model rationale.
        payload = {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "output_config": {"effort": "low"},
            "messages": [
                {"role": "user", "content": PROMPT + "\n" + json.dumps(case, sort_keys=True)},
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_PAYLOAD_BYTES:
            return
        # Conservative upper bound: 2 input tokens per UTF-8 byte plus the
        # hard output cap. No fast mode, cache, tools, or extra server calls.
        reserve_micro = 2 * len(raw) * INPUT_USD_PER_MTOK + MAX_TOKENS * OUTPUT_USD_PER_MTOK
        request_id = hashlib.sha256(
            (self.ledger.run_id + ":" + context.symbol + ":" +
             str(context.timestamp_ms) + ":" + decision.kind.value).encode("utf-8")
        ).hexdigest()
        trigger = self.ledger.eligible_and_reserve(
            symbol=context.symbol, market_ms=context.timestamp_ms,
            regime=context.regime, decision=decision, reserve_micro=reserve_micro,
            request_id=request_id,
        )
        if trigger is None:
            return
        try:
            response = self.transport(payload)
            if not isinstance(response, TransportResponse) or response.status_code != 200:
                self.ledger.record(request_id, actual_micro=None, status="invalid_response")
                return
            cost = _usage_cost_micro(response.body)
            opinion = _read_opinion(response.body)
            self.ledger.record(
                request_id, actual_micro=cost,
                status="ok" if opinion else "invalid_response", opinion=opinion)
        except Exception:
            try:
                self.ledger.record(request_id, actual_micro=None, status="provider_error")
            except Exception:
                pass


class ShadowFableAnalyst(Analyst):
    """Non-blocking observer: never delays or changes DeepSeek's decision."""

    def __init__(self, primary: Analyst, shadow: FableShadowAdviser):
        if not isinstance(primary, Analyst) or not isinstance(shadow, FableShadowAdviser):
            raise ValueError("invalid_shadow_analyst")
        self.primary, self.shadow = primary, shadow
        # At most ONE pending Fable consultation, always outside the real
        # execution decision path. An HTTP timeout must never delay an OPEN
        # nor the independent exit sidecar.
        self._pending = threading.Lock()

    def analyze(self, context: MarketContext, open_positions: list[Mapping]) -> BrainDecision:
        decision = self.primary.analyze(context, open_positions)
        if not self.shadow.enabled or not self._pending.acquire(blocking=False):
            return decision

        def _consult() -> None:
            try:
                self.shadow.observe(context, decision)
            except Exception:
                # Never log provider bodies, prompts, or key values.
                log.warning("fable_shadow_unavailable")
            finally:
                self._pending.release()

        try:
            threading.Thread(
                target=_consult, name="brain-fable-shadow", daemon=True).start()
        except Exception:
            self._pending.release()
            log.warning("fable_shadow_thread_unavailable")
        # The EXACT DeepSeek decision object is returned without waiting for
        # Fable to complete. Results are SHADOW-only.
        return decision
