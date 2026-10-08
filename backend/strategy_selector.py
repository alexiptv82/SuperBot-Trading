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
    # Gate di significatività statistica sulle PROMOZIONI (non sulla
    # selezione per-ciclo): un punteggio più alto non basta per diventare
    # champion se l'expectancy osservata non è significativa rispetto al
    # suo errore standard -- vedi PerformanceBucket.significance_t_stat.
    # 1.0 è una soglia permissiva (corrisponde grossomodo a un intervallo
    # di confidenza dell'~68% su una normale); va vista come un filtro
    # contro il rumore più evidente, non come un test rigoroso.
    min_significance_t_stat: float = 1.0
    # Abstention su disaccordo (trovato Qwen): se tra le decisioni
    # actionable di questo ciclo compaiono sia un LONG che uno SHORT con
    # selection_score molto vicini, non ha senso "vincere ai punti" per
    # una manciata di centesimi -- e' un segnale che le strategie non sono
    # davvero d'accordo sulla direzione, quindi il selettore si astiene
    # (nessuna selezione) invece di scegliere quello marginalmente più alto.
    # 0.10 e' empirico: selection_score e' in [-1, 1] circa, quindi 0.10 e'
    # un margine piccolo ma non infinitesimo.
    abstention_margin: float = 0.10

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
        if self.min_significance_t_stat < 0:
            raise ValueError("min_significance_t_stat must be >= 0")
        if self.abstention_margin < 0:
            raise ValueError("abstention_margin must be >= 0")


@dataclass
class PerformanceBucket:
    effective_samples: float = 0.0
    weighted_pnl_bps: float = 0.0
    weighted_wins: float = 0.0
    weighted_losses: float = 0.0
    gross_profit_bps: float = 0.0
    gross_loss_bps: float = 0.0
    # Somma pesata/decaduta dei pnl^2 -- serve SOLO per calcolare la vera
    # varianza empirica (Var = E[X^2] - E[X]^2) usata dal gate di
    # significatività statistica. Senza questo, l'unica alternativa sarebbe
    # stimare la varianza da vincita/perdita media, che collassa a zero in
    # casi degeneri (es. tutte vincite, ma di importo molto diverso tra
    # loro) e sottostima il rumore reale.
    weighted_pnl_sq_bps: float = 0.0
    # Conteggio di tutti i trade mai registrati in questo bucket, SENZA
    # decadimento -- a differenza di effective_samples, che decade a ogni
    # add() e quindi (con decay=0.985) si stabilizza asintoticamente
    # intorno a 1/(1-decay)=~66.7 campioni e non supera MAI una soglia più
    # alta. Serve come gate per il Kelly frazionale (vedi kelly_fraction),
    # che richiede una storia lunga davvero accumulata, non solo "recente".
    lifetime_samples: float = 0.0
    last_updated_at: str | None = None

    def decay_by(self, factor: float) -> None:
        self.effective_samples *= factor
        self.weighted_pnl_bps *= factor
        self.weighted_pnl_sq_bps *= factor
        self.weighted_wins *= factor
        self.weighted_losses *= factor
        self.gross_profit_bps *= factor
        self.gross_loss_bps *= factor

    def add(self, pnl_bps: float, decay: float) -> None:
        self.decay_by(decay)
        pnl_bps = float(pnl_bps)
        self.effective_samples += 1.0
        self.lifetime_samples += 1.0
        self.weighted_pnl_bps += pnl_bps
        self.weighted_pnl_sq_bps += pnl_bps * pnl_bps
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

    @property
    def pnl_variance_estimate(self) -> float:
        """Varianza empirica del pnl per trade: Var = E[X^2] - E[X]^2, dalla
        somma pesata/decaduta dei pnl^2 (weighted_pnl_sq_bps) e dalla media
        (expectancy_bps). Il clamp a 0 serve solo per i rari errori di
        arrotondamento in virgola mobile quando la varianza vera è
        prossima a zero."""
        if self.effective_samples <= 0:
            return 0.0
        mean = self.expectancy_bps
        mean_sq = self.weighted_pnl_sq_bps / self.effective_samples
        return max(0.0, mean_sq - mean * mean)

    @property
    def standard_error_bps(self) -> float:
        if self.effective_samples <= 1:
            return math.inf
        return math.sqrt(self.pnl_variance_estimate / self.effective_samples)

    @property
    def significance_t_stat(self) -> float:
        """t-stat approssimato: expectancy / errore standard. Un valore
        basso significa che l'expectancy osservata potrebbe benissimo
        essere rumore statistico, anche se e' la più alta tra le strategie
        candidate -- questo è esattamente il punto del gate di
        significatività (da Qwen): un punteggio più alto non basta, deve
        anche essere significativo rispetto alla sua incertezza."""
        se = self.standard_error_bps
        if not math.isfinite(se) or se <= 1e-9:
            return 0.0
        return self.expectancy_bps / se

    def is_statistically_significant(self, min_t_stat: float = 1.0) -> bool:
        return abs(self.significance_t_stat) >= min_t_stat

    # Kelly frazionale: parametri di sicurezza condivisi da tutti i bucket.
    KELLY_MIN_LIFETIME_SAMPLES = 200.0
    KELLY_FRACTION = 0.25          # 1/4 Kelly -- il pieno Kelly è troppo
                                    # aggressivo per stime di probabilità
                                    # rumorose (anche a 200 campioni).
    KELLY_MAX_STAKE_FRACTION = 0.05  # tetto di sicurezza assoluto: mai
                                      # oltre il 5% del capitale, qualunque
                                      # cosa dica la formula.

    def kelly_fraction(self) -> dict[str, Any]:
        """Frazione di capitale suggerita da un Kelly frazionale (1/4 Kelly),
        SOLO quando il bucket ha accumulato almeno KELLY_MIN_LIFETIME_SAMPLES
        trade (gate su lifetime_samples, che non decade mai -- vedi sopra).

        Puramente informativo in questa fase: il motore V0.5 gira in shadow
        mode, quindi questo numero viene solo calcolato e loggato per
        confronto, non usato per il sizing reale di nessun trade (che resta
        su risk_manager.py, V1/main, a rischio fisso).

        Ritorna sempre un dict con 'eligible': bool. Se eligible è True,
        contiene anche 'kelly_full' (frazione di Kelly piena, può essere
        negativa se l'edge è negativo) e 'kelly_fractional' (frazione
        frazionale già tagliata a KELLY_FRACTION e col tetto di sicurezza
        applicato, mai negativa).
        """
        if self.lifetime_samples < self.KELLY_MIN_LIFETIME_SAMPLES:
            return {"eligible": False,
                    "reason": f"solo {self.lifetime_samples:.0f}/{self.KELLY_MIN_LIFETIME_SAMPLES:.0f} trade lifetime"}

        wins, losses = self.weighted_wins, self.weighted_losses
        if wins <= 1e-9 or losses <= 1e-9 or self.gross_loss_bps <= 1e-9:
            return {"eligible": False,
                    "reason": "servono sia vincite che perdite per stimare il payoff ratio"}

        p = self.win_rate
        q = 1.0 - p
        avg_win = self.gross_profit_bps / wins
        avg_loss = self.gross_loss_bps / losses
        if avg_loss <= 1e-9:
            return {"eligible": False, "reason": "perdita media nulla, payoff ratio non calcolabile"}
        payoff_ratio = avg_win / avg_loss

        kelly_full = p - (q / payoff_ratio)
        kelly_fractional = max(0.0, min(kelly_full * self.KELLY_FRACTION, self.KELLY_MAX_STAKE_FRACTION))
        return {
            "eligible": True,
            "kelly_full": round(kelly_full, 4),
            "kelly_fractional": round(kelly_fractional, 4),
            "payoff_ratio": round(payoff_ratio, 3),
            "win_rate": round(p, 3),
            "lifetime_samples": round(self.lifetime_samples, 0),
        }


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

    @staticmethod
    def make_context_key(symbol: str, regime: str | None) -> str:
        """Combina simbolo e regime in un'unica chiave di bucket, cosi' le
        statistiche di performance (e quindi anche la selezione del
        champion/challenger) restano separate per simbolo oltre che per
        regime, invece di mescolare BTC/ETH (cripto) con XAU/XAG (metalli)
        nello stesso bucket solo perche' si trovano nello stesso regime di
        mercato -- vedi roadmap Fase 2.

        Il bucket GLOBAL (per sola strategy_id, vedi record_result) resta
        invece condiviso tra tutti i simboli: e' il fallback di warm-start
        per una combinazione (simbolo, regime) ancora senza campioni.

        Esempio: ('BTCUSDT', 'TREND_BULL') -> 'BTCUSDT::TREND_BULL'.
        """
        sym = str(symbol or "UNKNOWN").strip().upper()
        reg = str(regime or "unknown").strip().upper() or "UNKNOWN"
        return f"{sym}::{reg}"

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

    def kelly_suggestion(self, strategy_id: str, regime: str | None = None) -> dict[str, Any]:
        """Suggerimento di sizing Kelly frazionale per (strategy_id, regime)
        -- regime qui è già la chiave di bucket (es. l'output di
        make_context_key se si vuole il Kelly per uno specifico simbolo).
        Vedi PerformanceBucket.kelly_fraction per i dettagli e le soglie."""
        regime_key = self._normalize_regime(regime)
        return self._bucket(strategy_id, regime_key).kelly_fraction()

    def leaderboard(self, regime: str | None = None) -> list[dict[str, Any]]:
        regime_key = self._normalize_regime(regime)
        champion = self._champions.get(regime_key)
        rows = []
        for sid in self.strategy_ids:
            quality, metrics = self._performance_quality(sid, regime_key)
            # t-stat sul bucket SPECIFICO del regime (non quello blended con
            # il global usato per le altre metriche): la domanda del gate di
            # significatività è "questo expectancy, misurato in QUESTO
            # regime, è distinguibile dal rumore?", non una media pesata.
            t_stat = self._bucket(sid, regime_key).significance_t_stat
            rows.append({"strategy_id": sid, "role": "CHAMPION" if sid == champion else "CHALLENGER",
                         "performance_quality": quality, "significance_t_stat": t_stat, **metrics})
        rows.sort(key=lambda r: (r["performance_quality"], r["expectancy_bps"], r["effective_samples"]), reverse=True)
        return rows

    def _is_significant(self, row: dict[str, Any]) -> bool:
        return abs(row["significance_t_stat"]) >= self.config.min_significance_t_stat

    def _maybe_promote(self, regime: str) -> dict[str, Any] | None:
        board = self.leaderboard(regime)
        if not board:
            return None
        current = self._champions.get(regime)
        if current is None:
            eligible = [r for r in board
                        if r["effective_samples"] >= self.config.min_champion_samples and self._is_significant(r)]
            if not eligible:
                return None
            winner = eligible[0]
            self._champions[regime] = winner["strategy_id"]
            return {"type": "INITIAL_CHAMPION", "to": winner["strategy_id"], "regime": regime,
                    "quality": winner["performance_quality"], "t_stat": winner["significance_t_stat"]}
        champion_row = next(r for r in board if r["strategy_id"] == current)
        challengers = [r for r in board
                       if r["strategy_id"] != current and r["effective_samples"] >= self.config.min_challenger_samples
                       and self._is_significant(r)]
        if not challengers:
            return None
        best = challengers[0]
        if best["performance_quality"] >= champion_row["performance_quality"] + self.config.promotion_margin:
            self._champions[regime] = best["strategy_id"]
            return {"type": "CHALLENGER_PROMOTED", "from": current, "to": best["strategy_id"],
                    "regime": regime, "quality_delta": best["performance_quality"] - champion_row["performance_quality"],
                    "t_stat": best["significance_t_stat"]}
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

        # Abstention su disaccordo (trovato Qwen): se le migliori decisioni
        # actionable LONG e SHORT di questo ciclo sono quasi appaiate per
        # punteggio, le strategie non sono davvero d'accordo sulla
        # direzione -- meglio non scegliere nessuno che forzare una
        # selezione sul margine di un pelo. Controllato PRIMA della logica
        # normale di champion/challenger: un disaccordo forte scavalca
        # anche un champion attuale.
        actionable = [r for r in rankings if r["actionable"]]
        longs = [r for r in actionable if r["direction"] == SignalDirection.LONG.value]
        shorts = [r for r in actionable if r["direction"] == SignalDirection.SHORT.value]
        abstained = False
        if longs and shorts:
            best_long = max(longs, key=lambda r: r["selection_score"])
            best_short = max(shorts, key=lambda r: r["selection_score"])
            if abs(best_long["selection_score"] - best_short["selection_score"]) <= self.config.abstention_margin:
                abstained = True
                selected_role = "ABSTAINED_DISAGREEMENT"

        if abstained:
            selected = None
            return SelectionResult(selected=selected, champion_strategy_id=champion,
                                   selected_strategy_id=None, selected_role=selected_role,
                                   regime=regime_key, rankings=tuple(rankings), promotion=promotion)

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
                # Assente nei checkpoint precedenti al gate di significatività:
                # 0.0 fa partire la varianza stimata da zero, quindi il gate
                # resta prudente (t_stat=0, nessuna promozione) finché non si
                # riaccumula storia reale -- degradazione sicura, non un crash.
                weighted_pnl_sq_bps=float(row.get("weighted_pnl_sq_bps", 0.0)),
                weighted_wins=float(row.get("weighted_wins", 0.0)),
                weighted_losses=float(row.get("weighted_losses", 0.0)),
                gross_profit_bps=float(row.get("gross_profit_bps", 0.0)),
                gross_loss_bps=float(row.get("gross_loss_bps", 0.0)),
                # Un checkpoint precedente all'introduzione di lifetime_samples
                # non ha questo campo: effective_samples è una stima per
                # difetto accettabile (il decadimento lo tiene sempre <= al
                # vero conteggio lifetime), quindi il gate Kelly resta
                # prudente anche sui checkpoint vecchi.
                lifetime_samples=float(row.get("lifetime_samples", row.get("effective_samples", 0.0))),
                last_updated_at=row.get("last_updated_at"))
