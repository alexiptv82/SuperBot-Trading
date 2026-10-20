"""Turbo Scalp v0: strategia di scalping su barre CHIUSE da 5 minuti, SOLO in ombra.

Puro calcolo: niente rete, niente file, niente ordini. Lo stesso codice serve all'ombra in tempo reale e al
replay storico. Ogni trade e' ipotetico e registrato con costi pieni (commissioni e slippage come l'engine dei
bot: 6 bp + 2 bp per lato), senza vincoli di cassa: misura la strategia, non un portafoglio.

Regola v0 (ipotesi da validare, NON una strategia approvata). Rimbalzo sulla media veloce nel verso del trend:
  LONG  se EMA20 > EMA50, EMA50 in salita su 6 barre, la barra chiusa ha toccato l'EMA20 (minimo <= EMA20),
        ha chiuso sopra l'EMA20 ed e' verde. SHORT speculare.
  Ingresso all'APERTURA della barra successiva (+ slippage): la decisione si prende a barra chiusa.
  Stop a distanza d = max(1,2 x ATR14, 0,4%) dall'ingresso; segnale scartato se d > 1,5%.
    Il minimo 0,4% esiste per i costi: ~16 bp di andata e ritorno su uno stop dello 0,2% valgono 0,8R.
  Obiettivo a 1,5R. Uscita a tempo dopo 24 barre (2 ore) al prezzo di chiusura.
  Se nella stessa barra si toccano stop e obiettivo vale lo stop (ipotesi pessimistica, come l'engine).
  Massimo 3 posizioni insieme, una per simbolo; 3 barre di pausa sul simbolo dopo ogni uscita.
Il funding non e' contato (detenzione massima 2 ore: effetto trascurabile, dichiarato).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

SCHEMA = 1


@dataclass(frozen=True)
class Config:
    name: str = "turbo-scalp"
    version: str = "0.1.0"
    bar_ms: int = 300_000
    symbols: tuple = ("BTC", "ETH", "SOL", "XRP", "DOGE", "BNB")
    ema_fast: int = 20
    ema_slow: int = 50
    slope_bars: int = 6
    atr_n: int = 14
    sl_atr: float = 1.2
    sl_min: float = 0.004
    sl_max: float = 0.015
    tp_r: float = 1.5
    max_bars: int = 24
    cooldown_bars: int = 3
    max_open: int = 3
    fee_bp: float = 6.0
    slip_bp: float = 2.0
    margin_usd: float = 100.0      # scala in dollari dei risultati (come una posizione di Hawk)
    leverage: int = 20

    @property
    def min_bars(self) -> int:
        return self.ema_slow * 2 + self.slope_bars


def config_hash(cfg: Config) -> str:
    raw = json.dumps(asdict(cfg), sort_keys=True, separators=(",", ":"), default=list)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def algo(cfg: Config) -> dict:
    return {"name": cfg.name, "version": cfg.version, "config_hash": config_hash(cfg)}


# ---------------- indicatori (solo barre chiuse: tuple (open_ms, o, h, l, c))

def ema_last(values, n: int) -> list:
    a = 2 / (n + 1)
    out, cur = [], values[0]
    for v in values:
        cur = a * v + (1 - a) * cur
        out.append(cur)
    return out


def atr_last(bars, n: int) -> float:
    trs = [max(b[2] - b[3], abs(b[2] - p[4]), abs(b[3] - p[4])) for p, b in zip(bars[:-1], bars[1:])]
    tail = trs[-n:]
    return sum(tail) / len(tail)


def signal(bars, cfg: Config):
    """Segnale sull'ULTIMA barra chiusa di `bars`. Ritorna None o {"side", "dist", "atr_pct", "why"}."""
    if len(bars) < cfg.min_bars or not regular(bars[-cfg.min_bars:], cfg.bar_ms):
        return None
    closes = [b[4] for b in bars]
    fast, slow = ema_last(closes, cfg.ema_fast), ema_last(closes, cfg.ema_slow)
    o, h, lo, c = bars[-1][1], bars[-1][2], bars[-1][3], bars[-1][4]
    f, s, s_prev = fast[-1], slow[-1], slow[-1 - cfg.slope_bars]
    side = 0
    if f > s and s > s_prev and lo <= f < c and c > o:
        side = 1
    elif f < s and s < s_prev and h >= f > c and c < o:
        side = -1
    if not side:
        return None
    a = atr_last(bars, cfg.atr_n)
    dist = max(cfg.sl_atr * a / c, cfg.sl_min)
    if dist > cfg.sl_max:
        return None
    return {"side": side, "dist": round(dist, 6), "atr_pct": round(a / c, 6),
            "why": "rimbalzo EMA%d %s" % (cfg.ema_fast, "trend su" if side == 1 else "trend giu")}


# ---------------- simulazione

def _exit_record(sym, pos, bar, price, why, cfg: Config) -> dict:
    side, entry = pos["side"], pos["entry"]
    slip, fee = cfg.slip_bp / 1e4, cfg.fee_bp / 1e4
    fill = price * (1 - side * slip)
    notional = cfg.margin_usd * cfg.leverage
    qty = notional / entry
    gross = side * (fill - entry) * qty
    fees = fee * (entry * qty + fill * qty)
    net = gross - fees
    risk = notional * pos["dist"]
    return {"ev": "exit", "id": "%s:%d:exit" % (sym, pos["entry_bar_ms"]), "symbol": sym, "side": side,
            "entry_bar_ms": pos["entry_bar_ms"], "exit_bar_ms": bar[0], "close_ms": bar[0] + cfg.bar_ms,
            "entry": entry, "exit": round(fill, 10), "why": why, "bars": pos["bars"],
            "gross_usd": round(gross, 4), "fees_usd": round(fees, 4), "net_usd": round(net, 4),
            "net_r": round(net / risk, 4) if risk > 0 else None, "dist": pos["dist"]}


def _manage(sym, pos, bar, cfg: Config):
    """Gestisce una posizione su una barra. Ritorna (posizione_aggiornata | None, evento | None)."""
    _, o, h, lo, c = bar
    side, sl, tp = pos["side"], pos["sl"], pos["tp"]
    pos = dict(pos, bars=pos["bars"] + 1)
    if side == 1:
        if lo <= sl:
            return None, _exit_record(sym, pos, bar, min(sl, o), "stop", cfg)
        if h >= tp:
            return None, _exit_record(sym, pos, bar, tp, "obiettivo", cfg)
    else:
        if h >= sl:
            return None, _exit_record(sym, pos, bar, max(sl, o), "stop", cfg)
        if lo <= tp:
            return None, _exit_record(sym, pos, bar, tp, "obiettivo", cfg)
    if pos["bars"] >= cfg.max_bars:
        return None, _exit_record(sym, pos, bar, c, "tempo", cfg)
    return pos, None


def _fill(sym, pend, bar, cfg: Config):
    side, d = pend["side"], pend["dist"]
    entry = bar[1] * (1 + side * cfg.slip_bp / 1e4)
    pos = {"side": side, "entry": round(entry, 10), "dist": d, "entry_bar_ms": bar[0], "bars": 0,
           "sl": entry * (1 - side * d), "tp": entry * (1 + side * d * cfg.tp_r)}
    ev = {"ev": "fill", "id": "%s:%d:fill" % (sym, bar[0]), "symbol": sym, "side": side, "bar_ms": bar[0],
          "entry": pos["entry"], "sl": round(pos["sl"], 10), "tp": round(pos["tp"], 10), "dist": d}
    return pos, ev


def new_state(cfg: Config) -> dict:
    return {"schema": SCHEMA, "config_hash": config_hash(cfg), "last_bar_ms": {}, "open": {}, "pending": {},
            "cooldown_until_ms": {}}


def regular(bars, bar_ms: int) -> bool:
    return all(b[0] - a[0] == bar_ms for a, b in zip(bars[:-1], bars[1:]))


def step(state: dict, bars_by_symbol: dict, cfg: Config) -> tuple:
    """Elabora le barre chiuse NUOVE di ogni simbolo, in ordine di tempo su tutti i simboli (il tetto di
    posizioni e' globale). Primo incontro con un simbolo: si parte dall'ultima barra, senza ricostruire il
    passato. Un buco nella serie annulla segnale e posizione ipotetici di quel simbolo (evento "buco").
    Ritorna (nuovo stato, eventi). Lo stato in ingresso non viene modificato."""
    st = json.loads(json.dumps(state))
    events, timeline = [], []
    for sym, bars in sorted(bars_by_symbol.items()):
        bars = [tuple(b) for b in bars]
        if not bars:
            continue
        last = st["last_bar_ms"].get(sym)
        if last is None:
            st["last_bar_ms"][sym] = bars[-1][0]
            continue
        new = [b for b in bars if b[0] > last]
        if not new:
            continue
        hist = [b for b in bars if b[0] <= last]
        if (hist and new[0][0] - hist[-1][0] != cfg.bar_ms) or (not hist and new[0][0] - last != cfg.bar_ms) \
                or not regular(new, cfg.bar_ms):
            dropped = [k for k in ("open", "pending") if sym in st[k]]
            st["open"].pop(sym, None)
            st["pending"].pop(sym, None)
            st["last_bar_ms"][sym] = new[-1][0]
            events.append({"ev": "buco", "id": "%s:%d:buco" % (sym, new[-1][0]), "symbol": sym,
                           "after_ms": last, "until_ms": new[-1][0], "annullati": dropped})
            continue
        for i, b in enumerate(new):
            timeline.append((b[0], sym, b, bars[: len(hist) + i + 1]))
    timeline.sort(key=lambda x: (x[0], x[1]))
    for t, sym, bar, upto in timeline:
        pend = st["pending"].pop(sym, None)
        if pend is not None:
            pos, ev = _fill(sym, pend, bar, cfg)
            st["open"][sym] = pos
            events.append(ev)
        pos = st["open"].get(sym)
        if pos is not None:
            pos, ev = _manage(sym, pos, bar, cfg)
            if pos is None:
                st["open"].pop(sym)
                st["cooldown_until_ms"][sym] = t + cfg.cooldown_bars * cfg.bar_ms
                events.append(ev)
            else:
                st["open"][sym] = pos
        st["last_bar_ms"][sym] = t
        busy = len(st["open"]) + len(st["pending"])
        if sym in st["open"] or busy >= cfg.max_open or t < st["cooldown_until_ms"].get(sym, 0):
            continue
        sig = signal(upto, cfg)
        if sig:
            st["pending"][sym] = {"side": sig["side"], "dist": sig["dist"], "signal_bar_ms": t}
            events.append({"ev": "signal", "id": "%s:%d:signal" % (sym, t), "symbol": sym, "bar_ms": t,
                           "side": sig["side"], "dist": sig["dist"], "atr_pct": sig["atr_pct"], "why": sig["why"]})
    return st, events


def summarize(exits) -> dict:
    """Riepilogo onesto delle uscite: numero, vittorie, R medio con intervallo al 95% (approssimazione normale),
    netto in dollari. Sotto 30 trade il risultato e' solo indicativo."""
    rs = [e["net_r"] for e in exits if e.get("net_r") is not None]
    n = len(rs)
    out = {"trades": n, "net_usd": round(sum(e["net_usd"] for e in exits), 2),
           "fees_usd": round(sum(e["fees_usd"] for e in exits), 2), "indicativo": n < 30}
    if n:
        mean = sum(rs) / n
        var = sum((r - mean) ** 2 for r in rs) / (n - 1) if n > 1 else 0.0
        half = 1.96 * (var / n) ** 0.5
        out.update({"win_rate": round(sum(1 for r in rs if r > 0) / n, 3), "mean_r": round(mean, 3),
                    "ci95_r": [round(mean - half, 3), round(mean + half, 3)],
                    "by_why": {w: sum(1 for e in exits if e["why"] == w) for w in ("stop", "obiettivo", "tempo")}})
    return out
