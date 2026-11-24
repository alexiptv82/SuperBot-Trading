"""Pure PAPER risk quotation for V3 design tests (NOT an order executor).

No strategy rules, market connector, credentials, wallet writes or AI calls.
All risk limits MUST be supplied by a versioned, user-approved policy:
this module does not set or approve production percentages.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, InvalidOperation


def _d(value: object) -> Decimal:
    try:
        out = Decimal(str(value))
        if not out.is_finite():
            raise ValueError("non_finite")
        return out
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("invalid_number") from exc


@dataclass(frozen=True)
class RiskPolicy:
    max_loss_fraction: Decimal
    max_open_risk_fraction: Decimal
    max_position_margin_fraction: Decimal
    max_total_margin_fraction: Decimal
    minimum_equity: Decimal
    estimated_roundtrip_cost_bp: Decimal
    liquidation_buffer_fraction: Decimal
    # Optional PAPER profile: none/1x..125x preserves historical behavior.
    # 75 USDT risk on 350 USDT margin = 0.214285714285... of actual margin.
    max_loss_margin_fraction: Decimal | None = None
    min_leverage: int = 1
    max_leverage: int = 125
    # Profilo aggressivo (Falco Evoluto / Brain Scalp, 23/11). None = comportamento storico invariato.
    min_margin: Decimal | None = None             # margine minimo per trade, USDT: sotto -> NO_TRADE (mai rischio in piu')
    max_margin: Decimal | None = None             # margine massimo per trade, USDT
    max_positions: int | None = None              # posizioni aperte contemporanee
    # Esposizione correlata: le crypto del runner si muovono con BTC. Rischio a stop di TUTTE le posizioni nella
    # stessa direzione (piu' la nuova) entro questa frazione dell'equity.
    max_same_side_risk_fraction: Decimal | None = None
    # Brain unico (24/11): la leva e' scelta dal motore (la piu' bassa che raggiunge la dimensione massima), non
    # quella proposta dall'AI. Non cambia nessun controllo di questo modulo: vedi ``brain_f2/engine.py``.
    leverage_fit: bool = False


@dataclass(frozen=True)
class RiskRequest:
    equity: Decimal
    available_cash: Decimal
    margin_used: Decimal
    existing_open_risk: Decimal
    entry_price: Decimal
    stop_price: Decimal
    side: int  # +1 LONG, -1 SHORT
    requested_leverage: int
    exchange_leverage_limit: int
    quantity_step: Decimal
    minimum_notional: Decimal
    maintenance_fraction: Decimal
    market_data_fresh: bool
    paused: bool
    daily_loss_latched: bool
    open_positions: int = 0
    same_side_open_risk: Decimal = Decimal("0")   # rischio a stop delle posizioni aperte nella stessa direzione
    external_risk_cap: Decimal | None = None      # tetto del Profit Guardian (USDT); None = nessun tetto esterno


@dataclass(frozen=True)
class RiskQuote:
    allowed: bool
    reason: str
    quantity: Decimal = Decimal("0")
    notional: Decimal = Decimal("0")
    margin: Decimal = Decimal("0")
    worst_case_loss_estimate: Decimal = Decimal("0")
    risk_budget: Decimal = Decimal("0")


def _rejected(reason: str) -> RiskQuote:
    return RiskQuote(False, reason)


def estimated_loss_per_unit(price: Decimal, stop: Decimal, roundtrip_cost_bp: Decimal) -> Decimal:
    """Perdita STIMATA allo stop per unita': distanza dallo stop piu' i costi stimati andata e ritorno sul prezzo.
    Unica formula, usata dal RiskManager per la nuova posizione e dalla ricostruzione del rischio aperto
    (``cycle.snapshot_from_summary``) per quelle gia' aperte: le due misure restano coerenti per costruzione."""
    return abs(price - stop) + price * (roundtrip_cost_bp / Decimal("10000"))


def _aggressive_limits(policy: RiskPolicy, request: RiskRequest):
    """Limiti opzionali del profilo aggressivo: (min_margin, max_margin, same_side_fraction, guardian_cap) o rifiuto."""
    try:
        mn = None if policy.min_margin is None else _d(policy.min_margin)
        mx = None if policy.max_margin is None else _d(policy.max_margin)
        side = None if policy.max_same_side_risk_fraction is None else _d(policy.max_same_side_risk_fraction)
        cap = None if request.external_risk_cap is None else _d(request.external_risk_cap)
        same = _d(request.same_side_open_risk)
    except ValueError:
        return _rejected("invalid_numeric_input")
    if ((mn is not None and mn <= 0) or (mx is not None and mx <= 0) or (mn is not None and mx is not None and mn > mx)
            or (side is not None and not Decimal("0") < side <= Decimal("1")) or same < 0
            or (policy.max_positions is not None
                and (type(policy.max_positions) is not int or not 1 <= policy.max_positions <= 100))
            or type(request.open_positions) is not int or request.open_positions < 0):
        return _rejected("invalid_policy_or_market")
    if policy.max_positions is not None and request.open_positions >= policy.max_positions:
        return _rejected("max_positions_reached")
    return mn, mx, side, cap


def quote_paper_risk(policy: RiskPolicy, request: RiskRequest) -> RiskQuote:
    """Return a conservative quote, not an order.

    The stop-loss estimate includes a configurable round-trip cost buffer;
    execution gaps and market liquidation can still exceed that estimate.
    """
    if request.paused or request.daily_loss_latched:
        return _rejected("portfolio_locked")
    if not request.market_data_fresh:
        return _rejected("stale_market_data")
    if type(request.side) is not int or request.side not in (-1, 1):
        return _rejected("invalid_side")
    if (type(policy.min_leverage) is not int or type(policy.max_leverage) is not int
            or not 1 <= policy.min_leverage <= policy.max_leverage <= 125):
        return _rejected("invalid_policy_or_market")
    if (type(request.requested_leverage) is not int
            or type(request.exchange_leverage_limit) is not int
            or request.requested_leverage <= 0
            or request.exchange_leverage_limit <= 0
            or request.requested_leverage > request.exchange_leverage_limit):
        return _rejected("invalid_leverage")
    if not policy.min_leverage <= request.requested_leverage <= policy.max_leverage:
        return _rejected("leverage_outside_profile")

    try:
        if policy.max_loss_margin_fraction is not None:
            loss_per_margin = _d(policy.max_loss_margin_fraction)
            if not Decimal("0") < loss_per_margin <= Decimal("1"):
                return _rejected("invalid_policy_or_market")
        else:
            loss_per_margin = None
        p = [_d(x) for x in (
            policy.max_loss_fraction, policy.max_open_risk_fraction,
            policy.max_position_margin_fraction, policy.max_total_margin_fraction,
            policy.minimum_equity, policy.estimated_roundtrip_cost_bp,
            policy.liquidation_buffer_fraction)]
        q = [_d(x) for x in (
            request.equity, request.available_cash, request.margin_used,
            request.existing_open_risk, request.entry_price, request.stop_price,
            request.quantity_step, request.minimum_notional,
            request.maintenance_fraction)]
    except ValueError:
        return _rejected("invalid_numeric_input")
    (per_trade, total_risk, position_margin, total_margin,
     floor, costs_bp, buffer) = p
    (equity, cash, used_margin, used_risk, price, stop, step, minimum,
     maintenance) = q
    if (not (Decimal("0") < per_trade <= total_risk <= Decimal("1"))
        or not (Decimal("0") < position_margin <= total_margin <= Decimal("1"))
        or not (Decimal("0") < buffer <= Decimal("1"))
        or floor < 0 or costs_bp < 0 or price <= 0 or stop <= 0
        or step <= 0 or minimum < 0 or cash < 0 or used_risk < 0
        or used_margin < 0 or not (Decimal("0") <= maintenance < Decimal("1"))):
        return _rejected("invalid_policy_or_market")

    if equity <= floor:
        return _rejected("equity_floor_reached")
    extra = _aggressive_limits(policy, request)
    if isinstance(extra, RiskQuote):
        return extra
    min_margin, max_margin, side_room, guardian_cap = extra
    if ((request.side == 1 and stop >= price)
            or (request.side == -1 and stop <= price)):
        return _rejected("stop_wrong_side")

    leverage = Decimal(request.requested_leverage)
    cost_fraction = costs_bp / Decimal("10000")
    stop_fraction = abs(price - stop) / price
    liquid_dist = Decimal("1") / leverage - maintenance - cost_fraction
    if liquid_dist <= 0 or stop_fraction >= liquid_dist * buffer:
        return _rejected("stop_near_liquidation")
    # This is a bound on loss vs ACTUAL filled margin, not only equity.
    # Downsizing alone cannot change this ratio: a shorter stop or a lower
    # leverage is necessary. The Brain can try a safer leverage before veto.
    if loss_per_margin is not None and leverage * (stop_fraction + cost_fraction) > loss_per_margin:
        return _rejected("margin_loss_ratio_exceeded")

    if guardian_cap is not None and guardian_cap <= 0:
        return _rejected("guardian_budget_exhausted")
    # Il rischio autorizzato e' il MINORE fra tutti i limiti applicabili (mai aumentato per rispettare leva o margine).
    risk_budget = min(x for x in (
        equity * per_trade,
        equity * total_risk - used_risk,
        equity - floor - used_risk,
        None if side_room is None else equity * side_room - _d(request.same_side_open_risk),
        guardian_cap,
    ) if x is not None)
    if risk_budget <= 0:
        return _rejected("risk_budget_exhausted")

    # Cash reserves include the configured cost buffer; this is deliberately
    # stricter than reserving only the opening fee.
    cash_margin = cash / (Decimal("1") + leverage * cost_fraction)
    margin_budget = min(x for x in (
        equity * position_margin,
        equity * total_margin - used_margin,
        cash_margin,
        max_margin,
    ) if x is not None)
    if margin_budget <= 0:
        return _rejected("margin_budget_exhausted")

    loss_per_unit = estimated_loss_per_unit(price, stop, costs_bp)
    quantity_by_risk = risk_budget / loss_per_unit
    quantity_by_margin = margin_budget * leverage / price
    max_qty = min(quantity_by_risk, quantity_by_margin)
    steps = (max_qty / step).to_integral_value(rounding=ROUND_DOWN)
    quantity = steps * step
    if quantity <= 0 or quantity * price < minimum:
        return _rejected("below_minimum_size")

    notional = quantity * price
    margin = notional / leverage
    loss = quantity * loss_per_unit
    if min_margin is not None and margin < min_margin:
        # Non si alza il rischio ne' si stringe lo stop: con leva piu' bassa il margine cresce (il motore riprova).
        return _rejected("below_min_margin")
    if (loss > risk_budget or margin > margin_budget or
            (loss_per_margin is not None and loss > margin * loss_per_margin)):
        return _rejected("internal_risk_invariant")
    return RiskQuote(True, "quote_only", quantity, notional, margin,
                     loss, risk_budget)
