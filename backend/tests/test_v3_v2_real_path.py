"""Validazione della V2 sul PERCORSO REALE (25/11/2026): ``build_runner`` con la configurazione consegnata, motore,
consulto di Claude, arbitro, controllo finale, commit dell'apertura, esecutore PAPER, monitor delle uscite, journal.

Si fingono solo i confini: Bitget (stesso formato di risposta), DeepSeek e Claude (stesso formato delle API). Verifica:
veto di Claude invariato; una sola apertura iniziale (nessuna quota); fotografia V2 sulla posizione; cambio V2 -> V3
con la posizione aperta e regole precedenti preservate; stop protetto con la diagnostica dell'uscita; la nuova
apertura nasce con la V3. Secondo ingresso, memoria della nuova sessione e rollback senza Falco Evoluto sono coperti
da ``test_v3_single_position_scaling`` e ``deploy/brain-unico-2000/test_ripartenza.py``."""
from __future__ import annotations

import json
import tempfile
from decimal import Decimal as D
from pathlib import Path

from backend.tests.test_v3_runner_e2e import G, M, RUN, VIEW, _get_json_factory
from backend.v3 import strategy_versions as sv
from backend.v3.brain_f3.providers import TransportResponse
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.wiring import _strategy_of, build_runner, mandate_template

CFG = Path(__file__).resolve().parents[1] / "v3" / "runner" / "runner_config_brain_unico_2000_paper.json"


def _base() -> bytes:
    """La configurazione V2 consegnata, ridotta al mercato finto e al ritmo dei test (15', senza ragionamento)."""
    c = json.loads(CFG.read_bytes())
    c.update(symbols=["BTCUSDT"], cycle_minutes=15, thinking="disabled", reasoning_effort="omit", max_tokens=256)
    return json.dumps(c, indent=2).encode()


class DeepSeek:
    """SHORT con stop all'1 %, confidenza 0,62 e incertezza dichiarata (come quasi tutte le proposte del 24/11)."""

    def __init__(self):
        self.calls = 0

    def __call__(self, payload):
        self.calls += 1
        info = json.loads(payload["messages"][1]["content"])
        if "price" not in info:                       # revisione di una posizione: tenere
            return TransportResponse(200, {"choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps({"action": "HOLD", "confidence": 0.6})}}], "usage": {"prompt_tokens": 10,
                                                                                           "completion_tokens": 5}})
        price = D(info["price"])
        content = json.dumps({"kind": "OPEN", "side": -1, "entry_price": str(price), "stop_price": str(price * D("1.01")),
                              "leverage": 20, "confidence": 0.62, "strategy_id": "S25", "strategy_origin": "library",
                              "reasons": ["trend_down", "breakdown"], "uncertain": True})
        return TransportResponse(200, {"choices": [{"finish_reason": "stop", "message": {"content": content}}],
                                       "usage": {"prompt_tokens": 2500, "completion_tokens": 60}})


class Claude:
    def __init__(self, verdict="CONTEST"):
        self.verdict, self.calls = verdict, 0

    def __call__(self, payload):
        self.calls += 1
        text = json.dumps({"verdict": self.verdict, "confidence": 0.7, "reasons": ["setup_weak"]})
        return TransportResponse(200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": text}],
                                       "usage": {"input_tokens": 1000, "output_tokens": 40}})


CLOCK = {"t": G}


def _tick(built, t):
    CLOCK["t"] = t                                  # orologio fresco del runner = istante del tick (piu' 1 s)
    return built.runner.tick(t)


def _build(data_dir, base, ds, cl):
    cfg = load_runner_config(base)
    return build_runner(data_dir=data_dir, run_id=RUN, config=cfg, get_json=_get_json_factory(), inner_transport=ds,
                        claude_inner_transport=cl, view_params=VIEW, strategy=_strategy_of(data_dir, RUN, base),
                        clock_ms=lambda: CLOCK["t"] + 1_000)


def _kinds(built, kind):
    return [r.event for r in built.journal.list_run("brain", RUN) if r.event.kind == kind]


def test_v2_on_the_real_open_and_exit_path():
    base = _base()
    data_dir = Path(tempfile.mkdtemp())
    from backend.v3.events import EventJournal
    EventJournal(str(data_dir / "journal.db")).init_schema()          # run preparata: il journal esiste gia'
    ds, cl = DeepSeek(), Claude("CONTEST")
    built = _build(data_dir, base, ds, cl)
    cfg = load_runner_config(base)
    m = mandate_template(cfg.risk_policy, RUN)
    m.update(approved=True, approved_by="operator")
    (data_dir / "mandate.json").write_text(json.dumps(m))
    (data_dir / "runner_config.json").write_bytes(base)

    # 1. veto di Claude invariato: contestazione -> nessuna apertura
    _tick(built, G + 20_000)
    assert cl.calls == 1 and _kinds(built, "paper_open") == []
    assert [e.payload["code"] for e in _kinds(built, "ai_consultation")] == ["claude_contested"]

    # 2. conferma -> UNA sola apertura (nessuna quota), con la fotografia della V2
    cl.verdict = "CONFIRM"
    _tick(built, G + 15 * M + 20_000)
    [op] = _kinds(built, "paper_open")
    p = op.payload
    assert "leg" not in p and p["strategy"]["version"] == "V2"
    assert p["strategy"]["entry_policy"]["min_confidence"] == "0.56"
    assert p["strategy"]["entry_policy"]["consult_limit_fallback"] == "veto"
    assert D(p["stop_price"]) > D(p["fill_price"])                       # SHORT: stop sopra, gia' protetto

    # 3. cambio V2 -> V3 con la posizione aperta: le sue regole restano quelle della V2
    prop = sv.propose("Take profit finale a 2 R", sv.read_registry(built.journal, RUN, base), base, G + 16 * M)
    sv.save_proposal(data_dir, prop)
    sv.approve(data_dir, prop.id, "operatore", "prova V3", G + 16 * M)
    res = sv.apply_request(journal=built.journal, data_dir=data_dir, run_id=RUN, base_bytes=base, now_ms=G + 16 * M)
    assert res["ok"] and (res["from"], res["to"]) == ("V2", "V3")
    from backend.v3.dashboard import build_summary
    [pos] = build_summary(built.journal, "brain", RUN).open_positions
    assert pos.strategy_version == "V2" and pos.exit_snapshot.take_profit_r == D("3.5")

    # 4. stop protetto: il picco del minuto 17 tocca lo stop; chiusura con la candela che l'ha attivata
    _tick(built, G + 18 * M + 5_000)
    [close] = _kinds(built, "paper_close")
    assert close.payload["reason"] == "stop" and close.payload["exit_meta"]["signal_bar_ms"] == G + 17 * M
    assert close.payload["exit_meta"]["late"] is False and not _kinds(built, "exit_late")

    # 5. runner ricostruito con la versione attiva: la nuova apertura nasce con la V3
    built3 = _build(data_dir, base, ds, Claude("CONFIRM"))
    built3.runner._last_slot = (G + 15 * M) // built3.runner._cycle_ms
    _tick(built3, G + 30 * M + 20_000)
    opens = _kinds(built3, "paper_open")
    assert len(opens) == 2 and opens[-1].payload["strategy"]["version"] == "V3"
    assert opens[-1].payload["strategy"]["exit_policy"]["take_profit_r"] == "2"
    assert opens[0].payload["strategy"]["version"] == "V2"                # la storia non si riscrive
    built3.journal.verify_chain()
