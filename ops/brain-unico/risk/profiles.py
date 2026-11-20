"""Profili di rischio PROPOSTI per Brain Unico (capitale PAPER di riferimento 2.000 USDT). Solo aritmetica.

Nessun parametro operativo viene letto o scritto: le tabelle servono al proprietario per scegliere. Regole di calcolo
uguali al RiskManager (`backend/v3/risk.py`): perdita allo stop = rischio scelto, nozionale = rischio / (stop + costi),
margine = nozionale / leva, distanza di liquidazione = 1/leva - mantenimento - costi, stop entro buffer x distanza.
Uso: python3 profiles.py  (stampa le tabelle in Markdown).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

EQUITY = 2000.0
FEE = 0.0006           # per lato (runner_config: fee_bps 6)
SLIP = 0.0002          # per lato (runner_config: slippage_bps 2)
COST = 2 * (FEE + SLIP)  # 0,16 % andata e ritorno = estimated_roundtrip_cost_bp 16
MAINT = 0.005
BUFFER = 0.5           # liquidation_buffer_fraction
GAP = 0.03             # scenario di gap oltre lo stop


@dataclass(frozen=True)
class Profile:
    name: str
    risk: float               # rischio per trade (frazione dell'equity)
    open_risk: float          # rischio aperto totale
    pos_margin: float         # margine massimo per posizione
    total_margin: float       # margine totale
    min_lev: int
    max_lev: int
    cost_cap: float | None    # costi massimi come quota del rischio (None = nessun filtro)
    loss_margin: float | None  # vincolo storico perdita/margine
    warn: float               # limite giornaliero: avviso
    halt: float               # limite giornaliero: stop alle aperture (latch persistente)
    floor: float              # equity minima


HISTORICAL = Profile("Storico (non approvato)", 0.042857142857142857, 0.12, 0.20, 0.55, 20, 50, None,
                     0.214285714285714285, 0.35, 0.50, 450)
PROFILES = (
    Profile("A Prudente", 0.0075, 0.03, 0.20, 0.40, 1, 20, 0.20, None, 0.02, 0.03, 1700),
    Profile("B Bilanciato", 0.010, 0.04, 0.20, 0.50, 1, 30, 0.25, None, 0.03, 0.04, 1600),
    Profile("C Dinamico", 0.015, 0.06, 0.20, 0.55, 1, 50, 0.33, None, 0.045, 0.06, 1500),
)


def liq_dist(lev: int) -> float:
    return 1.0 / lev - MAINT - COST


def checks(p: Profile, stop: float, lev: int) -> str | None:
    """Controlli del RiskManager che dipendono dalla leva richiesta (non dalla dimensione): motivo o None."""
    if not (liq_dist(lev) > 0 and stop < BUFFER * liq_dist(lev)):
        return "liquidazione"
    if p.loss_margin is not None and lev * (stop + COST) > p.loss_margin:
        return "perdita/margine 21,4 %"
    return None


def quote(p: Profile, stop: float) -> dict:
    """Come `quote_paper_risk`: quantita' = min(da rischio, da tetto di margine x leva). Si sceglie la leva MINIMA
    che da' il rischio pieno; se nessuna leva ammessa lo consente, la leva ammessa piu' alta con rischio RIDOTTO."""
    risk_usd = EQUITY * p.risk
    cap = EQUITY * p.pos_margin
    full = risk_usd / (stop + COST)
    cost_share = COST / (stop + COST)
    out = {"stop": stop, "risk_usd": risk_usd, "cost_share": cost_share,
           "breakeven_wr_2r": (stop + COST) / (3 * stop)}
    ok = [lev for lev in range(p.min_lev, p.max_lev + 1) if checks(p, stop, lev) is None]
    if p.cost_cap is not None and cost_share > p.cost_cap:
        out.update(allowed=False, reasons=["costi (filtro proposto)"], notional=full, gap_loss=full * (GAP + COST))
        return out
    if not ok:
        out.update(allowed=False, reasons=[checks(p, stop, p.min_lev) or "leva"], notional=full,
                   gap_loss=full * (GAP + COST))
        return out
    fulls = [lev for lev in ok if cap * lev >= full]
    lev = min(fulls) if fulls else max(ok)
    notional = min(full, cap * lev)
    out.update(allowed=True, leverage=lev, notional=notional, margin=notional / lev, liq=liq_dist(lev),
               eff_risk=notional * (stop + COST), gap_loss=notional * (GAP + COST))
    return out


def summary(p: Profile) -> dict:
    risk = EQUITY * p.risk
    return {"risk_usd": risk, "positions_max": int(round(p.open_risk / p.risk)),
            "min_stop_costs": (COST / p.cost_cap - COST) if p.cost_cap else None,
            "day_halt_r": p.halt / p.risk, "day_worst_pct": p.halt + p.open_risk,
            "losses_to_floor": (EQUITY - p.floor) / risk, "floor_drawdown": 1 - p.floor / EQUITY}


def _pct(x, d=2):
    return ("%." + str(d) + "f %%") % (100 * x)


def markdown() -> str:
    lines = ["| Profilo | Rischio/trade | Posizioni max | Rischio aperto | Margine pos./tot. | Leva | Stop minimo (costi) "
             "| Giorno: avviso / stop | Giorno peggiore* | Pavimento | Perdite piene fino al pavimento |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in (HISTORICAL,) + PROFILES:
        s = summary(p)
        lines.append("| %s | %s (%.0f USDT) | %d | %s | %s / %s | %d–%d× | %s | %s / %s (%.1f R) | %s | %.0f (−%s) | %.1f |" % (
            p.name, _pct(p.risk), s["risk_usd"], s["positions_max"], _pct(p.open_risk, 0), _pct(p.pos_margin, 0),
            _pct(p.total_margin, 0), p.min_lev, p.max_lev,
            _pct(s["min_stop_costs"]) if s["min_stop_costs"] is not None else "nessuno",
            _pct(p.warn, 1), _pct(p.halt, 1), s["day_halt_r"], _pct(s["day_worst_pct"], 1), p.floor,
            _pct(s["floor_drawdown"], 1), s["losses_to_floor"]))
    lines.append("")
    lines.append("| Profilo | Stop | Leva | Nozionale | Margine | Rischio effettivo | Distanza liquidazione | Costi/rischio "
                 "| Pareggio con TP 2R | Gap 3 % (PAPER) | Esito |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for p in (HISTORICAL,) + PROFILES:
        for stop in (0.003, 0.005, 0.01, 0.02):
            q = quote(p, stop)
            if q["allowed"]:
                full = q["eff_risk"] >= q["risk_usd"] - 0.01
                lines.append("| %s | %s | %d× | %.0f | %.0f | %.0f USDT%s | %s | %s | %s | %.0f (%s) | %s |" % (
                    p.name, _pct(stop, 1), q["leverage"], q["notional"], q["margin"], q["eff_risk"],
                    "" if full else " (ridotto dal margine)", _pct(q["liq"]), _pct(q["cost_share"], 0),
                    _pct(q["breakeven_wr_2r"], 1), q["gap_loss"], _pct(q["gap_loss"] / EQUITY, 1),
                    "ammesso" if full else "ammesso, rischio ridotto"))
            else:
                lines.append("| %s | %s | — | — | — | — | — | %s | %s | — | rifiutato: %s |" % (
                    p.name, _pct(stop, 1), _pct(q["cost_share"], 0), _pct(q["breakeven_wr_2r"], 1),
                    ", ".join(q["reasons"])))
    lines.append("")
    lines.append("*Giorno peggiore = soglia di stop alle aperture + rischio delle posizioni ancora aperte (che "
                 "proseguono fino al loro stop), senza gap.")
    return "\n".join(lines)


if __name__ == "__main__":
    print(markdown())
