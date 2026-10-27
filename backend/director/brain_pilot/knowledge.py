"""Curated engineering/research provenance, explicitly distinct from trade evidence.

Only documented facts in reviewed source files. No unverified causal learning,
raw user prose, credentials, collector imports or recovered signal formulas.
"""
from .learning import digest

RESEARCH_REV = "bd9b04277dda8ed6a1ab310220a9b96e6234a0ed"
BRAIN_REV = "1f2edeb6182029adc96ba7218ad145a7503472a3"
GUARDIAN_REV = "63641f7059a977368f8bb8aecc517f7a7c74cbce"


def catalog(now_ms=None):
    notes = [{'available_after_ms': 1793089982888,
      'topic': 'best_observed_run',
      'kind': 'operator_reported_case_study',
      'scope': 'Classical PAPER Run #2; owner/account scope not independently verified',
      'fact': 'Operator-supplied Claude report describes Run #2, 12-16 Oct 2026, revision5818aee: '
              '+1090USD PAPER net, 60.5% win rate,76 trades, threshold70, daily stop12%, BTC '
              'downtrend. These values and the best-run ranking have not been reconciled against trade '
              'archives.',
      'purpose': 'Compare favorable and adverse runs before inferring effects of selectivity or market '
                 'regime. Do not restore historical parameters automatically.',
      'effectiveness': 'reported_single_run_unverified_not_causal',
      'evidence': {'source': 'user_supplied_claude_patch',
                   'document': 'chatgpt-push-istruzioni.md',
                   'document_sha256': '9d150a1a669aba3ca78adf5364ab42d477f2624b53bf4690a0d945c53f1ab43f',
                   'reported_revision': '5818aee',
                   'trade_archive_imported': False}},
     {'available_after_ms': 1793089982888,
      'topic': 'btc_regime_and_altcoin_direction',
      'kind': 'research_hypothesis_not_validated',
      'scope': 'PAPER research context',
      'fact': 'Test whether the current measured BTC regime provides useful context for each asset; '
              'correlations and directional edge vary. Apply the existing profile regime controls.',
      'purpose': 'Evaluate against attributable data and costs; this note cannot override method, '
                 'sizing, risk, data or budget controls.',
      'effectiveness': 'unverified_no_statistical_effect_claimed',
      'source': 'Topics supplied by Claude via operator; no identifiable supporting study supplied.'},
     {'available_after_ms': 1793089982888,
      'topic': 'funding_rate_as_market_signal',
      'kind': 'research_hypothesis_not_validated',
      'scope': 'PAPER research context',
      'fact': 'If timestamped funding data is available, assess actual carry and positioning context. '
              'Positive funding alone does not establish a profitable short or a reversal; no '
              'universal funding threshold is validated here.',
      'purpose': 'Evaluate against attributable data and costs; this note cannot override method, '
                 'sizing, risk, data or budget controls.',
      'effectiveness': 'unverified_no_statistical_effect_claimed',
      'source': 'Topics supplied by Claude via operator; no identifiable supporting study supplied.'},
     {'available_after_ms': 1793089982888,
      'topic': 'selectivity_vs_volume_tradeoff',
      'kind': 'research_hypothesis_not_validated',
      'scope': 'PAPER research context',
      'fact': 'Compare expected net value after the configured costs, not trade count or win rate '
              'alone. Fewer trades are not automatically more profitable; retain valid scalp '
              'opportunities and measure rejected opportunities.',
      'purpose': 'Evaluate against attributable data and costs; this note cannot override method, '
                 'sizing, risk, data or budget controls.',
      'effectiveness': 'unverified_no_statistical_effect_claimed',
      'source': 'Topics supplied by Claude via operator; no identifiable supporting study supplied.'},
     {'available_after_ms': 1793089982888,
      'topic': 'position_sizing_and_risk_per_trade',
      'kind': 'research_hypothesis_not_validated',
      'scope': 'PAPER research context',
      'fact': 'Evaluate dollar loss at the stop, not leverage or margin in isolation. Use the actual '
              'selected profile limits; no new percentage-of-equity risk cap is introduced by this '
              'note.',
      'purpose': 'Evaluate against attributable data and costs; this note cannot override method, '
                 'sizing, risk, data or budget controls.',
      'effectiveness': 'unverified_no_statistical_effect_claimed',
      'source': 'Topics supplied by Claude via operator; no identifiable supporting study supplied.'},
     {'available_after_ms': 1793089982888,
      'topic': 'common_losing_patterns_in_crypto_scalping',
      'kind': 'research_hypothesis_not_validated',
      'scope': 'PAPER research context',
      'fact': 'Review chasing extended moves, stop widening, revenge trading and repeated correlated '
              'entries as potential failure modes. Preserve hard daily stops and never force recovery; '
              'outcomes require measurement.',
      'purpose': 'Evaluate against attributable data and costs; this note cannot override method, '
                 'sizing, risk, data or budget controls.',
      'effectiveness': 'unverified_no_statistical_effect_claimed',
      'source': 'Topics supplied by Claude via operator; no identifiable supporting study supplied.'},
     {'available_after_ms': 1793089982888,
      'topic': 'altcoin_btc_correlation_risk',
      'kind': 'research_hypothesis_not_validated',
      'scope': 'PAPER research context',
      'fact': 'Measure shared directional exposure and current correlations rather than assuming '
              'diversification across tickers. Correlation does not imply identical positions or that '
              'portfolio risk always exceeds the sum of individual risks.',
      'purpose': 'Evaluate against attributable data and costs; this note cannot override method, '
                 'sizing, risk, data or budget controls.',
      'effectiveness': 'unverified_no_statistical_effect_claimed',
      'source': 'Topics supplied by Claude via operator; no identifiable supporting study supplied.'},
     {'available_after_ms': 1793089982888,
      'topic': 'high_volatility_session_timing',
      'kind': 'research_hypothesis_not_validated',
      'scope': 'PAPER research context',
      'fact': 'Evaluate observed volatility, liquidity, spread and execution quality by UTC window. No '
              'universally superior session, fixed volatility timetable or time-based entry ban is '
              'established here.',
      'purpose': 'Evaluate against attributable data and costs; this note cannot override method, '
                 'sizing, risk, data or budget controls.',
      'effectiveness': 'unverified_no_statistical_effect_claimed',
      'source': 'Topics supplied by Claude via operator; no identifiable supporting study supplied.'}] + [
        {"available_after_ms":1793022958000,"topic": "counter_evidence", "kind": "documented_code_change", "scope": "Brain",
         "fact": "New exposure requires nonempty bull and bear scenarios, verdict and structured invalidation.",
         "purpose": "Make contrary evidence explicit; do not infer that directional bias or profitability is solved.",
         "effectiveness": "unverified_by_this_catalog",
         "evidence": {"repository": "alexiptv82/SuperBot-Trading", "revision": BRAIN_REV,
                      "paths": ["backend/director/brain_pilot/pilot.py", "backend/director/brain_pilot/prompt_builder.py"]}},
        {"available_after_ms":1793001132000,"topic": "profit_protection", "kind": "documented_code", "scope": "Hawk/Bull research context",
         "fact": "Profit Guardian source defines ROI/giveback review and close/partial/hold proposals; its module declares SHADOW ONLY.",
         "purpose": "Distinguish intention, code presence, runtime activation and demonstrated outcomes; none implies the others.",
         "effectiveness": "runtime_hook_and_profit_effect_not_verified_by_this_catalog",
         "evidence": {"repository": "alexiptv82/SuperBot-Trading", "revision": GUARDIAN_REV,
                      "paths": ["backend/desk/profit_guardian.py"]}},
        {"available_after_ms":1789719405000,"topic": "microstructure_research", "kind": "historical_research_not_reproduced", "scope": "Research Console BTC/ETH",
         "fact": "The 36h report rejected standalone directional alpha below its 15bps hurdle; short-horizon execution candidates remain research only.",
         "purpose": "Do not transfer millisecond/second execution effects into a 15m direction rule or size multiplier.",
         "effectiveness": "frozen_engine_not_configured_and_raw_reproduction_pending",
         "evidence": {"repository": "alexiptv82/SuperBot-Research-Console", "revision": RESEARCH_REV,
                      "paths": ["audit/cp36_x/MULTIVENUE_V2_CHECKPOINT_36H/CHECKPOINT_36H_REPORT.md",
                                "backend/frozen_engine.py", "backend/recovery/harness.py"]}},
    ]
    return [dict(n, id=digest(n)) for n in notes if now_ms is None or n["available_after_ms"] <= now_ms]
