from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

try:
    from strategies.base import SignalDirection, StrategyDecision
except ImportError:
    from backend.strategies.base import SignalDirection, StrategyDecision


@dataclass(frozen=True)
class SelectorConfig:
    min_champion_samples: float = 20.0
    min_challenger_samples: float = 12.0
    promotion_margin: float = 0.08
    decay: float = 0.985
    min_actionable_strength: float = 55.0
    expectancy_scale_bps: float = 30.0
    fallback_signal_weight: float = 0.35
    learned_performance_weight: float = 0.65

    def validate(self) -> None:
        if not 0.0 < self.decay <= 1.0:
            raise ValueError("decay must be in (0,1]")
        if self.min_champion_samples < 1:
            raise ValueError("min_champion_samples must be >= 1")
        if self.min_challenger_samples < 1:
            raise ValueError("min_challenger_samples must be >= 1")
        if self.promotion_margin < 0:
            raise ValueError("promotion_margin must be >= 0")
        if not 0 <= self.min_actionable_strength <= 100:
            raise ValueError("min_actionable_strength must be in [0,100]")
        if self.expectancy_scale_bps <= 0:
            raise ValueError("expectancy_scale_bps must be > 0")
        if not math.isclose(self.fallback_signal_weight + self.learned_performance_weight,
                            1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError("fallback_signal_weight + learned_performance_weight must equal 1")


@dataclass
class PerformanceBucket:
    effective_samples: float = 0.0
    weighted_pnl_bps: float = 0.0
    weighted_wins: float = 0.0
    weighted_losses: float = 0.0
    gross_profit_bps: float = 0.0
    gross_loss_bps: float = 0.0
    last_updated_at: str | None = None

    def decay_by(self, factor: float) -> None:
        self.effective_samples *= factor
        self.weighted_pnl_bps *= factor
        self.weighted_wins *= factor
        self.weighted_losses *= factor
        self.gross_profit_bps *= factor
        self.gross_loss_bps *= factor

    def add(self, pnl_bps: float, decay: float) -> None:
        self.decay_by(decay)
        pnl_bps = float(pnl_bps)
        self.effective_samples += 1.0
        self.weighted_pnl_bps += pnl_bps
        if pnl_bps > 0:
            self.weighted_wins += 1.0
            self.gross_profit_bps += pnl_bps
        elif pnl_bps < 0:
            self.weighted_losses += 1.0
            self.gross_loss_bps += abs(pnl_bps)
        self.last_updated_at = datetime.now(timezone.utc).isoformat()

    @property
    def expectancy_bps(self) -> float:
        if self.effective_samples <= 0:
            return 0.0
        return self.weighted_pnl_bps / self.effective_samples

    @property
    def win_rate(self) -> float:
        labeled = self.weighted_wins + self.weighted_losses
        if labeled <= 0:
            return 0.5
        return self.weighted_wins / labeled

    @property
    def profit_factor(self) -> float:
        if self.gross_loss_bps <= 1e-12:
            return 3.0 if self.gross_profit_bps > 0 else 1.0
        return self.gross_profit_bps / self.gross_loss_bps

    def to_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.update(expectancy_bps=self.expectancy_bps, win_rate=self.win_rate, profit_factor=self.profit_factor)
        return out


@dataclass(frozen=True)
class SelectionResult:
    selected: StrategyDecision | None
    champion_strategy_id: str | None
    selected_strategy_id: str | None
    selected_role: str
    regime: str
    rankings: tuple[dict[str, Any], ...]
    promotion: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected": self.selected.to_dict() if self.selected else None,
            "champion_strategy_id": self.champion_strategy_id,
            "selected_strategy_id": self.selected_strategy_id,
            "selected_role": self.selected_role,
            "regime": self.regime,
            "rankings": [dict(r) for r in self.rankings],
            "promotion": dict(self.promotion) if self.promotion else None,
        }


class StrategySelector:
    GLOBAL_REGIME = "__GLOBAL__"

    def __init__(self, strategy_ids: Iterable[str], config: SelectorConfig | None = None):
        self.config = config or SelectorConfig()
        self.config.validate()
        ids = [str(s).strip() for s in strategy_ids if str(s).strip()]
        if len(ids) != len(set(ids)):
            raise ValueError("strategy_ids must be unique")
        if not ids:
            raise ValueError("at least one strategy_id is required")
        self.strategy_ids = tuple(ids)
        self._stats: dict[tuple[str, str], PerformanceBucket] = {}
        self._champions: dict[str, str] = {}

    @staticmethod
    def _normalize_regime(regime: str | None) -> str:
        value = str(regime or "unknown").strip().upper()
        return value or "UNKNOWN"

    def _bucket(self, strategy_id: str, regime: str) -> PerformanceBucket:
        key = (strategy_id, regime)
        if key not in self._stats:
            self._stats[key] = PerformanceBucket()
        return self._stats[key]

    def record_result(self, *, strategy_id: str, pnl_bps: float, regime: str | None = None) -> None:
        strategy_id = str(strategy_id).strip()
        if strategy_id not in self.strategy_ids:
            raise KeyError(f"unknown strategy_id: {strategy_id}")
        regime_key = self._normalize_regime(regime)
        self._bucket(strategy_id, self.GLOBAL_REGIME).add(pnl_bps, self.config.decay)
        if regime_key != self.GLOBAL_REGIME:
            self._bucket(strategy_id, regime_key).add(pnl_bps, self.config.decay)

    def _blended_metrics(self, strategy_id: str, regime: str) -> dict[str, float]:
        global_b = self._bucket(strategy_id, self.GLOBAL_REGIME)
        regime_b = self._bucket(strategy_id, regime)
        regime_weight = min(1.0, regime_b.effective_samples / max(1.0, self.config.min_challenger_samples))
        global_weight = 1.0 - regime_weight
        return {
            "effective_samples": regime_b.effective_samples * regime_weight + global_b.effective_samples * global_weight,
            "expectancy_bps": regime_b.expectancy_bps * regime_weight + global_b.expectancy_bps * global_weight,
            "win_rate": regime_b.win_rate * regime_weight + global_b.win_rate * global_weight,
            "profit_factor": min(regime_b.profit_factor, 3.0) * regime_weight + min(global_b.profit_factor, 3.0) * global_weight,
            "regime_weight": regime_weight,
        }

    def _performance_quality(self, strategy_id: str, regime: str) -> tuple[float, dict[str, float]]:
        metrics = self._blended_metrics(strategy_id, regime)
        expectancy_score = math.tanh(metrics["expectancy_bps"] / self.config.expectancy_scale_bps)
        win_score = (metrics["win_rate"] - 0.5) * 2.0
        pf_score = math.tanh((metrics["profit_factor"] - 1.0) / 1.25)
        raw_quality = 0.55 * expectancy_score + 0.25 * win_score + 0.20 * pf_score
        sample_confidence = 1.0 - math.exp(-metrics["effective_samples"] / max(1.0, self.config.min_challenger_samples))
        quality = raw_quality * sample_confidence
        metrics["sample_confidence"] = sample_confidence
        metrics["performance_quality"] = quality
        return quality, metrics

    @staticmethod
    def _signal_quality(decision: StrategyDecision) -> float:
        d = decision.normalized()
        if d.direction == SignalDirection.HOLD:
            return -1.0
        return 0.60 * d.confidence + 0.40 * (d.strength / 100.0)

    def leaderboard(self, regime: str | None = None) -> list[dict[str, Any]]:
        regime_key = self._normalize_regime(regime)
        champion = self._champions.get(regime_key)
        rows = []
        for sid in self.strategy_ids:
            quality, metrics = self._performance_quality(sid, regime_key)
            rows.append({"strategy_id": sid, "role": "CHAMPION" if sid == champion else "CHALLENGER",
                         "performance_quality": quality, **metrics})
        rows.sort(key=lambda r: (r["performance_quality"], r["expectancy_bps"], r["effective_samples"]), reverse=True)
        return rows

    def _maybe_promote(self, regime: str) -> dict[str, Any] | None:
        board = self.leaderboard(regime)
        if not board:
            return None
        current = self._champions.get(regime)
        if current is None:
            eligible = [r for r in board if r["effective_samples"] >= self.config.min_champion_samples]
            if not eligible:
                return None
            winner = eligible[0]
            self._champions[regime] = winner["strategy_id"]
            return {"type": "INITIAL_CHAMPION", "to": winner["strategy_id"], "regime": regime, "quality": winner["performance_quality"]}
        champion_row = next(r for r in board if r["strategy_id"] == current)
        challengers = [r for r in board if r["strategy_id"] != current and r["effective_samples"] >= self.config.min_challenger_samples]
        if not challengers:
            return None
        best = challengers[0]
        if best["performance_quality"] >= champion_row["performance_quality"] + self.config.promotion_margin:
            self._champions[regime] = best["strategy_id"]
            return {"type": "CHALLENGER_PROMOTED", "from": current, "to": best["strategy_id"],
                    "regime": regime, "quality_delta": best["performance_quality"] - champion_row["performance_quality"]}
        return None

    def select(self, decisions: Iterable[StrategyDecision], *, regime: str | None = None) -> SelectionResult:
        regime_key = self._normalize_regime(regime)
        promotion = self._maybe_promote(regime_key)
        champion = self._champions.get(regime_key)
        normalized: dict[str, StrategyDecision] = {}
        for decision in decisions:
            d = decision.normalized()
            if d.strategy_id in self.strategy_ids:
                normalized[d.strategy_id] = d
        rankings = []
        for sid in self.strategy_ids:
            decision = normalized.get(sid)
            quality, metrics = self._performance_quality(sid, regime_key)
            if decision is None or decision.direction == SignalDirection.HOLD or decision.strength < self.config.min_actionable_strength:
                actionable = False; signal_quality = -1.0; selection_score = -999.0
            else:
                actionable = True
                signal_quality = self._signal_quality(decision)
                selection_score = self.config.learned_performance_weight * quality + self.config.fallback_signal_weight * signal_quality
            rankings.append({"strategy_id": sid, "role": "CHAMPION" if sid == champion else "CHALLENGER",
                             "actionable": actionable, "direction": decision.direction.value if decision else None,
                             "strength": decision.strength if decision else 0.0, "confidence": decision.confidence if decision else 0.0,
                             "signal_quality": signal_quality, "selection_score": selection_score, **metrics})
        rankings.sort(key=lambda r: (r["selection_score"], r["performance_quality"], r["strength"]), reverse=True)
        selected_row = None; selected_role = "NONE"
        if champion is not None:
            champion_row = next((r for r in rankings if r["strategy_id"] == champion), None)
            if champion_row and champion_row["actionable"]:
                selected_row = champion_row; selected_role = "CHAMPION"
        if selected_row is None:
            selected_row = next((r for r in rankings if r["actionable"]), None)
            if selected_row is not None:
                selected_role = "CHAMPION" if selected_row["strategy_id"] == champion else "CHALLENGER_FALLBACK"
        selected = normalized[selected_row["strategy_id"]] if selected_row is not None else None
        return SelectionResult(selected=selected, champion_strategy_id=champion,
                               selected_strategy_id=selected.strategy_id if selected else None,
                               selected_role=selected_role, regime=regime_key,
                               rankings=tuple(rankings), promotion=promotion)

    def export_state(self) -> dict[str, Any]:
        return {"version": 1, "strategy_ids": list(self.strategy_ids), "champions": dict(self._champions),
                "stats": [{"strategy_id": sid, "regime": r, **b.to_dict()} for (sid, r), b in sorted(self._stats.items())]}

    def load_state(self, state: Mapping[str, Any]) -> None:
        if int(state.get("version", 0)) != 1:
            raise ValueError("unsupported selector state version")
        incoming_ids = tuple(state.get("strategy_ids") or ())
        if incoming_ids and incoming_ids != self.strategy_ids:
            raise ValueError("selector state strategy_ids do not match configured strategies")
        self._champions = {str(r): str(sid) for r, sid in dict(state.get("champions") or {}).items() if str(sid) in self.strategy_ids}
        self._stats.clear()
        for row in state.get("stats") or []:
            sid = str(row["strategy_id"]); regime = str(row["regime"])
            if sid not in self.strategy_ids:
                continue
            self._stats[(sid, regime)] = PerformanceBucket(
                effective_samples=float(row.get("effective_samples", 0.0)),
                weighted_pnl_bps=float(row.get("weighted_pnl_bps", 0.0)),
                weighted_wins=float(row.get("weighted_wins", 0.0)),
                weighted_losses=float(row.get("weighted_losses", 0.0)),
                gross_profit_bps=float(row.get("gross_profit_bps", 0.0)),
                gross_loss_bps=float(row.get("gross_loss_bps", 0.0)),
                last_updated_at=row.get("last_updated_at"))
