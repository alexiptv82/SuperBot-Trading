"""Biblioteca strategica per il Brain (F7, passo L0): caricatore rigido, classificazione dei dati, registro delle prove.

Che cosa e' e che cosa NON e'
-----------------------------
Le 24 schede di ``strategy_kb.json`` sono *ipotesi di ricerca* raccolte da fonti esterne
(video, documentazione, paper): tutte ``research_only``, nessuna provata redditizia, nessuna
validata su Bitget. Questo modulo le carica, le valida in modo rigido e dice per ciascuna
quali dati servono per provarla; non sceglie strategie, non tocca il Brain, il journal, i
prompt, le soglie o i limiti di rischio (collegarla al Brain e' un passo successivo che
richiede l'OK esplicito dell'utente). Il testo libero delle schede e' DATO, mai istruzione:
chi lo usera' dentro un prompt dovra' passare solo identificatori e campi controllati.

Regole esatte (contratto verificato dai test)
---------------------------------------------
* Modulo senza rete, orologio, casualita' o subprocess; legge SOLO il proprio file
  impacchettato ``strategy_kb.json``, fissato con SHA-256 (``KB_SHA256``) e mai scaricato.
  Il file va aggiornato insieme alla costante: un hash diverso e' ``kb_hash_mismatch``.
* ``parse_library(dati)`` valida una struttura gia' letta; ``load_library_bytes(raw,
  expected_sha256=...)`` controlla l'hash PRIMA di leggere il JSON (UTF-8 senza BOM, nessuna
  chiave duplicata, nessun NaN/Infinity); ``load_library()`` usa il file e la costante del modulo.
* Insiemi di chiavi ESATTI (niente chiavi mancanti o in piu'), tipi esatti (``bool`` non e'
  ``int``), elenchi chiusi per famiglia, stile, regimi, timeframe, origine, priorita', tipo
  e grado delle fonti. Gli id sono ``S[0-9][0-9]`` (schede) e ``[VGDP][0-9][0-9]`` (fonti), unici.
  Il testo libero e' stampabile, senza spazi ai bordi, con lunghezza limitata e senza
  backtick, graffe, URL o tag HTML (``<`` e ``>`` come confronti nelle soglie sono ammessi).
  ``ALL`` e' un regime a se': non si combina con altri.
* Nessuna scheda puo' dichiarare ``proven_profitable`` o ``validated_on_bitget`` veri, ne' uno
  stato diverso da ``research_only`` (``claim_not_allowed``); ``hypothesis_only`` deve valere
  vero se e solo se ``rule_origin`` non e' ``reproduced_source_rule`` (``inconsistent_origin``).
* Ogni feature richiesta deve essere classificata in modo esplicito (candele, storico
  pubblico, modellata, non disponibile): una feature nuova e' ``unclassified_feature`` finche'
  qualcuno non decide a mano dove va.
* Codici ``ValueError`` (il messaggio e' il codice), per FASE e poi per ordine nel file:
  ``invalid_library``, ``invalid_source``, ``duplicate_source_id``, ``invalid_strategy``,
  ``duplicate_strategy_id``, ``claim_not_allowed``, ``inconsistent_origin``,
  ``unclassified_feature``, ``unknown_source_ref``. Caricamento: ``invalid_input``,
  ``kb_hash_mismatch``, ``invalid_json``. Registro prove: ``invalid_evidence``,
  ``duplicate_evidence_id``, ``evidence_unknown_strategy``.
* Tutto cio' che esce e' immutabile (dataclass congelate, tuple) e deterministico.

Classificazione dei dati (``testable_now``)
-------------------------------------------
``candles``: solo feature derivabili dalle candele OHLCV (``spread`` e ``fees`` sono
*modellati* come costo, non misurati). ``candles_funding_oi``: in piu' funding e open
interest dallo storico pubblico. ``needs_new_data``: serve almeno una feature che oggi non
raccogliamo (order book L2, trade con lato aggressore, liquidazioni, spot/altre venue,
profilo di volume a tick, metriche interne): prima va raccolta in avanti. La classe riguarda
le FEATURE, non la profondita' storica per timeframe (1m/5m su sette anni vanno verificati).

Registro delle prove
--------------------
``EVIDENCE`` contiene i risultati del laboratorio del 9 ottobre 2026 (CI 37916437081, BTC+ETH
15m BitGet 2019-10-01..2026-10-08, costi A = 16 bp round trip) come prove ``analog``: regole
*vicine* a una scheda ma NON la scheda (le differenze sono scritte in ogni voce, compreso il
timeframe fuori scheda). Periodi: ``dev`` 2020-2023, ``val`` 2024-01..2025-06, ``test``
2025-07..2026-08-09. Numeri copiati dal documento del laboratorio; dove il documento non li
riporta il campo e' ``None``. Nessuna variante del laboratorio ha superato le soglie STRICT/COND.
Una prova ``analog`` non cambia lo stato di una scheda: resta ``research_only``.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

KB_FILENAME = "strategy_kb.json"
KB_SHA256 = "0b2900d3a545f25ad242d48c1de04c844b22643fcaae3f0243e5a06061e85c1b"

# ---------------------------------------------------------------- vocabolari chiusi
FAMILIES = frozenset({
    "basis_arbitrage", "breakout", "factor", "funding_arbitrage", "grid", "liquidations",
    "liquidity", "market_making", "mean_reversion", "meta", "order_flow", "positioning",
    "trend", "volatility", "volume_profile", "vwap",
})
HOLDING_STYLES = frozenset({
    "decision_system", "intraday", "market_neutral", "microstructure", "scalp",
    "signal_filter", "swing",
})
REGIMES = frozenset({
    "ALL", "EXPANSION", "RANGE", "REVERSAL_CANDIDATE", "SHOCK", "TREND_DOWN", "TREND_UP",
})
TIMEFRAMES = frozenset({"tick", "1m", "5m", "15m", "1h", "4h", "1d"})
RULE_ORIGINS = frozenset({"hypothesis", "reproduced_source_rule", "source_concept_adapted"})
PRIORITIES = frozenset({"high", "medium", "low"})
STATUS_RESEARCH_ONLY = "research_only"
SOURCE_TYPES = frozenset({"documentation", "github", "paper", "youtube"})
SOURCE_GRADES = frozenset({"A", "B", "C", "D"})
METADATA_STATUS = "research_only_no_live"

# ---------------------------------------------------------------- classi di dati
CANDLE_FEATURES = frozenset({
    "adx", "atr", "atr_percentile", "bollinger_bandwidth", "bollinger_percent_b",
    "donchian_high", "donchian_low", "ema20", "ema21", "ema50", "ema9", "macd", "macd_hist",
    "ohlcv", "returns", "rsi", "session_range", "supertrend", "swing_levels", "utc_anchor",
    "volatility", "volume", "vwap_session",
})
HISTORY_FEATURES = frozenset({"funding_rate", "open_interest"})
MODELLED_FEATURES = frozenset({"fees", "spread"})
UNAVAILABLE_FEATURES = frozenset({
    "aggressor_trades", "borrow_cost", "cvd", "depth", "execution_latency", "fills",
    "funding_rate_by_venue", "futures_basis", "inventory", "l2_orderbook", "latency",
    "liquidation_feed", "liquidity", "margin_by_venue", "mark_price", "market_data_health",
    "perp_mid", "perp_mid_by_venue", "regime_probabilities", "spot_mid",
    "strategy_oos_metrics", "trades", "trades_or_tick_volume", "volume_profile",
})
KNOWN_FEATURES = CANDLE_FEATURES | HISTORY_FEATURES | MODELLED_FEATURES | UNAVAILABLE_FEATURES
_AVAILABLE_FEATURES = CANDLE_FEATURES | HISTORY_FEATURES | MODELLED_FEATURES

FEATURE_CAVEATS = {
    "fees": "parametro del modello di costo (scenari 1x/2x/3x), non un dato di mercato",
    "funding_rate": "storico pubblico a intervalli di funding; il costo reale dipende da lato e momento",
    "open_interest": "storico pubblico solo da 5m in su; copertura per simbolo da verificare",
    "spread": "storico non disponibile: va modellato come costo o slippage",
    "volume": "volume delle candele: non separa acquisti e vendite aggressivi",
    "vwap_session": "approssimato dalle candele (prezzo tipico per volume), non dai trade",
}

DATA_CANDLES = "candles"
DATA_CANDLES_FUNDING_OI = "candles_funding_oi"
DATA_NEEDS_NEW = "needs_new_data"

# ---------------------------------------------------------------- limiti di forma
_SID_RE = re.compile(r"S[0-9]{2}")
_SRC_RE = re.compile(r"[VGDP][0-9]{2}")
_FEATURE_RE = re.compile(r"[a-z][a-z0-9_]{0,39}")
_VERSION_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_DATE_RE = re.compile(r"([0-9]{4})-([0-9]{2})(?:-([0-9]{2}))?")
_URL_RE = re.compile(
    r"https://[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?::[0-9]{1,5})?"
    r"(?:/[A-Za-z0-9._~:/?#\[\]@!$&()*+,;=%-]*)?"
)
_BAD_TEXT = re.compile(r"[`{}]|https?://|www\.|<[A-Za-z/!?]", re.IGNORECASE)
_EVIDENCE_ID_RE = re.compile(r"E[0-9]{2}")
_RUN_ID_RE = re.compile(r"[0-9]{1,20}")

CAP_NAME = 80
CAP_RULE_TEXT = 400
CAP_SRC_TITLE = 200
CAP_SRC_PUBLISHER = 80
CAP_SRC_ASSESSMENT = 300
CAP_URL = 300
MAX_ITEMS = 200

_STRATEGY_KEYS = frozenset({
    "id", "name", "family", "holding_style", "candidate_regimes", "timeframes",
    "required_features", "entry_hypothesis", "exit_hypothesis", "invalidate_when",
    "known_failure_modes", "sources", "rule_origin", "limitations", "research_priority",
    "proven_profitable", "validated_on_bitget", "status", "hypothesis_only",
})
_SOURCE_KEYS = frozenset({
    "id", "type", "publisher", "title", "url", "published_or_checked", "assessment",
    "source_grade",
})
_TOP_KEYS = frozenset({"metadata", "sources", "strategies"})


# ---------------------------------------------------------------- tipi
@dataclass(frozen=True)
class Source:
    id: str
    type: str
    publisher: str
    title: str
    url: str
    published_or_checked: str
    assessment: str
    source_grade: str


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    family: str
    holding_style: str
    candidate_regimes: tuple[str, ...]
    timeframes: tuple[str, ...]
    required_features: tuple[str, ...]
    entry_hypothesis: str
    exit_hypothesis: str
    invalidate_when: str
    known_failure_modes: str
    sources: tuple[str, ...]
    rule_origin: str
    limitations: str
    research_priority: str
    proven_profitable: bool
    validated_on_bitget: bool
    status: str
    hypothesis_only: bool


@dataclass(frozen=True)
class Library:
    version: str
    date: str
    sources: tuple[Source, ...]
    strategies: tuple[Strategy, ...]

    def strategy(self, strategy_id: str) -> Strategy:
        for s in self.strategies:
            if s.id == strategy_id:
                return s
        raise ValueError("unknown_strategy")


# ---------------------------------------------------------------- validazione
def _fail(code: str):
    raise ValueError(code)


def _is_text(v: object, cap: int) -> bool:
    return (
        type(v) is str
        and 1 <= len(v) <= cap
        and v == v.strip()
        and v.isprintable()
        and _BAD_TEXT.search(v) is None
    )


def _in(v: object, allowed: frozenset) -> bool:
    return type(v) is str and v in allowed


def _matches(v: object, pattern: re.Pattern) -> bool:
    return type(v) is str and pattern.fullmatch(v) is not None


def _str_list(v: object, lo: int, hi: int, *, pattern=None, allowed=None):
    """Tupla di stringhe uniche, o ``None`` se la lista non rispetta la forma."""
    if type(v) is not list or not lo <= len(v) <= hi:
        return None
    for x in v:
        if type(x) is not str:
            return None
        if pattern is not None and pattern.fullmatch(x) is None:
            return None
        if allowed is not None and x not in allowed:
            return None
    if len(set(v)) != len(v):
        return None
    return tuple(v)


def _valid_date(v: object, *, full: bool) -> bool:
    """``AAAA-MM`` oppure ``AAAA-MM-GG`` (se ``full`` solo la seconda), data reale."""
    if type(v) is not str:
        return False
    m = _DATE_RE.fullmatch(v)
    if m is None:
        return False
    year, month, day = int(m.group(1)), int(m.group(2)), m.group(3)
    if day is None:
        return (not full) and 1 <= month <= 12 and year >= 1
    try:
        datetime.date(year, month, int(day))
    except ValueError:
        return False
    return True


def _parse_source(d: object) -> Source:
    if type(d) is not dict or set(d) != _SOURCE_KEYS:
        _fail("invalid_source")
    ok = (
        _matches(d["id"], _SRC_RE)
        and _in(d["type"], SOURCE_TYPES)
        and _is_text(d["publisher"], CAP_SRC_PUBLISHER)
        and _is_text(d["title"], CAP_SRC_TITLE)
        and type(d["url"]) is str
        and len(d["url"]) <= CAP_URL
        and _URL_RE.fullmatch(d["url"]) is not None
        and _valid_date(d["published_or_checked"], full=False)
        and _is_text(d["assessment"], CAP_SRC_ASSESSMENT)
        and _in(d["source_grade"], SOURCE_GRADES)
    )
    if not ok:
        _fail("invalid_source")
    return Source(**d)


def _parse_strategy(d: object) -> Strategy:
    if type(d) is not dict or set(d) != _STRATEGY_KEYS:
        _fail("invalid_strategy")
    regimes = _str_list(d["candidate_regimes"], 1, len(REGIMES), allowed=REGIMES)
    timeframes = _str_list(d["timeframes"], 1, len(TIMEFRAMES), allowed=TIMEFRAMES)
    features = _str_list(d["required_features"], 1, 12, pattern=_FEATURE_RE)
    sources = _str_list(d["sources"], 1, 6, pattern=_SRC_RE)
    ok = (
        _matches(d["id"], _SID_RE)
        and _is_text(d["name"], CAP_NAME)
        and _in(d["family"], FAMILIES)
        and _in(d["holding_style"], HOLDING_STYLES)
        and regimes is not None
        and not ("ALL" in regimes and len(regimes) != 1)
        and timeframes is not None
        and features is not None
        and sources is not None
        and _is_text(d["entry_hypothesis"], CAP_RULE_TEXT)
        and _is_text(d["exit_hypothesis"], CAP_RULE_TEXT)
        and _is_text(d["invalidate_when"], CAP_RULE_TEXT)
        and _is_text(d["known_failure_modes"], CAP_RULE_TEXT)
        and _in(d["rule_origin"], RULE_ORIGINS)
        and _is_text(d["limitations"], CAP_RULE_TEXT)
        and _in(d["research_priority"], PRIORITIES)
        and type(d["proven_profitable"]) is bool
        and type(d["validated_on_bitget"]) is bool
        and type(d["status"]) is str
        and type(d["hypothesis_only"]) is bool
    )
    if not ok:
        _fail("invalid_strategy")
    return Strategy(
        id=d["id"], name=d["name"], family=d["family"], holding_style=d["holding_style"],
        candidate_regimes=regimes, timeframes=timeframes, required_features=features,
        entry_hypothesis=d["entry_hypothesis"], exit_hypothesis=d["exit_hypothesis"],
        invalidate_when=d["invalidate_when"], known_failure_modes=d["known_failure_modes"],
        sources=sources, rule_origin=d["rule_origin"], limitations=d["limitations"],
        research_priority=d["research_priority"], proven_profitable=d["proven_profitable"],
        validated_on_bitget=d["validated_on_bitget"], status=d["status"],
        hypothesis_only=d["hypothesis_only"],
    )


def _check_metadata(m: object) -> tuple[str, str]:
    if type(m) is not dict:
        _fail("invalid_library")
    version, date, status = m.get("version"), m.get("date"), m.get("status")
    if not _matches(version, _VERSION_RE) or not _valid_date(date, full=True):
        _fail("invalid_library")
    if status != METADATA_STATUS:
        _fail("invalid_library")
    return version, date


def parse_library(data: object) -> Library:
    """Valida una struttura gia' letta dal JSON e la trasforma in oggetti immutabili."""
    if type(data) is not dict or set(data) != _TOP_KEYS:
        _fail("invalid_library")
    version, date = _check_metadata(data["metadata"])
    for key in ("sources", "strategies"):
        if type(data[key]) is not list or not 1 <= len(data[key]) <= MAX_ITEMS:
            _fail("invalid_library")

    sources = tuple(_parse_source(d) for d in data["sources"])
    if len({s.id for s in sources}) != len(sources):
        _fail("duplicate_source_id")

    strategies = tuple(_parse_strategy(d) for d in data["strategies"])
    if len({s.id for s in strategies}) != len(strategies):
        _fail("duplicate_strategy_id")

    for s in strategies:
        if s.proven_profitable or s.validated_on_bitget or s.status != STATUS_RESEARCH_ONLY:
            _fail("claim_not_allowed")
    for s in strategies:
        if s.hypothesis_only != (s.rule_origin != "reproduced_source_rule"):
            _fail("inconsistent_origin")
    for s in strategies:
        if any(f not in KNOWN_FEATURES for f in s.required_features):
            _fail("unclassified_feature")
    known_sources = {x.id for x in sources}
    for s in strategies:
        if any(r not in known_sources for r in s.sources):
            _fail("unknown_source_ref")
    return Library(version=version, date=date, sources=sources, strategies=strategies)


# ---------------------------------------------------------------- caricamento
def _no_duplicate_keys(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate_key")
        out[k] = v
    return out


def _no_constant(name):
    raise ValueError("bad_constant")


def load_library_bytes(raw: bytes, *, expected_sha256: str) -> Library:
    """Controlla l'hash dei byte, poi legge il JSON in modo rigido e valida."""
    if type(raw) is not bytes or type(expected_sha256) is not str:
        _fail("invalid_input")
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        _fail("kb_hash_mismatch")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=_no_constant,
        )
    except (ValueError, RecursionError):          # UnicodeDecodeError e JSONDecodeError sono ValueError
        raise ValueError("invalid_json") from None
    return parse_library(data)


def load_library() -> Library:
    """Carica la biblioteca impacchettata, fissata con ``KB_SHA256``."""
    raw = Path(__file__).with_name(KB_FILENAME).read_bytes()
    return load_library_bytes(raw, expected_sha256=KB_SHA256)


# ---------------------------------------------------------------- classificazione dei dati
def data_gaps(strategy: Strategy) -> tuple[str, ...]:
    """Feature richieste che oggi non abbiamo (ne' storiche ne' modellabili), nell'ordine della scheda."""
    if type(strategy) is not Strategy:
        _fail("invalid_strategy")
    return tuple(f for f in strategy.required_features if f not in _AVAILABLE_FEATURES)


def testable_now(strategy: Strategy) -> str:
    """``candles``, ``candles_funding_oi`` oppure ``needs_new_data`` (vedi docstring del modulo)."""
    if data_gaps(strategy):
        return DATA_NEEDS_NEW
    if any(f in HISTORY_FEATURES for f in strategy.required_features):
        return DATA_CANDLES_FUNDING_OI
    return DATA_CANDLES


def feature_caveats(strategy: Strategy) -> tuple[tuple[str, str], ...]:
    """Avvertenze note sulle feature della scheda (approssimazioni, dati modellati), nell'ordine della scheda."""
    if type(strategy) is not Strategy:
        _fail("invalid_strategy")
    return tuple(
        (f, FEATURE_CAVEATS[f]) for f in strategy.required_features if f in FEATURE_CAVEATS
    )


# ---------------------------------------------------------------- registro delle prove
RELATION_ANALOG = "analog"
EVIDENCE_PERIODS = ("dev", "val", "test")


@dataclass(frozen=True)
class PeriodResult:
    period: str
    n: Optional[int]
    gross_bp: Decimal
    net_bp: Optional[Decimal]
    t_stat: Optional[Decimal]


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    strategy_id: str
    relation: str
    lab_variant: str
    timeframe: str
    differences: str
    cost_scenario: str
    periods: tuple[PeriodResult, ...]
    source_doc: str
    run_id: str
    limits: str


_LAB_DOC = "claude/laboratorio-strategie-risultati-2026-10-09.md"
_LAB_RUN = "37916437081"
_LAB_COST = "A taker/taker 16 bp round trip (12 commissioni + 4 slippage), funding 1 bp/8h sui long"
_LAB_LIMITS = (
    "BTC e ETH correlati; un solo set di parametri; funding approssimato; potenza insufficiente "
    "per 20 bp; nessuna variante ha superato STRICT o COND"
)


def _p(period, n, gross, net=None, t=None) -> PeriodResult:
    return PeriodResult(
        period=period,
        n=n,
        gross_bp=Decimal(gross),
        net_bp=None if net is None else Decimal(net),
        t_stat=None if t is None else Decimal(t),
    )


_S1_4H = (
    _p("dev", 257, "19.5", "-1.4"), _p("val", 94, "35.7", "14.9"), _p("test", 76, "50.0", "30.5"),
)
_S2_1H = (
    _p("dev", 861, "23.5", "5.8"), _p("val", 364, "1.1", "-16.4"), _p("test", 255, "28.9", "11.7"),
)
_S3_1H = (
    _p("dev", None, "-10.4", "-26.8"), _p("val", None, "-10.4", "-26.9"),
    _p("test", None, "-5.4", "-21.8"),
)
_S3_15M = (
    _p("dev", None, "-3.7", "-19.8", "-2.1"), _p("val", None, "-3.5", "-19.6", "-1.6"),
    _p("test", None, "-8.4", "-24.6", "-3.5"),
)
_S4_15M = (_p("dev", None, "1.0"), _p("val", None, "-1.0"), _p("test", None, "-1.8"))
_S5_15M = (_p("dev", None, "-3.4"), _p("val", None, "0.1"), _p("test", None, "-0.6"))

_MR_RULES = (
    "Lab: Bollinger 2.5 sigma con rientro confermato in regime ADX<20, target SMA20"
)

EVIDENCE: tuple[EvidenceRecord, ...] = (
    EvidenceRecord(
        "E01", "S07", RELATION_ANALOG, "S2 Donchian-20 1h", "1h",
        "Lab: Donchian-20 su 1h con filtro EMA200 4h, ATR in espansione, stop 2.5 ATR, uscita "
        "Donchian-10, max 48h. La scheda lascia N=20/55 e i filtri come candidati non fissati.",
        _LAB_COST, _S2_1H, _LAB_DOC, _LAB_RUN, _LAB_LIMITS,
    ),
    EvidenceRecord(
        "E02", "S07", RELATION_ANALOG, "S1 Donchian-20 4h", "4h",
        "Timeframe 4h NON elencato nella scheda (5m, 15m, 1h). Lab: Donchian-20 con ADX>=25, "
        "EMA20/50, stop 2 ATR, trailing 3 ATR, max 10 giorni.",
        _LAB_COST, _S1_4H, _LAB_DOC, _LAB_RUN, _LAB_LIMITS,
    ),
    EvidenceRecord(
        "E03", "S05", RELATION_ANALOG, "S3 mean reversion Bollinger 15m", "15m",
        _MR_RULES + "; senza MACD. La scheda usa %B 0.2/0.8 con MACD e uscite a deviazione standard.",
        _LAB_COST, _S3_15M, _LAB_DOC, _LAB_RUN, _LAB_LIMITS,
    ),
    EvidenceRecord(
        "E04", "S05", RELATION_ANALOG, "S3 mean reversion Bollinger 1h", "1h",
        "Timeframe 1h NON elencato nella scheda (5m, 15m). " + _MR_RULES + "; senza MACD.",
        _LAB_COST, _S3_1H, _LAB_DOC, _LAB_RUN, _LAB_LIMITS,
    ),
    EvidenceRecord(
        "E05", "S21", RELATION_ANALOG, "S3 mean reversion Bollinger 15m", "15m",
        _MR_RULES + ". La scheda usa RSI estremo e ritorno verso EMA50: analogia di famiglia "
        "(mean reversion in range), non la stessa regola.",
        _LAB_COST, _S3_15M, _LAB_DOC, _LAB_RUN, _LAB_LIMITS,
    ),
    EvidenceRecord(
        "E06", "S21", RELATION_ANALOG, "S3 mean reversion Bollinger 1h", "1h",
        "Timeframe 1h NON elencato nella scheda (1m, 5m, 15m). " + _MR_RULES + ". La scheda "
        "usa RSI ed EMA50: analogia di famiglia, non la stessa regola.",
        _LAB_COST, _S3_1H, _LAB_DOC, _LAB_RUN, _LAB_LIMITS,
    ),
    EvidenceRecord(
        "E07", "S01", RELATION_ANALOG, "S4 pullback 15m nel trend 1h", "15m",
        "Lab: pullback su 15m nel trend 1h (regole nel documento del lab). La scheda usa "
        "direzione 1h/4h, struttura 15m e trigger 1m/5m verso EMA20/50. Variante inversa (non "
        "una scheda): lordo +0.7/+2.0/+1.2 bp.",
        _LAB_COST, _S4_15M, _LAB_DOC, _LAB_RUN, _LAB_LIMITS,
    ),
    EvidenceRecord(
        "E08", "S06", RELATION_ANALOG, "S5 squeeze Bollinger con volume 15m", "15m",
        "Lab: squeeze Bollinger con volume su 15m (regole nel documento del lab); "
        "corrispondenza con la scheda non verificata punto per punto. Variante inversa (non "
        "una scheda): lordo +2.0/-0.4/+2.6 bp.",
        _LAB_COST, _S5_15M, _LAB_DOC, _LAB_RUN, _LAB_LIMITS,
    ),
)


def _valid_period(p: object) -> bool:
    if type(p) is not PeriodResult or not _in(p.period, frozenset(EVIDENCE_PERIODS)):
        return False
    if p.n is not None and (type(p.n) is not int or p.n < 0):
        return False
    if type(p.gross_bp) is not Decimal or not p.gross_bp.is_finite():
        return False
    for v in (p.net_bp, p.t_stat):
        if v is not None and (type(v) is not Decimal or not v.is_finite()):
            return False
    return True


def _valid_record(r: object) -> bool:
    if type(r) is not EvidenceRecord:
        return False
    periods = r.periods
    return (
        _matches(r.evidence_id, _EVIDENCE_ID_RE)
        and _matches(r.strategy_id, _SID_RE)
        and r.relation == RELATION_ANALOG
        and _is_text(r.lab_variant, 120)
        and _in(r.timeframe, TIMEFRAMES)
        and _is_text(r.differences, CAP_RULE_TEXT)
        and _is_text(r.cost_scenario, 200)
        and type(periods) is tuple
        and len(periods) >= 1                           # al massimo 3: periodi unici fra 3 nomi ammessi
        and all(_valid_period(p) for p in periods)
        and len({p.period for p in periods}) == len(periods)
        and _is_text(r.source_doc, 200)
        and _matches(r.run_id, _RUN_ID_RE)
        and _is_text(r.limits, CAP_RULE_TEXT)
    )


def check_evidence(library: Library, records: Sequence[EvidenceRecord]) -> None:
    """Verifica un registro di prove contro la biblioteca; ``ValueError`` con il codice."""
    if type(library) is not Library or not isinstance(records, (tuple, list)):
        _fail("invalid_evidence")
    if not all(_valid_record(r) for r in records):
        _fail("invalid_evidence")
    if len({r.evidence_id for r in records}) != len(records):
        _fail("duplicate_evidence_id")
    known = {s.id for s in library.strategies}
    if any(r.strategy_id not in known for r in records):
        _fail("evidence_unknown_strategy")


def evidence_for(
    strategy_id: str, records: Sequence[EvidenceRecord] = EVIDENCE
) -> tuple[EvidenceRecord, ...]:
    """Prove registrate per una scheda, nell'ordine del registro."""
    return tuple(r for r in records if r.strategy_id == strategy_id)


def _timeframe_in_card(library: Library, record: EvidenceRecord) -> bool:
    return record.timeframe in library.strategy(record.strategy_id).timeframes


# ---------------------------------------------------------------- rapporto
def format_library(library: Library, records: Sequence[EvidenceRecord] = EVIDENCE) -> str:
    """Tabella di testo deterministica: una riga per scheda, con classe dati, lacune e prove."""
    check_evidence(library, records)
    classes = [testable_now(s) for s in library.strategies]
    counts = ", ".join(
        f"{c}={classes.count(c)}" for c in (DATA_CANDLES, DATA_CANDLES_FUNDING_OI, DATA_NEEDS_NEW)
    )
    lines = [
        f"Biblioteca strategica v{library.version} ({library.date}): {len(library.strategies)} "
        f"schede, {len(library.sources)} fonti, tutte {STATUS_RESEARCH_ONLY}",
        f"Dati: {counts}",
        "id | famiglia | priorita | origine | dati | lacune | prove",
    ]
    for s, cls in zip(library.strategies, classes):
        ev = evidence_for(s.id, records)
        off = sum(1 for r in ev if not _timeframe_in_card(library, r))
        if ev:
            note = f"{len(ev)} {RELATION_ANALOG}" + (f" ({off} con timeframe fuori scheda)" if off else "")
        else:
            note = "-"
        gaps = ",".join(data_gaps(s)) or "-"
        lines.append(
            f"{s.id} | {s.family} | {s.research_priority} | {s.rule_origin} | {cls} | {gaps} | {note}"
        )
    return "\n".join(lines) + "\n"
