"""Esaminatore dei candidati scartati: etichettatura con le candele, unione dei quasi uguali, statistiche, rapporto."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desk import analyst as an  # noqa: E402

T0 = 1_800_000_000_000
BAR = an.BAR_MS


def cand(side=1, price=100.0, sl=0.01, tp=0.02, status="conf_bassa", ts=T0, symbol="BTC", bot="hawk", **extra):
    c = {"ev": "candidate", "status": status, "ts": ts, "symbol": symbol, "price": price, "side": side, "bot": bot,
         "run_no": 1, "features": {"dec_sl_pct": sl, "dec_tp_pct": tp, "dec_type": "medio"}}
    c.update(extra)
    return c


def bars(spec, start=T0 + BAR):
    """spec = [(high, low, close), ...] -> candele [ts, open, high, low, close, vol] una dopo l'altra."""
    return [[start + i * BAR, cl, hi, lo, cl, 1.0] for i, (hi, lo, cl) in enumerate(spec)]


FLAT = (100.2, 99.8, 100.0)


def test_long_hits_take_profit_first():
    lab = an.label_candidate(cand(), bars([FLAT, (101.0, 99.9, 100.9), (102.1, 100.5, 102.0)]), horizon_bars=8)
    assert lab["ok"] and lab["outcome"] == "tp" and lab["r"] == 2.0 and lab["bars"] == 3 and not lab["ambiguous"]
    assert lab["mfe_r"] > 1.9 and lab["mae_r"] < 0.3


def test_long_hits_stop_first():
    lab = an.label_candidate(cand(), bars([FLAT, (100.1, 98.9, 99.0), (103.0, 99.0, 103.0)]), horizon_bars=8)
    assert lab["outcome"] == "sl" and lab["r"] == -1.0 and lab["bars"] == 2, "dopo lo stop il resto non conta"


def test_short_is_the_mirror_image():
    c = cand(side=-1)
    assert an.label_candidate(c, bars([FLAT, (100.1, 97.9, 98.0)]), horizon_bars=8)["outcome"] == "tp"
    lab = an.label_candidate(c, bars([FLAT, (101.1, 99.9, 101.0)]), horizon_bars=8)
    assert lab["outcome"] == "sl" and lab["r"] == -1.0


def test_stop_and_take_profit_in_the_same_candle_counts_the_stop():
    lab = an.label_candidate(cand(), bars([(102.5, 98.5, 100.0)]), horizon_bars=1)
    assert lab["outcome"] == "sl" and lab["ambiguous"] is True and lab["r"] == -1.0


def test_timeout_is_marked_to_the_last_close_only_when_the_horizon_is_complete():
    flat = [FLAT] * 7 + [(100.6, 99.8, 100.5)]
    lab = an.label_candidate(cand(), bars(flat), horizon_bars=8)
    assert lab["ok"] and lab["outcome"] == "timeout" and lab["r"] == 0.5 and lab["bars"] == 8
    short_lab = an.label_candidate(cand(side=-1), bars(flat), horizon_bars=8)
    assert short_lab["outcome"] == "timeout" and short_lab["r"] == -0.5


def test_unresolved_candidates_are_not_labeled_but_resolved_ones_are_even_if_recent():
    pending = an.label_candidate(cand(), bars([FLAT] * 3), horizon_bars=8)
    assert pending == {"ok": False, "why": "non ancora risolto"}
    quick = an.label_candidate(cand(), bars([FLAT, (102.5, 100.0, 102.4)]), horizon_bars=8)
    assert quick["ok"] and quick["outcome"] == "tp", "se il TP e' gia' stato toccato il risultato e' noto"


def test_candle_of_the_candidate_itself_is_not_used():
    early = [[T0, 100.0, 105.0, 90.0, 100.0, 1.0]]                  # candela che inizia ESATTAMENTE al momento del candidato
    lab = an.label_candidate(cand(), early + bars([FLAT] * 8), horizon_bars=8)
    assert lab["outcome"] == "timeout", "il massimo/minimo di quella candela e' in parte precedente alla decisione"


def test_cannot_label_without_stop_or_candles_or_data():
    assert an.label_candidate(cand(sl=0), bars([FLAT] * 8))["why"] == "senza stop deciso"
    assert an.label_candidate(cand(), [])["why"] == "senza candele"
    assert an.label_candidate({"ev": "candidate"}, bars([FLAT]))["why"] == "dati mancanti"
    assert an.label_candidate(cand(side=0), bars([FLAT]))["why"] == "dati non validi"


def test_candidate_without_take_profit_can_only_stop_or_time_out():
    c = cand(tp=0)
    assert an.label_candidate(c, bars([FLAT, (110.0, 100.0, 110.0)]), horizon_bars=2)["outcome"] == "timeout"
    assert an.label_candidate(c, bars([FLAT, (100.0, 98.0, 98.5)]), horizon_bars=2)["outcome"] == "sl"


def test_scalps_use_a_shorter_horizon_than_the_others():
    c = cand()
    c["features"]["dec_type"] = "scalp"
    assert an.label_candidate(c, bars([FLAT] * 24))["outcome"] == "timeout", "6 ore bastano per uno scalp"
    assert an.label_candidate(cand(), bars([FLAT] * 24))["why"] == "non ancora risolto", "il medio ne vuole 96"


def test_dedupe_counts_a_repeated_idea_once():
    h = 3_600_000
    cs = [cand(ts=T0 + i * h) for i in range(6)]                       # la stessa idea riproposta ogni ora per 6 ore
    kept = an.dedupe(cs)
    assert [c["ts"] for c in kept] == [T0, T0 + 4 * h], "una ogni 4 ore"
    mixed = cs[:2] + [cand(ts=T0 + h, status="cooldown"), cand(ts=T0 + h, bot="bull"), cand(ts=T0 + h, side=-1),
                      cand(ts=T0 + h, symbol="ETH")]
    assert len(an.dedupe(mixed)) == 5, "stato, bot, lato e simbolo diversi sono idee diverse"
    assert an.status_head({"status": "rifiutata:margine"}) == "rifiutata" and an.status_head({}) == "?"


def test_summary_and_verdict_are_prudent_with_few_cases():
    lab = lambda o, r: {"ok": True, "outcome": o, "r": r, "mfe_r": 0.5, "mae_r": 0.5}
    few = an.summarize([(cand(), lab("sl", -1.0))] * 5)
    assert few["n"] == 5 and few["indicativo"] and "troppo pochi" in an.verdict(few)
    losers = an.summarize([(cand(), lab("sl", -1.0))] * 40)
    assert not losers["indicativo"] and losers["r_medio"] == -1.0 and "PROTEGGERE" in an.verdict(losers)
    winners = an.summarize([(cand(), lab("tp", 2.0))] * 40)
    assert winners["win_rate"] == 1.0 and "COSTARE" in an.verdict(winners)
    coin = an.summarize([(cand(), lab("tp", 2.0))] * 15 + [(cand(), lab("sl", -1.0))] * 25)
    assert "nessuna differenza chiara" in an.verdict(coin)
    assert an.summarize([]) == {"n": 0} and "nessun caso" in an.verdict({"n": 0})
    assert an.wilson(0, 0) == (None, None)


def test_fetch_range_pages_backwards_and_never_raises():
    start = T0
    all_bars = [[start + i * BAR, 1, 2, 0.5, 1, 1, 1] for i in range(450)]    # 450 candele = 3 pagine da 200
    calls = []

    def get(url):
        calls.append(url)
        end = int(url.split("endTime=")[1].split("&")[0])
        page = [b for b in all_bars if b[0] <= end][-200:]
        return json.dumps({"code": "00000", "data": [[str(x) for x in b] for b in reversed(page)]}).encode()

    out = an.fetch_range("BTC", start, start + 449 * BAR, get=get)
    assert len(out) == 450 and out[0][0] == start and out[-1][0] == start + 449 * BAR and len(calls) == 3
    assert all("BTCUSDT" in u and "history-candles" in u for u in calls)

    def broken(url):
        raise OSError("rete giu'")
    assert an.fetch_range("BTC", start, start + BAR, get=broken) == []
    assert an.fetch_range("BTC", start, start + BAR, get=lambda u: b"non json") == []
    assert an.fetch_range("BTC", start, start + BAR, get=lambda u: json.dumps({"code": "40001"}).encode()) == []


def test_examine_report_end_to_end():
    ev = {"hawk": [], "bull": []}
    # 35 idee diverse scartate per "conf_bassa" (una al giorno, cosi' non si uniscono) che avrebbero tutte perso
    for i in range(35):
        ev["hawk"].append(cand(ts=T0 + i * 86_400_000, status="conf_bassa", code_version="aaa1111"))
    ev["hawk"].append(cand(ts=T0 + 40 * 86_400_000, status="macro_blocco", features={
        "dec_sl_pct": 0.01, "dec_tp_pct": 0.02, "dec_type": "medio", "macro_regime": "alto"}))
    ev["bull"].append({"ev": "close", "run_no": 1, "id": 3, "net_r": 0.8})
    ev["bull"].append({"ev": "close", "run_no": 1, "id": 4, "net_r": -1.0})
    candles = []
    for i in range(35):
        candles += bars([(100.1, 98.9, 99.0)] + [FLAT] * 95, start=T0 + i * 86_400_000 + BAR)
    candles += bars([FLAT] * 5, start=T0 + 40 * 86_400_000 + BAR)             # il candidato macro e' ancora aperto
    txt = an.examine(ev, {"BTC": candles})
    assert "ESAMINATORE DEI CANDIDATI SCARTATI" in txt
    assert "candidati nel registro: 36" in txt and "etichettati: 35" in txt and "non ancora risolto" in txt
    assert "conf_bassa" in txt and "PROTEGGERE" in txt and "R_medio=-1.00" in txt
    assert "PER VERSIONE CODICE" not in txt or "aaa1111" in txt
    assert "PER CONFRONTO" in txt and "n=2" in txt
    empty = an.examine({"hawk": [], "bull": []}, {})
    assert "Nessun candidato etichettabile" in empty
