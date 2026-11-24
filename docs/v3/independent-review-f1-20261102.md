# Revisione indipendente richiesta — SuperBot V3 F1 (Cloud/Claude e Grok)

**Mandato:** verifica tecnica indipendente, NON modifica/implementazione. Leggere la [PR #29](https://github.com/alexiptv82/SuperBot-Trading/pull/29) e il codice **del ramo** `work/v3-foundations-event-risk-20261102`, non `main`. Non usare credenziali, non accedere alla VPS, non modificare GitHub, non chiudere/mergiare PR, non simulare ordini live e non correggere dati originali.

## Evidenza già registrata (da ricontrollare criticamente, non presumere vera)

- Audit snapshot offline read-only: [workflow #41497955027](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41497955027).
- Suite CI [#41497835752](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41497835752): 49 test PASS Python 3.10 e 3.11 su fixture sintetiche.
- Falco: 348/348 chiusure riconciliate su 7 run; current-run cash/book PASS, 6 posizioni PAPER lasciate aperte.
- Toro: 186/186 chiusure su 7 run; current-run cash/book PASS, 2 aperte.
- Brain Free: 8447 eventi, 182 open/182 final, 55 partial; riconciliazione cash e segmenti PASS su due epoche V1→V2; 0 posizioni residue. `experiment_reframed` riutilizza gli ID ma mantiene `old_cash == new_cash`.

## File essenziali

- `backend/v3/events.py`: SHA-256 journal append-only, idempotenza e hash chain.
- `backend/v3/legacy_audit.py`, `legacy_multirun.py`, `legacy_accounting.py`, `legacy_brain_books.py`.
- `backend/v3/risk.py` e suite `backend/tests/test_v3_*.py`.
- Contract sorgente `backend/desk/engine.py`, `backend/desk/cli.py` su `rule-pool`; `backend/director/brain_free/execution.py`, `store.py`, `reframe.py` su `work/brain-completion-20261031`.

## Questioni per il revisore

1. **Double counting / partial trades:** `trade_closed.net` Brain contiene già le `partial_trade`. Verificare ogni caso di part-only, chiusura totale, DCA/eventi futuri, liquidazione, funding e round-off. Il replay dei classici preserva record parziali e ID per run?
2. **Cash invariants:** la formula dei classici `cash + open margin = 1000 + Σclosed.net − remaining open fees` resta corretta in split-fill, DCA, funding, stop/liquidazione, reset/archiviazione, dopo riavvio? Quali transazioni la invalidano?
3. **V1/V2 reframe:** `experiment_reframed` conserva il vecchio cash. Separare ID per epoca è sufficiente o va legata ciascuna epoca all'`experiment_id` e al suo `build_sha`? I check proteggono da false continuity, collisioni, riordino eventi?
4. **Safety SQLite:** uso `mode=ro&immutable=1` soltanto sulle copie ferme; rischio WAL non checkpointed? Verificare che la copia estratta sia coerente e che hash dei backup siano certificati fuori-host.
5. **Provenance / JSONL:** gestione `start_equity` presente solo nel trade_history, truncation `reason`, tipi float vs int, righe duplicate identiche, righe learning mancanti, scrittura parziale, cambi di run.
6. **Statistical learning:** questi controlli provano coerenza contabile, **non** progresso di apprendimento o profitto. Quali altri gate sono necessari per non presentare ipotesi AI come fatti?
7. **Controlli negativi:** proporre almeno 10 test avversari concreti che producano FAIL-CLOSED e distinguere bug bloccanti da ottimizzazioni.
8. **Import F1:** progettare l'import offline atomico in un DB V3 NUOVO, versionato, con double-run idempotente, rollback su mismatch, confronto cash per run, hash manifest di input e output, nessuna scrittura sul legacy. Specificare quali test/criteri PASS mancano prima di abilitare scritture.

## Output richiesto

Restituire: (A) verdetto **GO / NO-GO per sola implementazione importatore OFFLINE** — non approvazione deploy, (B) problemi P0/P1/P2 citando file+riga, (C) test mancanti e rischio residuale, (D) diff o patch suggerite in testo, **senza applicarle**, (E) suggerimenti per audit F0 backup esterno cifrato.

I tre portafogli V3 sono previsti **PAPER 1000/1000/1000** e non ancora creati. **Nessun merge, deploy o riavvio senza nuovo OK dell'utente.** `NO_TRADE` valido sempre; storico originale conservato.
