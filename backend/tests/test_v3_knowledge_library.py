"""F7 / L0 — biblioteca strategica: verifica INDIPENDENTE (Claude) del caricatore, della classificazione e del registro prove.

Come e' scritta (lezioni dei passi precedenti):
* il JSON impacchettato e' riletto QUI con ``json`` e confrontato campo per campo con gli
  oggetti del modulo (oracolo indipendente dal parser del modulo);
* la tabella delle classi di dati (A/B/C) e delle lacune e' scritta a mano dalla lettura delle
  schede, non calcolata dal modulo; idem i numeri del registro prove, copiati dal documento
  del laboratorio del 9 ottobre;
* ogni codice d'errore ha un controllo valido e un difetto che differisce SOLO per quel
  difetto, applicato in piu' posizioni (non solo la prima); le FASI di validazione hanno un
  test di precedenza;
* input ostili: bool per int, tipi non hashable, unicode a larghezza piena, ``\\n`` finale
  (fullmatch), NaN/Infinity/chiavi duplicate nel JSON, hash giusto con contenuto sbagliato e
  viceversa;
* purezza del modulo (AST) e indipendenza dalla directory di lavoro.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest

from backend.v3.knowledge import library as lib_mod
from backend.v3.knowledge.library import (
    EVIDENCE, KB_SHA256, EvidenceRecord, Library, PeriodResult, Strategy,
    check_evidence, data_gaps, evidence_for, feature_caveats, format_library,
    load_library, load_library_bytes, parse_library,
)
from backend.v3.knowledge.library import testable_now as classify_data   # 'test*' verrebbe raccolto da pytest

KB_PATH = Path(lib_mod.__file__).with_name("strategy_kb.json")
RAW_BYTES = KB_PATH.read_bytes()
RAW = json.loads(RAW_BYTES.decode("utf-8"))
PINNED_SHA = "0b2900d3a545f25ad242d48c1de04c844b22643fcaae3f0243e5a06061e85c1b"

N_STRATEGIES = len(RAW["strategies"])
N_SOURCES = len(RAW["sources"])
S_POS = (0, 11, N_STRATEGIES - 1)        # prima, centrale, ultima scheda
SRC_POS = (0, 14, N_SOURCES - 1)         # prima, centrale, ultima fonte


def fresh() -> dict:
    return copy.deepcopy(RAW)


def expect(code: str, data) -> None:
    with pytest.raises(ValueError) as exc:
        parse_library(data)
    assert str(exc.value) == code


def with_strategy(idx: int, **over) -> dict:
    d = fresh()
    d["strategies"][idx].update(over)
    return d


def with_source(idx: int, **over) -> dict:
    d = fresh()
    d["sources"][idx].update(over)
    return d


# ======================================================================= dati e hash
class TestPinnedFile:
    def test_hash_constant_matches_packaged_file_and_literal(self):
        assert hashlib.sha256(RAW_BYTES).hexdigest() == KB_SHA256 == PINNED_SHA

    def test_file_is_utf8_without_bom(self):
        assert RAW_BYTES[:3] != b"\xef\xbb\xbf"
        RAW_BYTES.decode("utf-8")

    def test_gitattributes_keeps_bytes_untouched(self):
        ga = KB_PATH.with_name(".gitattributes").read_text(encoding="utf-8").split()
        assert ga == ["strategy_kb.json", "-text"]

    def test_load_library_works_from_any_cwd(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert len(load_library().strategies) == 24


class TestRealLibraryMatchesRawJson:
    """Oracolo: il JSON riletto qui, campo per campo."""

    lib = load_library()

    def test_counts_order_and_metadata(self):
        assert self.lib.version == RAW["metadata"]["version"] == "1.0.0"
        assert self.lib.date == RAW["metadata"]["date"] == "2026-11-04"
        assert [s.id for s in self.lib.strategies] == [f"S{i:02d}" for i in range(1, 25)]
        assert [s.id for s in self.lib.sources] == [x["id"] for x in RAW["sources"]]
        assert (len(self.lib.strategies), len(self.lib.sources)) == (24, 30)

    def test_every_strategy_field_equals_raw(self):
        for obj, raw in zip(self.lib.strategies, RAW["strategies"]):
            got = dataclasses.asdict(obj)
            want = {k: (tuple(v) if isinstance(v, list) else v) for k, v in raw.items()}
            assert got == want
            assert set(got) == set(raw)

    def test_every_source_field_equals_raw(self):
        for obj, raw in zip(self.lib.sources, RAW["sources"]):
            assert dataclasses.asdict(obj) == raw

    def test_honesty_flags_in_the_real_data(self):
        for s in self.lib.strategies:
            assert (s.proven_profitable, s.validated_on_bitget, s.status) == (
                False, False, "research_only")
        origins = [s.rule_origin for s in self.lib.strategies]
        assert origins.count("hypothesis") == 13
        assert origins.count("source_concept_adapted") == 10
        assert origins.count("reproduced_source_rule") == 1
        reproduced = [s for s in self.lib.strategies if s.rule_origin == "reproduced_source_rule"]
        assert [s.id for s in reproduced] == ["S05"]
        assert [s.id for s in self.lib.strategies if not s.hypothesis_only] == ["S05"]
        prio = [s.research_priority for s in self.lib.strategies]
        assert (prio.count("high"), prio.count("medium"), prio.count("low")) == (10, 9, 5)
        assert [s.id for s in self.lib.strategies if s.candidate_regimes == ("ALL",)] == [
            "S12", "S16", "S17", "S24"]

    def test_legit_symbols_survive_hygiene(self):
        """Le soglie con < > e le frecce -> NON sono markup e devono passare; l'apostrofo tipografico pure."""
        s05, s14, s18, s06 = (self.lib.strategy(i) for i in ("S05", "S14", "S18", "S06"))
        assert "%B < 0.2" in s05.entry_hypothesis and "MACD histogram > 0" in s05.entry_hypothesis
        assert "hist < 0" in s05.entry_hypothesis and "%B > 0.8" in s05.entry_hypothesis
        assert "->" in s14.entry_hypothesis and "->" in s18.known_failure_modes
        assert "\u2019" in s06.exit_hypothesis
        assert "\u2019" in self.lib.sources[[x.id for x in self.lib.sources].index("G01")].title

    def test_unused_sources_are_allowed(self):
        used = {r for s in self.lib.strategies for r in s.sources}
        unused = {x.id for x in self.lib.sources} - used
        assert unused == {"D07", "D08", "D12", "D13", "D14", "G02", "V05"}

    def test_closed_vocabularies_are_exactly_what_the_kb_uses(self):
        assert lib_mod.FAMILIES == {
            "basis_arbitrage", "breakout", "factor", "funding_arbitrage", "grid", "liquidations",
            "liquidity", "market_making", "mean_reversion", "meta", "order_flow", "positioning",
            "trend", "volatility", "volume_profile", "vwap"}
        assert lib_mod.HOLDING_STYLES == {
            "decision_system", "intraday", "market_neutral", "microstructure", "scalp",
            "signal_filter", "swing"}
        assert lib_mod.REGIMES == {
            "ALL", "EXPANSION", "RANGE", "REVERSAL_CANDIDATE", "SHOCK", "TREND_DOWN", "TREND_UP"}
        assert lib_mod.TIMEFRAMES == {"tick", "1m", "5m", "15m", "1h", "4h", "1d"}
        assert lib_mod.RULE_ORIGINS == {
            "hypothesis", "reproduced_source_rule", "source_concept_adapted"}
        assert lib_mod.PRIORITIES == {"high", "medium", "low"}
        assert lib_mod.SOURCE_TYPES == {"documentation", "github", "paper", "youtube"}
        assert lib_mod.SOURCE_GRADES == {"A", "B", "C", "D"}
        assert lib_mod.STATUS_RESEARCH_ONLY == "research_only"
        # e coincidono con i valori realmente usati (nessun valore in piu' "per sicurezza")
        used = lambda key: {s[key] for s in RAW["strategies"]}  # noqa: E731
        assert used("family") == lib_mod.FAMILIES
        assert used("holding_style") == lib_mod.HOLDING_STYLES
        assert used("rule_origin") == lib_mod.RULE_ORIGINS
        assert used("research_priority") == lib_mod.PRIORITIES
        assert {r for s in RAW["strategies"] for r in s["candidate_regimes"]} == lib_mod.REGIMES
        assert {t for s in RAW["strategies"] for t in s["timeframes"]} == lib_mod.TIMEFRAMES
        assert {x["type"] for x in RAW["sources"]} == lib_mod.SOURCE_TYPES
        assert {x["source_grade"] for x in RAW["sources"]} <= lib_mod.SOURCE_GRADES


# ======================================================================= controllo valido
class TestControl:
    def test_raw_parses_and_equals_load(self):
        assert parse_library(fresh()) == load_library()

    def test_flexibility_that_must_not_be_rejected(self):
        d = fresh()
        d["strategies"].reverse()                                  # ordine delle schede libero
        d["sources"].reverse()
        d["strategies"][0] = dict(reversed(list(d["strategies"][0].items())))  # ordine dei campi
        lib = parse_library(d)
        assert lib.strategies[0].id == "S24" and lib.strategies[-1].id == "S01"
        d = fresh()
        del d["strategies"][-1]                                    # 23 schede: ok
        assert len(parse_library(d).strategies) == 23
        d = fresh()
        d["metadata"]["note_extra"] = "ok"                         # metadati descrittivi in piu': ignorati
        assert parse_library(d) == load_library()
        d = with_strategy(4, rule_origin="hypothesis", hypothesis_only=True)
        assert parse_library(d).strategy("S05").rule_origin == "hypothesis"   # coppia coerente
        d = with_strategy(0, candidate_regimes=["TREND_UP", "TREND_DOWN", "EXPANSION", "RANGE",
                                                "REVERSAL_CANDIDATE", "SHOCK"])
        assert len(parse_library(d).strategies[0].candidate_regimes) == 6
        d = with_strategy(0, timeframes=["tick", "1m", "5m", "15m", "1h", "4h", "1d"])
        assert len(parse_library(d).strategies[0].timeframes) == 7
        d = with_strategy(0, sources=["V01", "V02", "V03", "V04", "V05", "V06"])
        assert len(parse_library(d).strategies[0].sources) == 6

    def test_input_is_not_mutated_and_output_is_detached(self):
        d = fresh()
        before = copy.deepcopy(d)
        lib = parse_library(d)
        assert d == before
        d["strategies"][0]["required_features"].append("zzz")
        d["strategies"][0]["name"] = "cambiato"
        assert lib == load_library()

    def test_deterministic(self):
        assert load_library() == load_library()
        assert format_library(load_library()) == format_library(load_library())


# ======================================================================= invalid_library
class TestInvalidLibrary:
    @pytest.mark.parametrize("data", [None, [], "x", 1, (), RAW["strategies"]])
    def test_top_level_not_a_dict(self, data):
        expect("invalid_library", data)

    def test_top_level_keys_exact(self):
        d = fresh(); d["extra"] = []
        expect("invalid_library", d)
        for k in ("metadata", "sources", "strategies"):
            d = fresh(); del d[k]
            expect("invalid_library", d)

    @pytest.mark.parametrize("meta", [None, [], "x", 1])
    def test_metadata_not_a_dict(self, meta):
        d = fresh(); d["metadata"] = meta
        expect("invalid_library", d)

    @pytest.mark.parametrize("key,value", [
        ("version", None), ("version", "1.0"), ("version", "1.0.0.0"), ("version", "v1.0.0"),
        ("version", "1.0.0\n"), ("version", " 1.0.0"), ("version", "\uff11.0.0"),
        ("version", 1), ("version", ["1.0.0"]),
        ("date", None), ("date", "2026-11"), ("date", "2026"), ("date", "2026-02-30"),
        ("date", "2026-13-01"), ("date", "2026-11-31"), ("date", "0000-01-01"),
        ("date", "2026-11-04\n"), ("date", "2026-11-4"), ("date", "\uff12026-11-04"), ("date", 20261104),
        ("status", None), ("status", "research_only"), ("status", "live"), ("status", "research_only_no_live\n"),
    ])
    def test_metadata_fields(self, key, value):
        d = fresh(); d["metadata"][key] = value
        expect("invalid_library", d)

    @pytest.mark.parametrize("key", ["version", "date", "status"])
    def test_metadata_field_missing(self, key):
        d = fresh(); del d["metadata"][key]
        expect("invalid_library", d)

    @pytest.mark.parametrize("key", ["sources", "strategies"])
    def test_lists_must_be_lists_and_nonempty_and_bounded(self, key):
        for bad in (None, {}, (), "x", 1):
            d = fresh(); d[key] = bad
            expect("invalid_library", d)
        d = fresh(); d[key] = []
        expect("invalid_library", d)
        d = fresh(); d[key] = [copy.deepcopy(RAW[key][0]) for _ in range(201)]
        expect("invalid_library", d)                     # 201 > limite: respinta PRIMA di guardare gli elementi
        d = fresh(); d[key] = [copy.deepcopy(RAW[key][0]) for _ in range(200)]
        expect("duplicate_source_id" if key == "sources" else "duplicate_strategy_id", d)


# ======================================================================= testo libero (stesse regole ovunque)
BAD_TEXTS = [
    "", " ", " x", "x ", "x\n", "\nx", "a\nb", "a\tb", "a\x00b", "a\x7fb", "a\u200bb", "a\u202eb",
    "x\u00a0", "a`b", "a{b", "a}b", "```", "see http://x.io", "see HTTPS://x.io", "go www.x.io",
    "<b>x", "x</b>", "a<b", "<!--", "<?x", 123, None, ["x"], b"x", True,
]
GOOD_TEXTS = [
    "a < b", "a > b", "x->y", "%B < 0.2, MACD > 0", "caff\u00e8", "it\u2019s", "<", "a <", "< 0", "a <3",
    "prezzo<2", "-", "x" * 5,
]
STRATEGY_TEXT_FIELDS = [
    ("name", 80), ("entry_hypothesis", 400), ("exit_hypothesis", 400), ("invalidate_when", 400),
    ("known_failure_modes", 400), ("limitations", 400),
]
SOURCE_TEXT_FIELDS = [("publisher", 80), ("title", 200), ("assessment", 300)]


class TestFreeText:
    @pytest.mark.parametrize("field,cap", STRATEGY_TEXT_FIELDS)
    def test_strategy_text_bad_values(self, field, cap):
        for pos in S_POS:
            for bad in BAD_TEXTS:
                expect("invalid_strategy", with_strategy(pos, **{field: bad}))

    @pytest.mark.parametrize("field,cap", STRATEGY_TEXT_FIELDS)
    def test_strategy_text_good_values_and_cap(self, field, cap):
        for pos in S_POS:
            for good in GOOD_TEXTS + ["a" * cap]:
                assert getattr(parse_library(with_strategy(pos, **{field: good})).strategies[pos], field) == good
            expect("invalid_strategy", with_strategy(pos, **{field: "a" * (cap + 1)}))

    @pytest.mark.parametrize("field,cap", SOURCE_TEXT_FIELDS)
    def test_source_text_bad_values(self, field, cap):
        for pos in SRC_POS:
            for bad in BAD_TEXTS:
                expect("invalid_source", with_source(pos, **{field: bad}))

    @pytest.mark.parametrize("field,cap", SOURCE_TEXT_FIELDS)
    def test_source_text_good_values_and_cap(self, field, cap):
        for pos in SRC_POS:
            for good in GOOD_TEXTS + ["a" * cap]:
                assert getattr(parse_library(with_source(pos, **{field: good})).sources[pos], field) == good
            expect("invalid_source", with_source(pos, **{field: "a" * (cap + 1)}))


# ======================================================================= invalid_source
class TestInvalidSource:
    @pytest.mark.parametrize("bad", [None, [], "V01", 1, ()])
    def test_item_not_a_dict(self, bad):
        for pos in SRC_POS:
            d = fresh(); d["sources"][pos] = bad
            expect("invalid_source", d)

    def test_keys_exact(self):
        for pos in SRC_POS:
            d = fresh(); d["sources"][pos]["extra"] = "x"
            expect("invalid_source", d)
            for k in RAW["sources"][0]:
                d = fresh(); del d["sources"][pos][k]
                expect("invalid_source", d)

    @pytest.mark.parametrize("bad", [
        "V1", "V001", "X01", "v01", "V01\n", " V01", "V0\uff11", "\uff36" "01", "", None, 1, ["V01"], True])
    def test_id(self, bad):
        for pos in SRC_POS:
            expect("invalid_source", with_source(pos, id=bad))

    @pytest.mark.parametrize("bad", ["blog", "YouTube", "paper ", "", None, ["paper"], {}, 1])
    def test_type(self, bad):
        for pos in SRC_POS:
            expect("invalid_source", with_source(pos, type=bad))

    @pytest.mark.parametrize("bad", ["E", "a", "AB", "A\n", "", None, ["A"], 1])
    def test_grade(self, bad):
        for pos in SRC_POS:
            expect("invalid_source", with_source(pos, source_grade=bad))

    @pytest.mark.parametrize("bad", [
        "http://example.com/x", "ftp://example.com", "HTTPS://example.com", "https://", "https://host",
        "https://exa mple.com", "https://example.com/a b", "https://example.com/\n", "https://example.com\n",
        "javascript:alert(1)", "//example.com", "example.com", "https://user@example.com/",
        "https://exa\u00e4mple.com", "https://example..com", "https://-.", "https://example.com/<x>",
        "https://example.com/\"", "https://example.com/'", "https://example.com/`", "https://example.com/\\",
        "https://example.com:/x", "https://example.com:123456/x", "https://example.com/{x}",
        "https://example.com/" + "a" * 300, "", None, 1, ["https://example.com"],
    ])
    def test_url_bad(self, bad):
        for pos in SRC_POS:
            expect("invalid_source", with_source(pos, url=bad))

    def test_url_good_and_cap(self):
        for good in ("https://example.com", "https://docs.example.com/a/b?x=1&y=2#frag",
                     "https://example.com:8443/x", "https://github.com/a/b-c_d.e%20f"):
            assert parse_library(with_source(3, url=good)).sources[3].url == good
        ok = "https://example.com/" + "a" * (300 - len("https://example.com/"))
        assert len(ok) == 300 and parse_library(with_source(3, url=ok)).sources[3].url == ok
        expect("invalid_source", with_source(3, url=ok + "a"))

    @pytest.mark.parametrize("bad", [
        "2023-13", "2023-00", "2023", "2023-1", "23-01", "2023-02-30", "2023-01-32", "2023-01-00",
        "2023-01-1", "2023-01-01\n", "2023-01-", "\uff12023-01", "2023/01/01", "", None, 202301, ["2023-01"],
        "0000-05", "0000-05-10"])
    def test_date_bad(self, bad):
        for pos in SRC_POS:
            expect("invalid_source", with_source(pos, published_or_checked=bad))

    @pytest.mark.parametrize("good", ["2012-05", "2023-02-28", "2024-02-29", "2023-12", "2023-01-01"])
    def test_date_good(self, good):
        assert parse_library(with_source(5, published_or_checked=good)).sources[5].published_or_checked == good
        # l'anno bisestile conta
        expect("invalid_source", with_source(5, published_or_checked="2023-02-29"))

    def test_duplicate_source_id(self):
        for k in (1, 14, N_SOURCES - 1):
            d = fresh(); d["sources"][k]["id"] = d["sources"][0]["id"]
            expect("duplicate_source_id", d)


# ======================================================================= invalid_strategy
LIST_FIELD_CASES = {
    "candidate_regimes": [
        [], ["BULL"], ["trend_up"], ["TREND_UP", "TREND_UP"], ["ALL", "RANGE"], ["RANGE", "ALL"],
        "TREND_UP", ("TREND_UP",), [["TREND_UP"]], [1], [None], [{}], [True],
    ],
    "timeframes": [[], ["2h"], ["1M"], ["5m", "5m"], "5m", ("5m",), [["5m"]], [5], [None]],
    "sources": [
        [], ["V1"], ["v01"], ["X01"], ["V01", "V01"], "V01", ("V01",), [["V01"]], [1], [None],
        ["V01\n"], ["V0\uff11"], ["V01", "V02", "V03", "V04", "V05", "V06", "V07"],
    ],
    "required_features": [
        [], ["ATR"], ["1atr"], ["atr-14"], ["atr 14"], [""], ["a" * 41], ["atr\n"], ["\u00e0tr"],
        ["atr", "atr"], "atr", ("atr",), [["atr"]], [1], [None], [{}],
        [f"f{i:02d}" for i in range(13)],
    ],
}


class TestInvalidStrategy:
    @pytest.mark.parametrize("bad", [None, [], "S01", 1, ()])
    def test_item_not_a_dict(self, bad):
        for pos in S_POS:
            d = fresh(); d["strategies"][pos] = bad
            expect("invalid_strategy", d)

    def test_keys_exact(self):
        for pos in S_POS:
            d = fresh(); d["strategies"][pos]["extra"] = "x"
            expect("invalid_strategy", d)
            d = fresh(); d["strategies"][pos]["Status"] = "x"       # refuso di un campo vero
            expect("invalid_strategy", d)
            for k in RAW["strategies"][0]:
                d = fresh(); del d["strategies"][pos][k]
                expect("invalid_strategy", d)

    @pytest.mark.parametrize("bad", [
        "S1", "S001", "s01", "T01", "S01\n", " S01", "S0\uff11", "\uff33" "01", "", None, 1, ["S01"], True])
    def test_id(self, bad):
        for pos in S_POS:
            expect("invalid_strategy", with_strategy(pos, id=bad))

    @pytest.mark.parametrize("field", ["family", "holding_style", "rule_origin", "research_priority"])
    @pytest.mark.parametrize("bad", ["", "bogus", "Trend", "trend ", "trend\n", None, ["trend"], {}, 1, True])
    def test_enums(self, field, bad):
        for pos in S_POS:
            expect("invalid_strategy", with_strategy(pos, **{field: bad}))

    @pytest.mark.parametrize("field", list(LIST_FIELD_CASES))
    def test_list_fields(self, field):
        for pos in S_POS:
            for bad in LIST_FIELD_CASES[field]:
                expect("invalid_strategy", with_strategy(pos, **{field: bad}))

    def test_feature_list_boundary_is_twelve(self):
        twelve = sorted(lib_mod.KNOWN_FEATURES)[:12]
        d = with_strategy(0, required_features=twelve)
        assert parse_library(d).strategies[0].required_features == tuple(twelve)
        expect("invalid_strategy", with_strategy(0, required_features=sorted(lib_mod.KNOWN_FEATURES)[:13]))

    def test_source_list_boundary_is_six(self):
        expect("invalid_strategy", with_strategy(
            0, sources=["V01", "V02", "V03", "V04", "V05", "V06", "V07"]))

    @pytest.mark.parametrize("field", ["proven_profitable", "validated_on_bitget", "hypothesis_only"])
    @pytest.mark.parametrize("bad", [0, 1, "False", "True", "", None, [], {}, 0.0])
    def test_bool_fields_need_real_bool(self, field, bad):
        for pos in S_POS:
            expect("invalid_strategy", with_strategy(pos, **{field: bad}))

    @pytest.mark.parametrize("bad", [0, 1, None, [], {}, True])
    def test_status_must_be_a_string(self, bad):
        for pos in S_POS:
            expect("invalid_strategy", with_strategy(pos, status=bad))

    def test_regime_all_must_stand_alone(self):
        assert parse_library(with_strategy(0, candidate_regimes=["ALL"])).strategies[0].candidate_regimes == ("ALL",)
        for bad in (["ALL", "RANGE"], ["RANGE", "ALL"], ["TREND_UP", "ALL", "SHOCK"]):
            expect("invalid_strategy", with_strategy(0, candidate_regimes=bad))

    def test_duplicate_strategy_id(self):
        for k in (1, 11, N_STRATEGIES - 1):
            d = fresh(); d["strategies"][k]["id"] = d["strategies"][0]["id"]
            expect("duplicate_strategy_id", d)


# ======================================================================= affermazioni, origine, feature, fonti
class TestClaimsOriginFeaturesSources:
    @pytest.mark.parametrize("field", ["proven_profitable", "validated_on_bitget"])
    def test_true_flags_are_refused(self, field):
        for pos in S_POS:
            expect("claim_not_allowed", with_strategy(pos, **{field: True}))

    @pytest.mark.parametrize("status", [
        "", "paper_eligible", "lab_positive_oos", "lab_negative", "RESEARCH_ONLY", "research_only ",
        "research_only\n", "research-only", "live"])
    def test_other_statuses_are_refused(self, status):
        for pos in S_POS:
            expect("claim_not_allowed", with_strategy(pos, status=status))

    def test_hypothesis_only_must_follow_origin(self):
        for pos in S_POS:
            s = RAW["strategies"][pos]
            expect("inconsistent_origin", with_strategy(pos, hypothesis_only=not s["hypothesis_only"]))
        expect("inconsistent_origin", with_strategy(4, rule_origin="hypothesis"))              # S05 resta False
        expect("inconsistent_origin", with_strategy(0, rule_origin="reproduced_source_rule"))  # S01 resta True
        expect("inconsistent_origin", with_strategy(0, rule_origin="source_concept_adapted", hypothesis_only=False))
        assert parse_library(with_strategy(
            0, rule_origin="reproduced_source_rule", hypothesis_only=False)).strategies[0].hypothesis_only is False

    @pytest.mark.parametrize("feature", ["zzz_new", "atr14", "a" * 40, "l3_orderbook", "spread_bp", "ohlc"])
    def test_unclassified_feature(self, feature):
        for pos in S_POS:
            d = fresh(); d["strategies"][pos]["required_features"].append(feature)
            expect("unclassified_feature", d)
            d = fresh(); d["strategies"][pos]["required_features"][0] = feature
            expect("unclassified_feature", d)

    def test_unknown_source_reference(self):
        for pos in S_POS:
            expect("unknown_source_ref", with_strategy(pos, sources=["V99"]))
            expect("unknown_source_ref", with_strategy(pos, sources=["V01", "D99"]))
        d = fresh()                       # tolgo una fonte che qualcuno cita
        d["sources"] = [x for x in d["sources"] if x["id"] != "P03"]
        expect("unknown_source_ref", d)
        d = fresh()                       # tolgo una fonte che NESSUNO cita: ammesso
        d["sources"] = [x for x in d["sources"] if x["id"] != "D07"]
        assert len(parse_library(d).sources) == 29


class TestStagePrecedence:
    """Le fasi sono nell'ordine documentato; un difetto di una fase prevale su tutti quelli delle successive."""

    DEFECTS = [
        ("invalid_library", lambda d: d["metadata"].update(version="x")),
        ("invalid_source", lambda d: d["sources"][1].update(type="blog")),
        ("duplicate_source_id", lambda d: d["sources"][3].update(id=d["sources"][2]["id"])),
        ("invalid_strategy", lambda d: d["strategies"][1].update(family="bogus")),
        ("duplicate_strategy_id", lambda d: d["strategies"][3].update(id=d["strategies"][2]["id"])),
        ("claim_not_allowed", lambda d: d["strategies"][5].update(proven_profitable=True)),
        ("inconsistent_origin", lambda d: d["strategies"][6].update(hypothesis_only=False)),
        ("unclassified_feature", lambda d: d["strategies"][8]["required_features"].append("zzz_new")),
        ("unknown_source_ref", lambda d: d["strategies"][10].update(sources=["V99"])),
    ]

    @pytest.mark.parametrize("start", range(9))
    def test_earliest_stage_wins(self, start):
        d = fresh()
        for _, apply in self.DEFECTS[start:]:
            apply(d)
        expect(self.DEFECTS[start][0], d)

    @pytest.mark.parametrize("i", range(9))
    def test_each_defect_alone_gives_its_own_code(self, i):
        d = fresh()
        self.DEFECTS[i][1](d)
        # il difetto 'duplicate_source_id' orfana anche una fonte citata: il codice resta quello della fase precedente
        expect(self.DEFECTS[i][0], d)

    def test_later_stage_item_placed_first_does_not_win(self):
        d = fresh()
        d["strategies"][0]["proven_profitable"] = True                 # fase 6 sulla prima scheda
        d["strategies"][20]["family"] = "bogus"                        # fase 4 sull'ultima
        expect("invalid_strategy", d)


# ======================================================================= caricamento da byte
class TestLoadBytes:
    def test_good(self):
        assert load_library_bytes(RAW_BYTES, expected_sha256=KB_SHA256) == load_library()

    def test_expected_hash_is_keyword_only(self):
        with pytest.raises(TypeError):
            load_library_bytes(RAW_BYTES, KB_SHA256)  # type: ignore[misc]

    @pytest.mark.parametrize("raw", ["x", bytearray(b"x"), memoryview(b"x"), None, 1, ["x"]])
    def test_raw_must_be_bytes(self, raw):
        with pytest.raises(ValueError) as e:
            load_library_bytes(raw, expected_sha256=KB_SHA256)
        assert str(e.value) == "invalid_input"

    @pytest.mark.parametrize("h", [None, b"0" * 64, 1, ["0" * 64]])
    def test_expected_hash_must_be_str(self, h):
        with pytest.raises(ValueError) as e:
            load_library_bytes(RAW_BYTES, expected_sha256=h)
        assert str(e.value) == "invalid_input"

    @pytest.mark.parametrize("pos", [0, 100, len(RAW_BYTES) // 2, len(RAW_BYTES) - 1])
    def test_any_byte_change_is_a_mismatch(self, pos):
        raw = bytearray(RAW_BYTES)
        raw[pos] ^= 0x01
        with pytest.raises(ValueError) as e:
            load_library_bytes(bytes(raw), expected_sha256=KB_SHA256)
        assert str(e.value) == "kb_hash_mismatch"

    def test_appended_or_truncated_is_a_mismatch(self):
        for raw in (RAW_BYTES + b"\n", RAW_BYTES[:-1], b""):
            with pytest.raises(ValueError) as e:
                load_library_bytes(raw, expected_sha256=KB_SHA256)
            assert str(e.value) == "kb_hash_mismatch"

    def test_uppercase_or_padded_hash_is_a_mismatch(self):
        for h in (KB_SHA256.upper(), KB_SHA256 + " ", " " + KB_SHA256, KB_SHA256[:-1], ""):
            with pytest.raises(ValueError) as e:
                load_library_bytes(RAW_BYTES, expected_sha256=h)
            assert str(e.value) == "kb_hash_mismatch"

    def test_hash_is_checked_before_json(self):
        with pytest.raises(ValueError) as e:
            load_library_bytes(b"\xff not json", expected_sha256=KB_SHA256)
        assert str(e.value) == "kb_hash_mismatch"

    @staticmethod
    def _load(raw: bytes):
        return load_library_bytes(raw, expected_sha256=hashlib.sha256(raw).hexdigest())

    @pytest.mark.parametrize("raw", [
        b"", b"   ", b"{", b'{"a": 1,}', RAW_BYTES[:-2], RAW_BYTES + b"x", b"\xef\xbb\xbf" + RAW_BYTES,
        b"\xff\xfe{}", b'{"metadata": NaN, "sources": [], "strategies": []}',
        b'{"metadata": Infinity, "sources": [], "strategies": []}',
        b'{"metadata": -Infinity, "sources": [], "strategies": []}',
        b"[" * 100000, b'{"a": 1, "a": 2}',
    ])
    def test_bad_json_with_matching_hash(self, raw):
        with pytest.raises(ValueError) as e:
            self._load(raw)
        assert str(e.value) == "invalid_json"

    def test_duplicate_key_inside_a_real_record(self):
        text = RAW_BYTES.decode("utf-8")
        marker = '"id": "S01",'
        assert text.count(marker) == 1
        raw = text.replace(marker, marker + ' "id": "S01",').encode("utf-8")
        with pytest.raises(ValueError) as e:
            self._load(raw)
        assert str(e.value) == "invalid_json"

    @pytest.mark.parametrize("raw", [b"[]", b"null", b"{}", b'"x"', b"1"])
    def test_valid_json_wrong_shape_goes_to_validation(self, raw):
        with pytest.raises(ValueError) as e:
            self._load(raw)
        assert str(e.value) == "invalid_library"

    def test_semantic_defect_with_matching_hash_goes_to_validation(self):
        d = fresh(); d["strategies"][0]["proven_profitable"] = True
        with pytest.raises(ValueError) as e:
            self._load(json.dumps(d).encode("utf-8"))
        assert str(e.value) == "claim_not_allowed"


# ======================================================================= classificazione dei dati
CLASS_A = ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S15", "S20", "S21")
CLASS_B = ("S12", "S23")
GAPS_C = {
    "S10": ("l2_orderbook", "trades", "depth", "latency"),
    "S11": ("aggressor_trades", "cvd", "depth", "latency"),
    "S13": ("liquidation_feed", "trades"),
    "S14": ("trades_or_tick_volume", "volume_profile"),
    "S16": ("spot_mid", "perp_mid", "borrow_cost", "depth", "execution_latency"),
    "S17": ("funding_rate_by_venue", "perp_mid_by_venue", "depth", "margin_by_venue"),
    "S18": ("l2_orderbook", "fills", "latency", "inventory", "mark_price"),
    "S19": ("depth", "inventory"),
    "S22": ("futures_basis", "liquidity"),
    "S24": ("regime_probabilities", "strategy_oos_metrics", "market_data_health"),
}
EXPECTED_CLASS = {
    **{i: "candles" for i in CLASS_A},
    **{i: "candles_funding_oi" for i in CLASS_B},
    **{i: "needs_new_data" for i in GAPS_C},
}


def strat(features, **over) -> Strategy:
    base = dict(load_library().strategy("S01").__dict__)
    base.update(required_features=tuple(features), **over)
    return Strategy(**base)


class TestClassification:
    lib = load_library()

    def test_golden_table_covers_every_strategy_once(self):
        assert set(EXPECTED_CLASS) == {s.id for s in self.lib.strategies}
        assert len(CLASS_A) + len(CLASS_B) + len(GAPS_C) == 24

    def test_class_and_gaps_per_strategy(self):
        for s in self.lib.strategies:
            assert classify_data(s) == EXPECTED_CLASS[s.id], s.id
            assert data_gaps(s) == GAPS_C.get(s.id, ()), s.id

    def test_feature_partition(self):
        c, h, m, u = (lib_mod.CANDLE_FEATURES, lib_mod.HISTORY_FEATURES,
                      lib_mod.MODELLED_FEATURES, lib_mod.UNAVAILABLE_FEATURES)
        assert (len(c), len(h), len(m), len(u)) == (23, 2, 2, 24)
        assert not (c & h or c & m or c & u or h & m or h & u or m & u)
        used = {f for s in RAW["strategies"] for f in s["required_features"]}
        assert len(used) == 51 and c | h | m | u == used == lib_mod.KNOWN_FEATURES
        assert h == {"funding_rate", "open_interest"} and m == {"fees", "spread"}

    def test_class_combinations(self):
        assert classify_data(strat(["ohlcv", "atr"])) == "candles"
        assert classify_data(strat(["ohlcv", "spread", "fees"])) == "candles"            # modellati: non bloccano
        assert classify_data(strat(["ohlcv", "funding_rate"])) == "candles_funding_oi"
        assert classify_data(strat(["open_interest"])) == "candles_funding_oi"
        assert classify_data(strat(["ohlcv", "funding_rate", "depth"])) == "needs_new_data"
        assert classify_data(strat(["depth"])) == "needs_new_data"
        assert classify_data(strat(["ohlcv", "zzz_unknown"])) == "needs_new_data"      # chiuso: ignoto = lacuna
        assert data_gaps(strat(["ohlcv", "zzz_unknown", "depth", "spread"])) == ("zzz_unknown", "depth")
        assert data_gaps(strat(["depth", "ohlcv"])) == ("depth",)

    @pytest.mark.parametrize("fn", [classify_data, data_gaps, feature_caveats])
    @pytest.mark.parametrize("bad", [None, {}, RAW["strategies"][0], "S01", 1, []])
    def test_non_strategy_input(self, fn, bad):
        with pytest.raises(ValueError) as e:
            fn(bad)
        assert str(e.value) == "invalid_strategy"

    @pytest.mark.parametrize("fn", [classify_data, data_gaps, feature_caveats])
    def test_strategy_subclass_is_refused(self, fn):
        class Sub(Strategy):
            pass
        s = self.lib.strategy("S01")
        sub = Sub(**s.__dict__)
        with pytest.raises(ValueError) as e:
            fn(sub)
        assert str(e.value) == "invalid_strategy"

    def test_caveats(self):
        assert feature_caveats(self.lib.strategy("S03")) == (
            ("vwap_session", lib_mod.FEATURE_CAVEATS["vwap_session"]),
            ("volume", lib_mod.FEATURE_CAVEATS["volume"]),
            ("spread", lib_mod.FEATURE_CAVEATS["spread"]),
        )
        assert [f for f, _ in feature_caveats(self.lib.strategy("S12"))] == [
            "open_interest", "funding_rate", "volume"]                  # ordine della scheda
        assert feature_caveats(self.lib.strategy("S05")) == ()
        assert set(lib_mod.FEATURE_CAVEATS) <= lib_mod.KNOWN_FEATURES
        assert all(lib_mod._is_text(t, 300) for t in lib_mod.FEATURE_CAVEATS.values())
        assert lib_mod.FEATURE_CAVEATS["spread"].startswith("storico non disponibile")


# ======================================================================= registro prove
def _rows(*cells):
    return [(p, n, g, net, t) for p, n, g, net, t in cells]


S1_4H = _rows(("dev", 257, "19.5", "-1.4", None), ("val", 94, "35.7", "14.9", None),
              ("test", 76, "50.0", "30.5", None))
S2_1H = _rows(("dev", 861, "23.5", "5.8", None), ("val", 364, "1.1", "-16.4", None),
              ("test", 255, "28.9", "11.7", None))
S3_1H = _rows(("dev", None, "-10.4", "-26.8", None), ("val", None, "-10.4", "-26.9", None),
              ("test", None, "-5.4", "-21.8", None))
S3_15M = _rows(("dev", None, "-3.7", "-19.8", "-2.1"), ("val", None, "-3.5", "-19.6", "-1.6"),
               ("test", None, "-8.4", "-24.6", "-3.5"))
S4_15M = _rows(("dev", None, "1.0", None, None), ("val", None, "-1.0", None, None),
               ("test", None, "-1.8", None, None))
S5_15M = _rows(("dev", None, "-3.4", None, None), ("val", None, "0.1", None, None),
               ("test", None, "-0.6", None, None))
# copia a mano della tabella del documento "laboratorio-strategie-risultati-2026-10-09"
DOC_TABLE = {
    "E01": ("S07", "1h", S2_1H), "E02": ("S07", "4h", S1_4H),
    "E03": ("S05", "15m", S3_15M), "E04": ("S05", "1h", S3_1H),
    "E05": ("S21", "15m", S3_15M), "E06": ("S21", "1h", S3_1H),
    "E07": ("S01", "15m", S4_15M), "E08": ("S06", "15m", S5_15M),
}


def _dec(v):
    return None if v is None else Decimal(v)


class TestEvidenceRegistry:
    lib = load_library()

    def test_registry_is_valid_against_the_library(self):
        check_evidence(self.lib, EVIDENCE)
        check_evidence(self.lib, ())
        check_evidence(self.lib, list(EVIDENCE))

    def test_ids_and_numbers_equal_the_lab_document(self):
        assert [r.evidence_id for r in EVIDENCE] == list(DOC_TABLE)
        for r in EVIDENCE:
            sid, tf, rows = DOC_TABLE[r.evidence_id]
            assert (r.strategy_id, r.timeframe) == (sid, tf), r.evidence_id
            assert len(r.periods) == len(rows) == 3
            for got, (period, n, gross, net, t) in zip(r.periods, rows):
                assert got.period == period
                assert got.n == n
                assert got.gross_bp == Decimal(gross) and type(got.gross_bp) is Decimal
                assert got.net_bp == _dec(net)
                assert got.t_stat == _dec(t)
                for v in (got.net_bp, got.t_stat):
                    assert v is None or type(v) is Decimal

    def test_constants_of_the_run(self):
        for r in EVIDENCE:
            assert r.relation == "analog"
            assert r.run_id == "37916437081"
            assert r.source_doc == "claude/laboratorio-strategie-risultati-2026-10-09.md"
            assert "16 bp" in r.cost_scenario
            assert "STRICT" in r.limits and "COND" in r.limits

    def test_evidence_for_mapping(self):
        by = {s.id: tuple(r.evidence_id for r in evidence_for(s.id)) for s in self.lib.strategies}
        assert by["S07"] == ("E01", "E02") and by["S05"] == ("E03", "E04")
        assert by["S21"] == ("E05", "E06") and by["S01"] == ("E07",) and by["S06"] == ("E08",)
        assert all(v == () for k, v in by.items() if k not in {"S01", "S05", "S06", "S07", "S21"})
        assert evidence_for("S99") == ()
        assert evidence_for("S07", ()) == ()
        assert evidence_for("S07", EVIDENCE[:1]) == (EVIDENCE[0],)

    def test_timeframe_outside_the_card_is_declared(self):
        outside = {
            r.evidence_id for r in EVIDENCE
            if r.timeframe not in self.lib.strategy(r.strategy_id).timeframes
        }
        assert outside == {"E02", "E04", "E06"}
        for r in EVIDENCE:
            assert ("NON elencato" in r.differences) == (r.evidence_id in outside), r.evidence_id
            assert len(r.differences) > 40

    def test_registry_text_is_clean(self):
        for r in EVIDENCE:
            for text in (r.lab_variant, r.differences, r.cost_scenario, r.limits, r.source_doc):
                assert lib_mod._is_text(text, 400)

    def test_shared_lab_rows_are_identical_objects_in_value(self):
        by = {r.evidence_id: r for r in EVIDENCE}
        assert by["E03"].periods == by["E05"].periods and by["E04"].periods == by["E06"].periods

    # ---- difetti isolati
    @staticmethod
    def _bad(code, records):
        with pytest.raises(ValueError) as e:
            check_evidence(load_library(), records)
        assert str(e.value) == code

    @staticmethod
    def _rep(i=0, **over):
        return dataclasses.replace(EVIDENCE[i], **over)

    @pytest.mark.parametrize("over", [
        {"evidence_id": "E1"}, {"evidence_id": "E001"}, {"evidence_id": "e01"}, {"evidence_id": "E01\n"},
        {"evidence_id": "E\uff10\uff11"}, {"evidence_id": 1},
        {"strategy_id": "s07"}, {"strategy_id": "S7"}, {"strategy_id": "S07\n"}, {"strategy_id": None},
        {"relation": "direct"}, {"relation": "Analog"}, {"relation": ""}, {"relation": None},
        {"timeframe": "2h"}, {"timeframe": None}, {"timeframe": ["1h"]},
        {"lab_variant": ""}, {"lab_variant": "x" * 121}, {"lab_variant": "a`b"}, {"lab_variant": None},
        {"differences": ""}, {"differences": "x" * 401}, {"differences": "see http://x.io"}, {"differences": 5},
        {"cost_scenario": ""}, {"cost_scenario": "x" * 201}, {"cost_scenario": "a\nb"},
        {"source_doc": ""}, {"source_doc": "x" * 201}, {"source_doc": "<b>"},
        {"run_id": ""}, {"run_id": "abc"}, {"run_id": "12\n"}, {"run_id": "1" * 21}, {"run_id": 37916437081},
        {"run_id": "\uff11\uff12"},
        {"limits": ""}, {"limits": "x" * 401}, {"limits": "a{b"},
        {"periods": ()}, {"periods": []}, {"periods": None},
    ])
    def test_invalid_evidence_fields(self, over):
        for i in (0, len(EVIDENCE) - 1):
            self._bad("invalid_evidence", [self._rep(i, **over)])

    def test_invalid_evidence_periods(self):
        p = EVIDENCE[0].periods
        good = dict(p[0].__dict__)

        def pr(**over):
            return PeriodResult(**{**good, **over})

        bad_period_sets = [
            p + (PeriodResult("dev", 1, Decimal(1), None, None),),                     # 4 periodi
            (p[0], p[0]),                                                              # periodo ripetuto
            (pr(period="oos"),), (pr(period="Dev"),), (pr(period=None),),
            (pr(n=-1),), (pr(n=True),), (pr(n=1.5),), (pr(n="5"),),
            (pr(gross_bp=1.5),), (pr(gross_bp=None),), (pr(gross_bp="1"),), (pr(gross_bp=1),),
            (pr(gross_bp=Decimal("NaN")),), (pr(gross_bp=Decimal("Infinity")),),
            (pr(net_bp=1.5),), (pr(net_bp=Decimal("NaN")),), (pr(net_bp=Decimal("-Infinity")),),
            (pr(t_stat=2.0),), (pr(t_stat=Decimal("NaN")),),
            ["not a tuple"], ("x",), (None,), (EVIDENCE[0],),
        ]
        for periods in bad_period_sets:
            self._bad("invalid_evidence", [self._rep(0, periods=periods)])
        # controlli validi: n 0, net/t assenti, un solo periodo
        for periods in ((pr(n=0),), (pr(net_bp=None, t_stat=None, n=None),), (p[1],)):
            check_evidence(self.lib, [self._rep(0, periods=periods)])

    def test_non_record_items_and_containers(self):
        self._bad("invalid_evidence", [EVIDENCE[0], "E02"])
        self._bad("invalid_evidence", [EVIDENCE[0], None])
        self._bad("invalid_evidence", [EVIDENCE[0], dataclasses.asdict(EVIDENCE[1])])
        self._bad("invalid_evidence", (r for r in EVIDENCE))
        self._bad("invalid_evidence", {EVIDENCE[0]})                      # un insieme non e' una sequenza
        self._bad("invalid_evidence", "E01")
        self._bad("invalid_evidence", None)
        with pytest.raises(ValueError):
            check_evidence(None, EVIDENCE)
        with pytest.raises(ValueError):
            check_evidence(RAW, EVIDENCE)

    def test_record_subclass_is_refused(self):
        class Sub(EvidenceRecord):
            pass
        self._bad("invalid_evidence", [Sub(**EVIDENCE[0].__dict__)])

    def test_duplicate_evidence_id(self):
        self._bad("duplicate_evidence_id", [EVIDENCE[0], self._rep(1, evidence_id="E01")])
        self._bad("duplicate_evidence_id", [EVIDENCE[0], EVIDENCE[0]])

    def test_evidence_unknown_strategy(self):
        self._bad("evidence_unknown_strategy", [self._rep(0, strategy_id="S99")])
        self._bad("evidence_unknown_strategy", [EVIDENCE[0], self._rep(1, strategy_id="S25")])

    def test_stage_order_of_evidence_errors(self):
        both = [self._rep(0, strategy_id="S99"), self._rep(1, evidence_id="E01")]
        self._bad("duplicate_evidence_id", both)
        worse = [self._rep(0, strategy_id="S99", evidence_id="E01"), self._rep(1, relation="direct")]
        self._bad("invalid_evidence", worse)
        self._bad("invalid_evidence", [self._rep(0, evidence_id="E01"), self._rep(1, evidence_id="E01", run_id="x")])


# ======================================================================= rapporto
def _expected_rows(lib: Library) -> list[str]:
    ev_count = {sid: sum(1 for t in DOC_TABLE.values() if t[0] == sid) for sid in
                {t[0] for t in DOC_TABLE.values()}}
    outside = {sid: sum(1 for t in DOC_TABLE.values()
                        if t[0] == sid and t[1] not in next(
                            r for r in RAW["strategies"] if r["id"] == sid)["timeframes"])
               for sid in ev_count}
    rows = []
    for raw in RAW["strategies"]:
        sid = raw["id"]
        gaps = ",".join(GAPS_C.get(sid, ())) or "-"
        if sid in ev_count:
            note = f"{ev_count[sid]} analog" + (
                f" ({outside[sid]} con timeframe fuori scheda)" if outside[sid] else "")
        else:
            note = "-"
        rows.append(" | ".join([sid, raw["family"], raw["research_priority"], raw["rule_origin"],
                                EXPECTED_CLASS[sid], gaps, note]))
    return rows


class TestReport:
    lib = load_library()

    def test_full_report_built_independently(self):
        want = "\n".join([
            "Biblioteca strategica v1.0.0 (2026-11-04): 24 schede, 30 fonti, tutte research_only",
            "Dati: candles=12, candles_funding_oi=2, needs_new_data=10",
            "id | famiglia | priorita | origine | dati | lacune | prove",
            *_expected_rows(self.lib),
        ]) + "\n"
        assert format_library(self.lib) == want

    def test_format_properties(self):
        text = format_library(self.lib)
        assert text.endswith("\n") and not text.endswith("\n\n")
        lines = text.splitlines()
        assert len(lines) == 3 + 24
        assert all(line == line.rstrip() for line in lines)
        assert all(line.count(" | ") == 6 for line in lines[2:])

    def test_report_without_evidence(self):
        text = format_library(self.lib, ())
        assert all(line.endswith(" | -") for line in text.splitlines()[3:])
        assert "analog" not in text

    def test_report_refuses_a_bad_registry(self):
        bad = [dataclasses.replace(EVIDENCE[0], strategy_id="S99")]
        with pytest.raises(ValueError) as e:
            format_library(self.lib, bad)
        assert str(e.value) == "evidence_unknown_strategy"

    def test_unknown_strategy_lookup(self):
        with pytest.raises(ValueError) as e:
            self.lib.strategy("S99")
        assert str(e.value) == "unknown_strategy"
        assert self.lib.strategy("S05") is self.lib.strategies[4]


# ======================================================================= immutabilita' e purezza
class TestImmutabilityAndPurity:
    lib = load_library()

    def test_frozen_dataclasses(self):
        targets = [
            (self.lib, "version"), (self.lib.strategies[0], "name"), (self.lib.sources[0], "url"),
            (EVIDENCE[0], "run_id"), (EVIDENCE[0].periods[0], "n"),
        ]
        for obj, attr in targets:
            with pytest.raises(dataclasses.FrozenInstanceError):
                setattr(obj, attr, "x")

    def test_collections_are_tuples(self):
        assert type(self.lib.strategies) is tuple and type(self.lib.sources) is tuple
        for s in self.lib.strategies:
            for f in ("candidate_regimes", "timeframes", "required_features", "sources"):
                assert type(getattr(s, f)) is tuple, (s.id, f)
        for r in EVIDENCE:
            assert type(r.periods) is tuple
        assert type(EVIDENCE) is tuple

    def test_module_source_is_pure(self):
        src = Path(lib_mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module)
        assert imported == {
            "__future__", "datetime", "hashlib", "json", "re", "collections.abc", "dataclasses",
            "decimal", "pathlib", "typing"}
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        assert not names & {"float", "eval", "exec", "compile", "__import__", "open", "input", "print",
                            "globals", "locals", "vars", "getattr", "setattr"}
        assert not attrs & {"now", "today", "utcnow", "urlopen", "system", "popen", "run", "call",
                            "random", "time", "environ", "getenv", "read_text", "write_text",
                            "write_bytes", "open", "unlink", "mkdir"}
        reads = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "read_bytes"]
        assert len(reads) == 1                                       # legge soltanto il proprio file
        withs = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "with_name"]
        assert len(withs) == 1
        floats = [n for n in ast.walk(tree) if isinstance(n, ast.Constant) and type(n.value) is float]
        assert floats == []

    def test_no_import_side_effects_on_environment(self):
        before = dict(os.environ)
        import importlib
        importlib.reload(lib_mod)
        assert dict(os.environ) == before
        assert lib_mod.KB_SHA256 == PINNED_SHA

    def test_package_does_not_touch_the_brain(self):
        """L0 e' solo dati: nessun import da brain_f2/brain_f3/executor/events nel pacchetto knowledge."""
        for path in KB_PATH.parent.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                for m in mods:
                    assert not m.startswith("backend"), (path.name, m)
