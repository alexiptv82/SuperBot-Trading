# Lettore di regime v2 e laboratorio (Claude, 30/10/2026)

Proposta NON VALIDATA, offline: nessun bot, deploy o file di produzione toccato (ramo isolato, mai unito a `rule-pool`).

- `regime_v2.py` — il lettore (solo numpy): direzione (contesto K, presente D), qualita' del movimento (ER), volatilita' anomala (VR),
  9 stati + SHOCK, classe per lato ALIGNED/NEUTRAL/OPPOSED con **specchio esatto** long/short, livello simbolo e mercato (mediane),
  `read_regime()` per l'uso vivo (non solleva mai), blocco di prompt per il decisore. Profili `classic15` (15m/1h/4h, laboratorio) e
  `scalp1m` (1m/5m/15m/1h/4h, per il Brain: non validato, mancano dati 1m).
- `tests/test_regime_v2.py` — 19 test: specchio, causalita', equivalenza batch/vivo, buchi, isteresi, dati sporchi, svolta sintetica.
- `PREREGISTRAZIONE.md` — domande, parametri congelati e criteri, scritti prima dei risultati; registro di errata.
- `run_regime_lab.py` — laboratorio in due fasi (`--phase structure` non legge mai i rendimenti; `--phase full`). Dati: candele 15m pubbliche Bitget
  (`labdata.py`, solo in GitHub Actions: dal sandbox Bitget non e' raggiungibile) e i trade della replica base13 del 13/10 in `inputs/`.
- `PHASE` e `ITERATION` — quale fase gira al prossimo push (il workflow `regime-lab-claude.yml` li legge). `results/<fase>_<iterazione>/` — uscite.

Uso locale (dati finti): `python run_regime_lab.py --synthetic --days 60 --phase structure --out /tmp/x`.
