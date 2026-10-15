"""Calendario macro: lettura delle fonti, regime, finestre di blocco, integrazione nel ciclo del bot."""
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["DESK_MACRO_FETCH"] = "0"   # come conftest.py: mai rete vera nei test

import test_desk as td  # noqa: E402   (riuso del mondo di candele, dello sandbox e dello stub di Claude)
from desk import cli, learning, macro_calendar as mc  # noqa: E402

NOW = td.NOW

MIN, HOUR = 60_000, 3_600_000


def _utc_ms(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def _ev(ts, impact="High", title="CPI m/m", src="ff"):
    return {"ts": ts, "title": title, "country": "USD", "impact": impact, "src": src}


# ---------------------------------------------------------------- ora legale e lettura delle fonti
def test_us_eastern_offset_follows_dst_rules():
    assert mc.us_eastern_offset_h(date(2026, 3, 7)) == -5     # prima del 2a domenica di marzo (8 marzo)
    assert mc.us_eastern_offset_h(date(2026, 3, 8)) == -4
    assert mc.us_eastern_offset_h(date(2026, 10, 31)) == -4
    assert mc.us_eastern_offset_h(date(2026, 11, 1)) == -5    # 1a domenica di novembre


def test_parse_ff_keeps_only_usd_high_and_medium_with_a_timezone():
    raw = json.dumps([
        {"title": "CPI m/m", "country": "USD", "date": "2026-10-14T08:30:00-04:00", "impact": "High"},
        {"title": "Unemployment Claims", "country": "USD", "date": "2026-10-15T08:30:00-04:00", "impact": "Medium"},
        {"title": "Low thing", "country": "USD", "date": "2026-10-15T09:00:00-04:00", "impact": "Low"},
        {"title": "BOJ", "country": "JPY", "date": "2026-10-15T03:00:00-04:00", "impact": "High"},
        {"title": "senza fuso", "country": "USD", "date": "2026-10-15T09:00:00", "impact": "High"},
        {"title": "rotto", "country": "USD", "impact": "High"},
        "non un oggetto",
    ]).encode()
    out = mc.parse_ff(raw)
    assert [(e["title"], e["impact"]) for e in out] == [("CPI m/m", "High"), ("Unemployment Claims", "Medium")]
    assert out[0]["ts"] == _utc_ms(2026, 10, 14, 12, 30)      # 08:30 a New York (ora legale) = 12:30 UTC


def test_parse_bls_ics_converts_new_york_time_and_keeps_only_key_releases():
    ics = ("BEGIN:VCALENDAR\r\n"
           "BEGIN:VEVENT\r\nSUMMARY:Consumer Price Index\r\nDTSTART;TZID=US-Eastern:20261015T083000\r\nEND:VEVENT\r\n"
           "BEGIN:VEVENT\r\nSUMMARY:Employment Situation\r\nDTSTART;TZID=US-Eastern:20261106T083000\r\nEND:VEVENT\r\n"
           "BEGIN:VEVENT\r\nSUMMARY:Import and Export Price Indexes\r\nDTSTART;TZID=US-Eastern:20261016T083000\r\nEND:VEVENT\r\n"
           "BEGIN:VEVENT\r\nSUMMARY:Producer Price Index\r\nDTSTART;VALUE=DATE:20261017\r\nEND:VEVENT\r\n"
           "END:VCALENDAR\r\n")
    out = mc.parse_bls_ics(ics, _utc_ms(2026, 10, 15, 0, 0))
    assert [(e["title"], e["ts"]) for e in out] == [
        ("CPI (BLS)", _utc_ms(2026, 10, 15, 12, 30)),              # ora legale: 08:30 = 12:30 UTC
        ("Occupazione/NFP (BLS)", _utc_ms(2026, 11, 6, 13, 30))]   # dopo il 1 novembre: 08:30 = 13:30 UTC
    assert all(e["impact"] == "High" and e["src"] == "bls" for e in out)


# ---------------------------------------------------------------- regime e finestre
def test_blackout_window_boundaries_and_regime_by_time():
    t = _utc_ms(2026, 10, 15, 12, 30)
    evs = [_ev(t)]
    at = lambda delta_min: mc.evaluate(evs, t + delta_min * MIN)
    assert at(-13 * 60)["regime"] == "calmo"                     # oltre le 12 ore di anticipo
    assert at(-11 * 60)["regime"] == "alto" and not at(-11 * 60)["blackout"]
    assert at(-61)["blackout"] is False and at(-61)["regime"] == "alto"
    assert at(-60)["blackout"] is True                            # da 60 minuti prima (incluso)
    assert at(119)["blackout"] is True
    assert at(120)["blackout"] is False and at(120)["regime"] == "alto"   # fine blocco (escluso), ancora regime alto
    assert at(181)["regime"] == "calmo"                           # oltre le 3 ore dopo
    assert at(-60)["blackout_until_ms"] == t + 120 * MIN
    assert at(-30)["conf_bonus"] == mc.CFG.conf_bonus_alto == 5 and at(-13 * 60)["conf_bonus"] == 0


def test_medium_only_day_is_informational_and_next_event_is_reported():
    t = _utc_ms(2026, 10, 15, 12, 30)
    m = mc.evaluate([_ev(t, "Medium", "Claims")], t - 2 * HOUR)
    assert m["regime"] == "medio" and m["conf_bonus"] == 0 and m["blackout"] is False
    h = mc.evaluate([_ev(t), _ev(t + 5 * HOUR, title="Warsh")], t - 30 * MIN)
    assert h["next"]["title"] == "CPI m/m" and h["next"]["min"] == 30
    assert [u["title"] for u in h["upcoming"]] == ["CPI m/m", "Warsh"]
    after = mc.evaluate([_ev(t)], t + 20 * MIN)
    assert after["next"] is None and after["recent"][0]["min"] == -20


# ---------------------------------------------------------------- cache, rete, interruttori
def _fetcher(calls, ff=None, ics="", fail=False):
    def fetch(url, timeout):
        calls.append(url)
        if fail:
            raise OSError("rete assente")
        if "faireconomy" in url:
            return json.dumps(ff if ff is not None else []).encode()
        return ics.encode()
    return fetch


def test_refresh_caches_and_does_not_hammer_after_a_failure():
    ff = [{"title": "CPI m/m", "country": "USD", "date": "2026-10-15T08:30:00-04:00", "impact": "High"}]
    os.environ["DESK_MACRO_FETCH"] = "1"
    try:
        with tempfile.TemporaryDirectory() as d:
            calls = []
            t0 = _utc_ms(2026, 10, 15, 6, 0)
            c = mc.refresh_if_due(d, t0, _fetcher(calls, ff))
            assert len(calls) == 2 and len(c["ff"]["events"]) == 1             # primo giro: feed + BLS
            mc.refresh_if_due(d, t0 + HOUR, _fetcher(calls, ff))
            assert len(calls) == 2                                              # ancora in cache
            mc.refresh_if_due(d, t0 + 3 * HOUR + MIN, _fetcher(calls, ff))
            assert len(calls) == 3 and "faireconomy" in calls[-1]               # solo il feed (BLS: una volta al giorno)
            # errore: si tiene il vecchio, si segna l'errore, si riprova solo dopo 15 minuti
            t1 = t0 + 7 * HOUR
            bad = []
            c = mc.refresh_if_due(d, t1, _fetcher(bad, fail=True))
            assert len(bad) == 1 and len(c["ff"]["events"]) == 1 and "OSError" in c["ff"]["error"]
            mc.refresh_if_due(d, t1 + 5 * MIN, _fetcher(bad, fail=True))
            assert len(bad) == 1                                                # niente raffica
            mc.refresh_if_due(d, t1 + 16 * MIN, _fetcher(bad, fail=True))
            assert len(bad) == 2
            assert mc.current(d, t1 + 17 * MIN, _fetcher([], fail=True))["n_events"] == 1   # usa ancora la cache
    finally:
        os.environ["DESK_MACRO_FETCH"] = "0"


def test_current_is_neutral_without_data_and_never_raises():
    os.environ["DESK_MACRO_FETCH"] = "1"
    try:
        with tempfile.TemporaryDirectory() as d:
            m = mc.current(d, NOW, _fetcher([], fail=True))
            assert m["regime"] == "nd" and m["blackout"] is False and m["conf_bonus"] == 0 and m["error"]
            assert mc.prompt_lines(m) == [] and mc.features(m)["macro_blackout"] is False
        with tempfile.TemporaryDirectory() as d:                      # fonte che lancia un errore non previsto
            def boom(url, timeout):
                raise RuntimeError("inatteso")
            assert mc.current(d, NOW, boom)["regime"] == "nd"
        with tempfile.NamedTemporaryFile() as f:                      # cartella dati impossibile da creare/leggere
            assert mc.current(os.path.join(f.name, "sotto"), NOW, _fetcher([], fail=True))["regime"] == "nd"
        with tempfile.TemporaryDirectory() as d:                      # cache corrotta
            open(os.path.join(d, mc.CACHE_FILE), "w").write("{non json")
            assert mc.current(d, NOW)["regime"] == "nd"
    finally:
        os.environ["DESK_MACRO_FETCH"] = "0"


def test_current_swallows_an_internal_error_in_the_evaluation():
    saved = mc.evaluate
    try:
        with tempfile.TemporaryDirectory() as d:
            _write_cache(d, [_ev(NOW + 10 * MIN)])
            mc.evaluate = lambda *a, **k: (_ for _ in ()).throw(ZeroDivisionError("bug"))
            m = mc.current(d, NOW)
            assert m["regime"] == "nd" and m["blackout"] is False and "ZeroDivisionError" in m["error"]
    finally:
        mc.evaluate = saved


def test_kill_switches_turn_the_filter_off():
    with tempfile.TemporaryDirectory() as d:
        t = _utc_ms(2026, 10, 15, 12, 30)
        with open(os.path.join(d, mc.CACHE_FILE), "w") as fh:
            json.dump({"ff": {"ts": t, "next_try_ms": t + 10**12, "events": [_ev(t)], "error": ""}}, fh)
        assert mc.current(d, t)["blackout"] is True
        open(os.path.join(d, mc.OFF_FLAG), "w").write("1")
        off = mc.current(d, t)
        assert off["regime"] == "off" and off["blackout"] is False and off["conf_bonus"] == 0
        os.remove(os.path.join(d, mc.OFF_FLAG))
        os.environ["DESK_MACRO"] = "0"
        try:
            assert mc.current(d, t)["regime"] == "off"
        finally:
            del os.environ["DESK_MACRO"]


def test_prompt_lines_only_when_there_is_something_to_say():
    t = _utc_ms(2026, 10, 15, 12, 30)
    assert mc.prompt_lines(mc.evaluate([], t)) == []
    assert mc.prompt_lines(mc.evaluate([_ev(t + 30 * HOUR)], t)) == []      # evento oltre 24 ore: nessuna riga
    lines = "\n".join(mc.prompt_lines(mc.evaluate([_ev(t)], t - 30 * MIN)))
    assert "CALENDARIO MACRO" in lines and "ALTO" in lines and "CPI m/m" in lines and "12:30 UTC" in lines
    assert "ORA ATTIVO fino alle 14:30 UTC" in lines and "+5" in lines
    assert "Usciti da poco" in "\n".join(mc.prompt_lines(mc.evaluate([_ev(t)], t + 20 * MIN)))


# ---------------------------------------------------------------- dentro il ciclo del bot
def _write_cache(d, events, ts=None):
    ts = ts or NOW
    src = {"ts": ts, "next_try_ms": ts + 10**12, "events": events, "error": ""}
    with open(os.path.join(d, mc.CACHE_FILE), "w") as fh:
        json.dump({"ff": src, "bls": {**src, "events": []}}, fh)


def _recording(stub, prompts):
    """Avvolge lo stub di Claude registrando il prompt che riceve."""
    def call(system, user, max_tokens=1100, timeout=60):
        prompts.append(user)
        return stub(system, user, max_tokens, timeout)
    return call


def _swap_claude(stub):
    import desk.brain as _brain
    import desk.cli as _c
    _brain.call_claude = _c.call_claude = stub


def _cycle(state, now_ms):
    state["last_call_ms"] = 0
    state["last_open_ms"] = {}
    cli.run_cycle(state, now_ms)
    return cli.make_account(state)


def test_cycle_blackout_blocks_new_opening_and_logs_a_candidate():
    prompts = []
    stub = _recording(td._decisions_stub(td._dec("BTC", "open_long")), prompts)
    with td._sandbox(stub) as (d, calls):
        _write_cache(d, [_ev(NOW + 10 * MIN)])                       # CPI tra 10 minuti: blocco attivo
        state = {}
        acc = _cycle(state, NOW)
        assert "BTC" not in acc.positions, "nessuna NUOVA apertura durante il blocco"
        cands = learning.read_events(d, "candidate")
        assert cands and all(c["status"] == "macro_blocco" for c in cands)
        f = cands[0]["features"]
        assert f["macro_regime"] == "alto" and f["macro_blackout"] is True and f["macro_bonus"] == 5
        assert f["macro_min_next"] == 10
        assert any("CALENDARIO MACRO" in p and "ORA ATTIVO" in p for p in prompts), "Claude deve saperlo"
        assert cli.HB["macro"]["blackout"] is True and cli.HB["macro"]["regime"] == "alto"


def test_cycle_after_the_blackout_window_it_opens_again():
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long"))) as (d, calls):
        _write_cache(d, [_ev(NOW + 10 * MIN)])
        state = {}
        assert "BTC" not in _cycle(state, NOW).positions
        acc = _cycle(state, NOW + 10 * MIN + 125 * MIN)              # 125 minuti dopo l'evento: blocco finito
        assert "BTC" in acc.positions


def test_cycle_without_nearby_events_is_unchanged_and_prompt_has_no_macro_lines():
    prompts = []
    stub = _recording(td._decisions_stub(td._dec("BTC", "open_long")), prompts)
    with td._sandbox(stub) as (d, calls):
        _write_cache(d, [_ev(NOW + 72 * HOUR)])                      # evento tra 3 giorni: calmo
        acc = _cycle({}, NOW)
        assert "BTC" in acc.positions
        assert not any("CALENDARIO MACRO" in p for p in prompts)
        op = learning.read_events(d, "open")[0]["features"]
        assert op["macro_regime"] == "calmo" and op["macro_blackout"] is False and op["macro_bonus"] == 0


def test_cycle_when_calendar_is_unavailable_the_bot_works_as_before():
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long"))) as (d, calls):   # nessuna cache, rete spenta
        acc = _cycle({}, NOW)
        assert "BTC" in acc.positions
        assert cli.HB["macro"]["regime"] == "nd" and cli.HB["macro"]["blackout"] is False
        assert learning.read_events(d, "open")[0]["features"]["macro_regime"] == "nd"


def test_cycle_high_regime_raises_required_confidence_by_five():
    event = [_ev(NOW + 8 * HOUR)]                                    # nelle prossime 12 ore ma fuori dal blocco
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long", confidence=62))) as (d, calls):
        _write_cache(d, event)                                       # BTC richiede 60: 62 passa di solito, con +5 no
        assert "BTC" not in _cycle({}, NOW).positions
        assert {c["status"] for c in learning.read_events(d, "candidate")} == {"conf_bassa_macro"}
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long", confidence=66))) as (d, calls):
        _write_cache(d, event)                                       # 66 >= 65: apre, e il registro dice in che regime
        assert "BTC" in _cycle({}, NOW).positions
        assert learning.read_events(d, "open")[0]["features"]["macro_regime"] == "alto"
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long", confidence=62))) as (d, calls):
        assert "BTC" in _cycle({}, NOW).positions                    # senza evento: 62 passa, nessun cambiamento


def test_cycle_low_confidence_in_high_regime_keeps_the_old_status():
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long", confidence=55))) as (d, calls):
        _write_cache(d, [_ev(NOW + 8 * HOUR)])
        assert "BTC" not in _cycle({}, NOW).positions
        assert {c["status"] for c in learning.read_events(d, "candidate")} == {"conf_bassa"}   # sotto soglia anche senza macro


def test_cycle_blackout_does_not_touch_open_positions():
    """Il filtro riguarda solo le NUOVE aperture: una chiusura decisa durante il blocco viene eseguita."""
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long"))) as (d, calls):
        _write_cache(d, [_ev(NOW + HOUR + 10 * MIN)])                # primo ciclo: evento tra 70 min (nessun blocco)
        state = {}
        assert "BTC" in _cycle(state, NOW).positions
        _swap_claude(td._decisions_stub(td._dec("BTC", "close", reason="segnale girato")))
        acc = _cycle(state, NOW + HOUR)                              # secondo ciclo: evento tra 10 min = blocco attivo
        assert cli.HB["macro"]["blackout"] is True
        assert "BTC" not in acc.positions and len(acc.closed) == 1


def test_cycle_blackout_does_not_block_dca_on_an_open_position():
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long"))) as (d, calls):
        _write_cache(d, [_ev(NOW + HOUR + 10 * MIN)])
        state = {}
        assert "BTC" in _cycle(state, NOW).positions
        _swap_claude(td._decisions_stub(td._dec("BTC", "dca")))
        acc = _cycle(state, NOW + HOUR)
        assert cli.HB["macro"]["blackout"] is True
        assert "BTC" in acc.positions                                # il filtro non interviene sulle posizioni aperte


def test_cycle_off_switch_ignores_the_calendar_without_restart():
    with td._sandbox(td._decisions_stub(td._dec("BTC", "open_long"))) as (d, calls):
        _write_cache(d, [_ev(NOW + 10 * MIN)])
        open(os.path.join(d, mc.OFF_FLAG), "w").close()
        acc = _cycle({}, NOW)
        assert "BTC" in acc.positions and cli.HB["macro"]["regime"] == "off"


def test_cycle_rules_only_path_is_also_blocked_by_the_calendar():
    """Senza Claude (solo regole) il blocco vale lo stesso: e' nel codice che esegue, non nel prompt."""
    with td._sandbox(None) as (d, calls):
        state = {}
        calm = set(_cycle(state, NOW).positions)
    with td._sandbox(None) as (d, calls):
        _write_cache(d, [_ev(NOW + 10 * MIN)])
        blocked = set(_cycle({}, NOW).positions)
        assert not blocked
        if calm:
            assert any(c["status"] == "macro_blocco" for c in learning.read_events(d, "candidate"))
