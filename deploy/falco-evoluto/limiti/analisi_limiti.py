"""Interazioni fra i limiti che bloccano le NUOVE aperture di una run PAPER (Falco Evoluto / Brain Scalp).

Solo aritmetica sulla configurazione (nessuna rete, nessun file della run): per un'equity di inizio giornata ``E``,
un massimo contabilizzato ``H`` (high-water mark del Guardian, solo realizzato) e un'equity d'inizio sessione ``S``,
calcola a quale equity scatta ciascun limite durante un calo e quale scatta per primo.

Limiti considerati (codice in produzione, non modificato):
* freno giornaliero (``runner/daily_loss.py``): perdita di oggi (realizzato oggi + non realizzato) >= ``halt`` * E
  -> nessuna nuova apertura fino a 00:00 UTC (agganciato); ``warn`` = solo avviso;
* Guardian, perdita di sessione (``guardian.py``): equity MTM <= S * (1 - session_loss) -> LOCKED fino alle 08:00
  Europe/Rome (agganciato per la sessione);
* Guardian, drawdown globale: equity MTM <= H * (1 - lock) -> LOCKED finche' vale (non agganciato);
  <= H * (1 - half) -> rischio per trade dimezzato (non blocca);
* floor di equity (``risk.py``): equity CONTABILIZZATA <= floor -> ``equity_floor_reached``; inoltre il rischio di ogni
  apertura e' <= equity - floor - rischio aperto, quindi le nuove aperture non possono, a stop, portare sotto il floor;
* rischio per trade 4 % e rischio aperto 10 % (invariati): limitano quanto si perde DOPO che un blocco e' scattato,
  perche' i blocchi fermano solo le nuove aperture (le posizioni aperte proseguono fino a stop/obiettivo/uscita).

Limiti di questo modello (dichiarati nel rapporto): gap e slippage oltre lo stop, liquidazione, finestre diverse
(giorno UTC contro sessione 08:00 Roma) e la base diversa del freno giornaliero (non realizzato contro il prezzo
d'ingresso) non sono simulati: il codice reale e' verificato separatamente nei test.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal as D
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.v3.runner.config import RunnerConfig, load_runner_config  # noqa: E402

def _pc(x) -> str:
    return f"{(x * 100).normalize():f}"


BLOCKS = ("freno_giornaliero", "guardian_sessione", "guardian_drawdown_globale", "floor_equity")
LABEL = {"freno_giornaliero": "stop giornaliero", "guardian_sessione": "Guardian perdita di sessione",
         "guardian_drawdown_globale": "Guardian drawdown globale 20 %", "floor_equity": "floor di equity",
         "avviso": "avviso giornaliero (solo messaggio)", "rischio_dimezzato": "Guardian: rischio per trade dimezzato"}


@dataclass(frozen=True)
class Soglia:
    nome: str
    equity: D          # equity alla quale scatta
    blocca: bool       # True = ferma le nuove aperture


def load(path: Path) -> RunnerConfig:
    return load_runner_config(Path(path).read_bytes())


def soglie(c: RunnerConfig, E: D, H: D | None = None, S: D | None = None) -> list[Soglia]:
    """Soglie in ordine di scatto durante un calo da ``E`` (prima la piu' alta)."""
    H = E if H is None else H
    S = E if S is None else S
    g, p = c.guardian, c.risk_policy
    out = [Soglia("avviso", E * (1 - c.daily_loss_warn), False),
           Soglia("freno_giornaliero", E * (1 - c.daily_loss_halt), True),
           Soglia("guardian_sessione", S * (1 - g.session_loss_fraction), True),
           Soglia("rischio_dimezzato", H * (1 - g.global_drawdown_half), False),
           Soglia("guardian_drawdown_globale", H * (1 - g.global_drawdown_lock), True),
           Soglia("floor_equity", p.minimum_equity, True)]
    return sorted(out, key=lambda s: (-s.equity, s.nome))


def primo_blocco(c: RunnerConfig, E: D, H: D | None = None, S: D | None = None) -> list[Soglia]:
    """Il limite (o i limiti, a parita') che ferma per primo le nuove aperture."""
    bl = [s for s in soglie(c, E, H, S) if s.blocca]
    top = bl[0].equity
    return [s for s in bl if s.equity == top]


def mai_raggiunti(c: RunnerConfig, E: D, H: D | None = None, S: D | None = None) -> list[str]:
    """Limiti bloccanti che, con sole nuove aperture rispettose del floor, non possono scattare: stanno SOTTO il floor
    (o sotto un blocco agganciato piu' alto). Possono ancora scattare per gap oltre lo stop."""
    bl = [s for s in soglie(c, E, H, S) if s.blocca]
    return [s.nome for s in bl if s.equity < c.risk_policy.minimum_equity]


def perdita_massima_giorno(c: RunnerConfig, E: D, H: D | None = None) -> D:
    """Perdita massima (frazione di E) di una giornata stimata a stop: il primo blocco scatta appena prima della soglia
    con il rischio aperto massimo ancora in corso; il floor la tronca. Esclude gap/slippage oltre lo stop."""
    first = primo_blocco(c, E, H)[0].equity
    worst = first - E * c.risk_policy.max_open_risk_fraction
    floor = c.risk_policy.minimum_equity
    return (E - max(worst, floor)) / E


def stop_pieni_prima_del_blocco(c: RunnerConfig, E: D, H: D | None = None) -> int:
    """Quante perdite consecutive a rischio pieno (una posizione alla volta) prima del primo blocco: rischio per trade
    = min(R, equity - floor), R dimezzato dal drawdown globale 10 %. Indicativo."""
    H = E if H is None else H
    first = primo_blocco(c, E, H)[0].equity
    eq, n = E, 0
    while eq > first and eq > c.risk_policy.minimum_equity and n < 1000:
        r = eq * c.risk_policy.max_loss_fraction
        if (H - eq) / H >= c.guardian.global_drawdown_half:
            r /= 2
        r = min(r, eq - c.risk_policy.minimum_equity)
        if r <= 0:
            break
        eq -= r
        n += 1
    return n


def _pct(x: D, base: D) -> str:
    return f"{(x - base) / base * 100:+.1f} %"


def rapporto(nome: str, c: RunnerConfig, scenari) -> str:
    righe = [f"== {nome}: capitale {c.initial_equity}, floor {c.risk_policy.minimum_equity}, "
             f"avviso {_pc(c.daily_loss_warn)} %, stop {_pc(c.daily_loss_halt)} %, "
             f"sessione {_pc(c.guardian.session_loss_fraction)} %, drawdown globale "
             f"{_pc(c.guardian.global_drawdown_half)}/{_pc(c.guardian.global_drawdown_lock)} %"]
    for titolo, E, H in scenari:
        righe.append(f"-- {titolo} (inizio giornata {E}, massimo contabilizzato {H})")
        for s in soglie(c, E, H):
            righe.append(f"   {s.equity:>9.2f}  {_pct(s.equity, E):>8}  {'BLOCCA ' if s.blocca else 'avviso '} {LABEL[s.nome]}")
        pb = primo_blocco(c, E, H)
        righe.append(f"   primo blocco: {' = '.join(LABEL[s.nome] for s in pb)} a {_pct(pb[0].equity, E)}")
        mr = mai_raggiunti(c, E, H)
        if mr:
            righe.append(f"   non raggiungibili con nuove aperture (sotto il floor): {', '.join(LABEL[n] for n in mr)}")
        righe.append(f"   perdita massima stimata della giornata (a stop, senza gap): "
                     f"{perdita_massima_giorno(c, E, H) * 100:.1f} %; perdite consecutive a rischio pieno prima del "
                     f"blocco: {stop_pieni_prima_del_blocco(c, E, H)}")
    return "\n".join(righe)


def scenari_di(c: RunnerConfig):
    i = c.initial_equity
    return (("partenza", i, i), ("dopo +20 % contabilizzato", i * D("1.2"), i * D("1.2")),
            ("dopo una giornata a -10 %", i * D("0.9"), i))


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    runner = ROOT / "backend" / "v3" / "runner"
    for nome, f in (("Brain Scalp", "runner_config_brain_scalp_paper.json"),
                    ("Falco Evoluto", "runner_config_falco_evoluto_paper.json")):
        for tag, base in (("ATTUALE", runner), ("PROPOSTA", here)):
            c = load(base / f)
            print(rapporto(f"{nome} {tag}", c, scenari_di(c)))
            print()
