"""Regole dei contratti con il codice installato e i dati Bitget ATTUALI (pubblici): ogni simbolo delle run deve averle.
Uso (dalla cartella del codice): python contratti_check.py <runner_config.json> [...]. Uscita 0 = tutti disponibili."""
import sys
import time
from decimal import Decimal

from backend.v3.lab_tools.fetch_candles import http_json
from backend.v3.runner.config import load_runner_config
from backend.v3.runner.contracts import ContractRules

syms = set()
for path in sys.argv[1:]:
    with open(path, "rb") as fh:
        syms |= set(load_runner_config(fh.read()).symbols)
rules = ContractRules(http_json, maintenance_fraction=Decimal("0.005"))
rules.load(int(time.time() * 1000))
miss = sorted(s for s in syms if rules(s) is None)
for s in sorted(syms - set(miss)):
    r = rules(s)
    print("  %s: leva exchange %s, passo %s, nozionale minimo %s" % (s, r["exchange_leverage_limit"], r["quantity_step"],
                                                                   r["minimum_notional"]))
print("regole contratti (dati Bitget attuali): %d/%d simboli%s" % (len(syms) - len(miss), len(syms),
                                                                    (" MANCANTI: " + ",".join(miss)) if miss else ""))
sys.exit(1 if miss or not syms else 0)
