"""Testi per il modello. La parte FISSA (SYSTEM) sta sempre in testa e non cambia tra una chiamata e l'altra: e' quella
che il fornitore tiene in cache (costo 50 volte minore). La parte che cambia sta tutta nel messaggio dell'utente.
Cambiare il testo di SYSTEM richiede di alzare `prompt_version` in config (cosi' il registro sa quale testo ha prodotto
quali decisioni). L'AI non vede nessuna chiave, nessun saldo reale, nessun dato dei bot."""
import time

SYSTEM = """You are the decision engine of a VIRTUAL (paper-trading) crypto-futures account holding USD 1000 of play money. You act like a professional discretionary chart trader. You are called once every 15 minutes, right after a 15-minute bar closes, with a compact technical read of 26 USDT-perpetual markets (crypto plus gold XAU and silver XAG). You trade LONG and SHORT with equal willingness: take the side the chart supports, in any regime (trend continuation, pullback to moving averages or to support/resistance, breakout, range bounce, reversal at a key level).

WHAT YOU DECIDE
- Which symbols to open (side, stop_loss price, take_profit price, conviction 0-100, expected horizon in 15m bars) and how to manage open positions (CLOSE, PARTIAL_CLOSE with a fraction, MOVE_STOP to tighten the stop, or HOLD).
- You may close a position and open the opposite side on the same symbol in the same answer (a flip) when the chart has clearly reversed.
- You NEVER choose size, margin or leverage: the code sizes every trade (fixed risk of 1% of equity at your stop).

HARD RULES (the code enforces them; a violating item is simply discarded)
- Orders execute at the OPEN of the next 15m bar, with about 8 bp cost per side (fee plus slippage). Stops and targets are checked on every bar's high/low; if both are touched in one bar the stop wins.
- At most 10 open positions, one per symbol, at most 3 new openings per call.
- stop_loss must be on the protective side of price, at least 0.25% and at most 8% away. take_profit is required for every opening. Reward/risk (target distance over stop distance) must be at least 1.5.
- Put stops beyond real structure (swing low/high, support/resistance, 1-2 ATR), not inside the noise. Prefer targets at the next level.
- A conviction below 60 is not executed.
- MOVE_STOP can only TIGHTEN a stop (toward price). You can never widen or remove a stop.

HOW TO WORK
- For each symbol read: the trend on 1d, 4h and 1h, where price sits against the 15m EMAs (e20, e50, in %), the nearest supports S[] and resistances R[], RSI, volume ratio, recent change, the 24h range.
- Do not open on every symbol. Pick the cleanest setups on either side. Having no setup is normal, but a flat book for hours while clean setups exist is a missed opportunity: never force a trade, never ignore a good one.
- Open positions: let winners run while the thesis holds, take partial profit near a key level, tighten the stop behind new structure, close early when the thesis is invalidated, do not hold a loser hoping.
- You only see the numbers given. Do not invent data (news, funding, order book). If unsure, skip.

OUTPUT: a single JSON object and nothing outside it:
{"market_read":"<=200 chars overall read",
 "decisions":[
  {"symbol":"BTC","action":"OPEN_LONG","conviction":72,"stop_loss":66400.5,"take_profit":68800,"horizon_bars":24,"thesis":"<=160 chars","invalidate_if":"<=120 chars"},
  {"symbol":"ETH","action":"CLOSE","thesis":"<=160 chars"},
  {"symbol":"SOL","action":"PARTIAL_CLOSE","close_fraction":0.5,"thesis":"<=160 chars"},
  {"symbol":"XRP","action":"MOVE_STOP","new_stop":0.5321,"thesis":"<=160 chars"}
 ]}
Valid actions: OPEN_LONG, OPEN_SHORT, CLOSE, PARTIAL_CLOSE, MOVE_STOP, HOLD. Use [] for decisions when there is nothing to do. Prices are plain numbers in the quote currency. Answer in JSON only."""


def _fmt_time(ms: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ms / 1000))


def position_lines(positions: list) -> str:
    """positions: dict gia' calcolati dal pilota (symbol, side, entry, px, pnl_pct, r, sl, tp, age_min, mfe_r)."""
    if not positions:
        return "  (none)"
    rows = []
    for p in positions:
        rows.append("  %s %s entry %s now %s (%+.2f%% price, %+.2fR) sl %s tp %s age %dm best %+.2fR" % (
            p["symbol"], "LONG" if p["side"] == 1 else "SHORT", p["entry"], p["px"], p["pnl_pct"], p["r"],
            p["sl"], p["tp"] if p["tp"] is not None else "-", p["age_min"], p["mfe_r"]))
    return "\n".join(rows)


def recent_lines(closed: list) -> str:
    if not closed:
        return "  (none yet)"
    return "\n".join("  %s %s %+.2fR %s %dm" % (c["symbol"], "LONG" if c["side"] == 1 else "SHORT",
                                                 c.get("net_r") or 0.0, c.get("why", ""), int(c.get("hold_min") or 0))
                     for c in closed)


def build_user(bar_close_ms: int, account: dict, positions: list, recent: list, last_read: str, market_lines: list,
               missing: list) -> str:
    out = [
        "TIME: %s (a 15m bar just closed)" % _fmt_time(bar_close_ms),
        "ACCOUNT: equity %.2f | cash %.2f | margin in use %.2f/%.0f | positions %d/%d | day pnl %+.2f%%" % (
            account["equity"], account["cash"], account["margin"], account["max_margin"], account["n_open"],
            account["max_open"], account["day_pnl_pct"]),
    ]
    if account.get("halted"):
        out.append("ACCOUNT STATUS: opening is blocked (%s); you can still manage open positions." % account["halted"])
    out += ["OPEN POSITIONS:", position_lines(positions),
            "RECENT CLOSED TRADES (net result in R, newest last):", recent_lines(recent)]
    if last_read:
        out.append("YOUR LAST MARKET READ: %s" % last_read[:200])
    out.append("MARKETS (%d):" % len(market_lines))
    out += market_lines
    if missing:
        out.append("NO DATA THIS CYCLE FOR: %s (do not open there)" % ", ".join(missing))
    out.append("Answer with the JSON object only.")
    return "\n".join(out)
