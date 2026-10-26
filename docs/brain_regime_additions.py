# PROPOSED ADDITIONS ONLY to backend/desk/brain.py, after imports.
# Not activated: cli.py must supply closed candles and persistent per-bot instances.
from dataclasses import replace
import math

try:
    from desk.market_regime import MarketRegimeClassifier
except Exception:
    MarketRegimeClassifier = None

try:
    from desk.episode_memory import EpisodeMemory
except Exception:
    EpisodeMemory = None


# Add below rules_decisions. Create classifier/memory once PER BOT in its runner.
def prepare_entry_readings(readings, candles_by_symbol, trade_history_path,
                           classifier=None, memory=None, *, now_ms=None):
    """New copies for entries only; original readings and management stay intact.

    candles_by_symbol: {symbol: (closed_1h, closed_15m)}.
    Always feed original readings, never the previous cycle's adjusted copies.
    """
    bias = {}
    try:
        if memory is not None:
            bias = memory.get_bias(trade_history_path, hours=3)
    except Exception:
        pass

    def multiplier(result, name):
        try:
            value = float(result.get(name + "_modifier", 1.0))
            return value if math.isfinite(value) and 0 <= value <= 1 else 1.0
        except Exception:
            return 1.0

    output = []
    for original in readings:
        regime = {}
        try:
            if classifier is not None:
                h, m = candles_by_symbol[original.symbol]
                regime = classifier.classify(h, m, symbol=original.symbol, now_ms=now_ms)
        except Exception:
            pass
        try:
            lm = multiplier(regime, "long") * multiplier(bias, "long")
            sm = multiplier(regime, "short") * multiplier(bias, "short")
            if lm == sm == 1.0:
                output.append(original)
                continue
            # Floor avoids rounding a penalized score up over the entry threshold.
            long = math.floor(original.long_score * lm)
            short = math.floor(original.short_score * sm)
            side = 1 if long > short else -1 if short > long else 0
            facts = dict(original.facts)
            facts["entry_context"] = {"regime": regime.get("regime", "UNKNOWN"),
                                      "long_modifier": lm, "short_modifier": sm,
                                      "raw_long": original.long_score, "raw_short": original.short_score}
            output.append(replace(original, long_score=long, short_score=short,
                                  side=side, score=max(long, short), facts=facts,
                                  why=[f"entry context L{long}/S{short}; raw L{original.long_score}/S{original.short_score}"]))
        except Exception:
            output.append(original)
    return output


def context_rules_decisions(readings, positions, open_symbols, entry_score=70,
                            only_manage=False, *, candles_by_symbol=None,
                            trade_history_path=None, classifier=None, memory=None,
                            now_ms=None):
    # Management MUST see original scores, including Claude HOLD (P2).
    management = rules_decisions(readings, positions, open_symbols, entry_score,
                                 only_manage=True)
    if only_manage:
        return management
    entries = readings
    try:
        entries = prepare_entry_readings(readings, candles_by_symbol or {},
                                        trade_history_path, classifier, memory, now_ms=now_ms)
    except Exception:
        pass
    return management + rules_decisions(entries, [], open_symbols, entry_score)
