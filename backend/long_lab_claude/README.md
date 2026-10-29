# Laboratorio "modifica long" (Claude, 29/10/2026)

Misura la modifica P1 ("sbias LONG", commit 635b964, oggi in stand-by) sul codice del 13/10 (`9fa667f`, quello in funzione) e
prova varianti piu' affidabili. **Offline: nessun bot, nessun deploy, nessun file di produzione toccato.**

- `PREREGISTRAZIONE.md` — domande, varianti e criteri di adozione, scritti prima dei risultati.
- `labfeat.py` — valori e punteggio vettoriale, identici a `desk.signals.read_symbol` (test).
- `labrun.py` — riproduzione con `PaperAccount` e `rules_decisions` veri, regime (`desk.regime`), statistiche e criteri.
- `events.py` — esperimento sugli eventi (il rimbalzo di P1 ha un vantaggio proprio?).
- `run_lab.py` — orchestrazione; `labdata.py` — candele pubbliche Bitget.
- `tests/test_lab.py` — equivalenza con la funzione vera (anche P1), stagionalita', riproduzione.
- `results/` — `summary.json` e `report.md`, scritti dal workflow `long-lab-claude.yml` sul solo ramo del laboratorio.

Uso locale (dati finti): `cd backend/long_lab_claude && python run_lab.py --synthetic --days 30 --out /tmp/x`.
