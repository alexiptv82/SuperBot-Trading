"""Orari di trading: spenti di default, solo restringono (come la Pausa), le posizioni aperte si chiudono da sole."""
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["DESK_MACRO_FETCH"] = "0"

import test_desk as td  # noqa: E402   (mondo di candele, sandbox, stub di Claude, orologio congelato)
from desk import cli, learning, trading_hours as th  # noqa: E402

NOW = td.NOW      # 2027-01-15 08:00:20 UTC = venerdi, ora italiana 09:00:20 (CET)


def _utc(y, mo, d, h=0, mi=0):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def _write(d, obj):
    with open(os.path.join(d, th.HOURS_FILE), "w") as fh:
        json.dump(obj, fh) if not isinstance(obj, str) else fh.write(obj)


def _hours(windows, enabled=True, tz="Europe/Rome"):
    return {"enabled": enabled, "tz": tz, "windows": windows}


def _st(obj, now_ms):
    with tempfile.TemporaryDirectory() as d:
        _write(d, obj)
        return th.hours_state(d, now_ms)


# ---------------------------------------------------------------- ora legale e controllo del file
def test_the_fixture_clock_is_what_the_tests_assume():
    t = datetime.fromtimestamp(NOW / 1000, tz=timezone.utc)
    assert (t.weekday(), t.hour, t.minute) == (4, 8, 0)


def test_rome_offset_follows_eu_dst_rules():
    at = lambda *a: th.rome_offset_min(datetime(*a, tzinfo=timezone.utc))
    assert at(2026, 3, 29, 0, 59) == 60 and at(2026, 3, 29, 1, 0) == 120      # ultima domenica di marzo, 01:00 UTC
    assert at(2026, 10, 25, 0, 59) == 120 and at(2026, 10, 25, 1, 0) == 60    # ultima domenica di ottobre, 01:00 UTC
    assert at(2026, 10, 15) == 120 and at(2027, 1, 15) == 60 and at(2027, 7, 1) == 120


def test_parse_accepts_a_good_file_and_defaults_to_all_days():
    cfg, err = th.parse(_hours([{"start": "08:00", "end": "22:30"}, {"days": [5, 6, 5], "start": "22:00", "end": "02:00"}]))
    assert err == "" and cfg["enabled"] and cfg["tz"] == "Europe/Rome"
    assert cfg["windows"][0]["days"] == [0, 1, 2, 3, 4, 5, 6] and cfg["windows"][0]["end"] == 22 * 60 + 30
    assert cfg["windows"][1]["days"] == [5, 6]
    assert th.parse(_hours([{"start": "00:00", "end": "24:00"}]))[1] == ""


def test_parse_rejects_bad_files_with_a_readable_reason():
    bad = {
        "no windows": _hours([]),
        "bad tz": _hours([{"start": "08:00", "end": "09:00"}], tz="Mars/Base"),
        "same start/end": _hours([{"start": "08:00", "end": "08:00"}]),
        "bad hm": _hours([{"start": "8:00", "end": "09:00"}]),
        "bad hour": _hours([{"start": "25:00", "end": "09:00"}]),
        "24:00 as start": _hours([{"start": "24:00", "end": "09:00"}]),
        "bad days": _hours([{"days": [7], "start": "08:00", "end": "09:00"}]),
        "bool days": _hours([{"days": [True], "start": "08:00", "end": "09:00"}]),
        "empty days": _hours([{"days": [], "start": "08:00", "end": "09:00"}]),
        "window not object": _hours(["08:00-09:00"]),
        "too many": _hours([{"start": "08:00", "end": "09:00"}] * (th.MAX_WINDOWS + 1)),
    }
    for name, obj in bad.items():
        cfg, err = th.parse(obj)
        assert cfg is None and err, name
    assert th.parse([1, 2])[1], "un file che non e' un oggetto"
    assert th.parse({"enabled": False, "windows": "rotto"}) == ({"enabled": False, "tz": "Europe/Rome", "windows": []}, "")


# ---------------------------------------------------------------- cosa e' permesso, e quando cambia
def test_default_is_off_and_never_blocks():
    with tempfile.TemporaryDirectory() as d:
        s = th.hours_state(d, NOW)                                   # nessun file
        assert s["mode"] == "off" and s["allowed"] and not s["blocked"] and s["error"] == ""
    s = _st(_hours([{"start": "20:00", "end": "21:00"}], enabled=False), NOW)   # file presente ma spento
    assert s["mode"] == "off" and not s["blocked"]
    assert not _st({"windows": [{"start": "20:00", "end": "21:00"}]}, NOW)["blocked"], "senza enabled=true resta spento"


def test_weekday_window_in_italian_time_with_dst():
    obj = _hours([{"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "22:00"}])
    thu = lambda h, m=0: _utc(2026, 10, 15, h, m)                    # giovedi, CEST (UTC+2)
    assert _st(obj, thu(5, 59))["blocked"] and not _st(obj, thu(6, 0))["blocked"]      # 08:00 italiane = 06:00 UTC
    assert not _st(obj, thu(19, 59))["blocked"] and _st(obj, thu(20, 0))["blocked"]    # 22:00 italiane = 20:00 UTC
    assert _st(obj, _utc(2026, 10, 17, 12))["blocked"]               # sabato
    jan = _st(obj, _utc(2027, 1, 14, 7, 0))                          # giovedi in ora solare (UTC+1): 08:00 = 07:00 UTC
    assert jan["allowed"] and jan["mode"] == "on" and jan["tz"] == "Europe/Rome"
    assert _st(obj, _utc(2027, 1, 14, 6, 59))["blocked"]


def test_next_change_points_to_the_next_start_or_end():
    obj = _hours([{"days": [0, 1, 2, 3, 4], "start": "08:00", "end": "22:00"}])
    sat = _st(obj, _utc(2026, 10, 17, 12))
    assert sat["blocked"] and sat["next_change_ms"] == _utc(2026, 10, 19, 6, 0)       # lunedi 08:00 italiane
    thu = _st(obj, _utc(2026, 10, 15, 12))
    assert thu["allowed"] and thu["next_change_ms"] == _utc(2026, 10, 15, 20, 0)      # oggi alle 22:00 italiane
    fri_night = _st(obj, _utc(2026, 10, 16, 19, 0))
    assert fri_night["next_change_ms"] == _utc(2026, 10, 16, 20, 0)


def test_window_crossing_midnight_belongs_to_the_day_it_starts():
    obj = _hours([{"days": [4], "start": "22:00", "end": "02:00"}])    # solo la sera del venerdi, fino alle 02:00
    assert _st(obj, _utc(2026, 10, 16, 20, 30))["allowed"]            # venerdi 22:30 italiane
    assert _st(obj, _utc(2026, 10, 16, 22, 30))["allowed"]            # sabato 00:30 italiane (continua)
    assert _st(obj, _utc(2026, 10, 17, 0, 30))["blocked"]             # sabato 02:30 italiane (finita)
    assert _st(obj, _utc(2026, 10, 17, 20, 30))["blocked"]            # sabato sera: non e' venerdi
    assert _st(obj, _utc(2026, 10, 17, 22, 30))["blocked"]            # domenica 00:30 italiane: la fascia del sabato non c'e'
    assert _st(obj, _utc(2026, 10, 14, 22, 30))["blocked"]            # giovedi 00:30 italiane: la fascia del mercoledi non c'e'


def test_all_day_utc_and_adjacent_windows():
    assert _st(_hours([{"start": "00:00", "end": "24:00"}]), NOW)["allowed"]
    assert _st(_hours([{"start": "00:00", "end": "24:00"}]), NOW)["next_change_ms"] is None
    utc = _hours([{"start": "08:00", "end": "09:00"}], tz="UTC")
    assert _st(utc, NOW)["allowed"] and _st(utc, _utc(2027, 1, 15, 9, 0))["blocked"]
    adj = _hours([{"start": "08:00", "end": "12:00"}, {"start": "12:00", "end": "16:00"}], tz="UTC")
    s = _st(adj, _utc(2027, 1, 15, 10, 0))
    assert s["allowed"] and s["next_change_ms"] == _utc(2027, 1, 15, 16, 0), "il passaggio 12:00 non e' un cambio"


# ---------------------------------------------------------------- file rovinato: mai operare fuori orario per errore
def test_broken_file_suspends_new_openings_and_keeps_the_last_good_hours():
    with tempfile.TemporaryDirectory() as d:
        _write(d, "{non json")
        s = th.hours_state(d, NOW)
        assert s["mode"] == "invalid" and s["blocked"] and "illeggibile" in s["error"]
        _write(d, _hours([{"start": "00:00", "end": "24:00"}]))
        assert th.hours_state(d, NOW)["allowed"] and th.hours_state(d, NOW)["error"] == ""
        _write(d, _hours([]))                                         # file non valido dopo uno valido: resta il valido
        s = th.hours_state(d, NOW)
        assert s["mode"] == "on" and s["allowed"] and "nessuna fascia" in s["error"]
        os.remove(os.path.join(d, th.HOURS_FILE))                     # tolto il file = spento
        assert th.hours_state(d, NOW)["mode"] == "off"


def test_hours_state_never_raises():
    saved = th._allowed_at
    try:
        with tempfile.TemporaryDirectory() as d:
            _write(d, _hours([{"start": "00:00", "end": "24:00"}]))
            th.hours_state(d, NOW)                                    # carica una configurazione valida
            th._allowed_at = lambda *a: (_ for _ in ()).throw(ZeroDivisionError("bug"))
            _write(d, _hours([{"start": "00:00", "end": "24:00"}], tz="UTC"))
            s = th.hours_state(d, NOW)
            assert s["blocked"] and s["mode"] == "invalid" and "ZeroDivisionError" in s["error"]
    finally:
        th._allowed_at = saved


# ---------------------------------------------------------------- dentro il ciclo del bot
def _drain_ok(stub_decs):
    return td._sandbox(td._decisions_stub(*stub_decs))


def test_cycle_outside_hours_opens_nothing_and_inside_hours_works_as_before():
    with _drain_ok([td._dec("BTC", "open_long")]) as (d, calls):
        _write(d, _hours([{"start": "20:00", "end": "22:00"}]))      # NOW = 09:00 italiane: fuori
        state = {}
        cli.run_cycle(state, NOW)
        assert not cli.make_account(state).positions, "fuori orario nessuna nuova apertura"
        assert cli.drain_reason(NOW) == "orari"
    with _drain_ok([td._dec("BTC", "open_long")]) as (d, calls):
        _write(d, _hours([{"start": "08:00", "end": "12:00"}]))      # 09:00 italiane: dentro
        state = {}
        cli.run_cycle(state, NOW)
        assert "BTC" in cli.make_account(state).positions
        assert cli.drain_reason(NOW) == ""


def test_cycle_outside_hours_still_lets_the_bot_close_what_is_open():
    with _drain_ok([td._dec("BTC", "open_long")]) as (d, calls):
        state = {}
        cli.run_cycle(state, NOW)
        assert "BTC" in cli.make_account(state).positions            # aperta prima, senza orari
        _write(d, _hours([{"start": "20:00", "end": "22:00"}]))
        import desk.brain as _brain
        import desk.cli as _c
        _brain.call_claude = _c.call_claude = td._decisions_stub(td._dec("ETH", "open_long"), td._dec("BTC", "dca"))
        state["last_call_ms"] = 0
        state["last_open_ms"] = {}
        cli.run_cycle(state, NOW + cli.HOUR_MS)
        acc = cli.make_account(state)
        assert list(acc.positions) == ["BTC"] and acc.positions["BTC"].dca_count == 0, "niente nuovo ingresso, niente DCA"
        _brain.call_claude = _c.call_claude = td._decisions_stub(td._dec("BTC", "close", reason="segnale girato"))
        state["last_call_ms"] = 0
        cli.run_cycle(state, NOW + 2 * cli.HOUR_MS)
        assert not cli.make_account(state).positions, "l'uscita decisa dal bot e' ammessa anche fuori orario"


def test_the_pause_button_wins_even_inside_the_hours():
    with _drain_ok([td._dec("BTC", "open_long")]) as (d, calls):
        _write(d, _hours([{"start": "00:00", "end": "24:00"}]))
        assert cli.drain_reason(NOW) == ""
        open(os.path.join(d, "pause.flag"), "w").close()
        assert cli.drain_reason(NOW) == "pausa"
        state = {}
        cli.run_cycle(state, NOW)
        assert not cli.make_account(state).positions


def test_the_hours_can_never_start_a_paused_bot():
    """Se l'utente ha messo in pausa, entrare in una fascia non fa ripartire nulla."""
    with td._frozen_clock(), _drain_ok([td._dec("BTC", "open_long")]) as (d, calls):
        _write(d, _hours([{"start": "00:00", "end": "24:00"}]))
        open(os.path.join(d, "pause.flag"), "w").close()
        state, ctl = {}, {"next_cycle_ms": 0, "prev_paused": None}
        cli.loop_step(state, ctl)
        assert not cli.make_account(state).positions and not calls, "in pausa niente ciclo, niente Claude"


def test_loop_step_outside_hours_is_idle_without_positions_and_resumes_when_hours_start():
    with td._frozen_clock(), _drain_ok([td._dec("BTC", "open_long")]) as (d, calls):
        hb = lambda: json.load(open(os.path.join(d, "heartbeat.json")))
        _write(d, _hours([{"start": "20:00", "end": "22:00"}]))      # fuori
        state, ctl = {}, {"next_cycle_ms": 0, "prev_paused": None}
        assert cli.loop_step(state, ctl) is False, "fuori orario e senza posizioni: nessun ciclo"
        assert not calls, "nessuna chiamata a Claude, nessun costo"
        h = hb()["hours"]
        assert h["blocked"] and h["mode"] == "on" and h["next_change_ms"] == _utc(2027, 1, 15, 19, 0)
        assert hb()["mode"] == "running", "il tasto Pausa non e' stato premuto: la modalita' resta quella"
        _write(d, _hours([{"start": "08:00", "end": "12:00"}]))      # entra nella fascia
        assert cli.loop_step(state, ctl) is True, "entrando nella fascia il ciclo parte subito"
        assert "BTC" in cli.make_account(state).positions and calls
        assert hb()["hours"]["allowed"] and not hb()["hours"]["blocked"]


def test_loop_step_outside_hours_keeps_managing_open_positions():
    with td._frozen_clock(), _drain_ok([td._dec("BTC", "open_long")]) as (d, calls):
        state, ctl = {}, {"next_cycle_ms": 0, "prev_paused": None}
        assert cli.loop_step(state, ctl) is True
        assert "BTC" in cli.make_account(state).positions
        _write(d, _hours([{"start": "20:00", "end": "22:00"}]))      # esce dalla fascia con una posizione aperta
        assert cli.loop_step(state, ctl) is True, "la posizione aperta va ancora gestita: ciclo subito"
        assert "BTC" in cli.make_account(state).positions, "fuori orario NON si chiude a forza"
        assert ctl["next_cycle_ms"] - NOW <= (cli.CYCLE_FAST_S + 5) * 1000, "si controlla spesso, come in pausa"


def test_heartbeat_carries_the_hours_summary_and_nothing_changes_without_the_file():
    with td._frozen_clock(), _drain_ok([td._dec("BTC", "open_long")]) as (d, calls):
        state, ctl = {}, {"next_cycle_ms": 0, "prev_paused": None}
        assert cli.loop_step(state, ctl) is True
        h = json.load(open(os.path.join(d, "heartbeat.json")))["hours"]
        assert h["mode"] == "off" and h["blocked"] is False and h["enabled"] is False
        assert "BTC" in cli.make_account(state).positions
