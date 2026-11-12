# Checkpoint 12/11/2026, 22:48 Europe/Rome — PR #92 collaudata localmente, HEAD f8332c9; PASS tecnico, non rilasciata

## Novità verificata

La [PR Draft #92](https://github.com/alexiptv82/SuperBot-Trading/pull/92), ramo `work/rc84-phase3-falco-short-only-20261112`, è avanzata da `fefa7ed...` a [`f8332c92cc2bc4edee3ea7363f71f15a0a37a816`](https://github.com/alexiptv82/SuperBot-Trading/commit/f8332c92cc2bc4edee3ea7363f71f15a0a37a816).

Stato GitHub verificato: PR aperta, Draft, non mergiata; base `dc98413ee555c7f0aefeeca8a5367b41ba370c92`; 4 commit, 4 file, +488/−19. Il nuovo commit è `[skip ci]`, co-firmato nella cronologia da Claude Opus 5.5. Nessuna GitHub Actions è stata avviata.

## Correzione minima introdotta

Il contatore heartbeat `hawk_short_only_long_dca_blocked` era cumulativo per la vita del processo, mentre gli altri contatori `hawk_short_only_*` sono per ciclo. Una prova con asserzione `>= 1` poteva quindi passare grazie a cicli precedenti.

Il commit:

- azzera il contatore a ogni ciclo PAPER Falco;
- rende la posizione di prova realmente idonea al DCA LONG (medio e prezzo sfavorevole);
- richiede `== 1`, così SHORT_ONLY è l'unica causa dimostrata del blocco;
- aggiunge controllo in modalità `BOTH`, dove lo stesso DCA LONG avviene.

## Collaudo locale riportato e fonte

Fonte primaria: commit `f8332c9...` e documento versionato `docs/v3/RC84-FASE3-FALCO-SHORT-ONLY.md`. La suite non è stata rieseguita da questa automazione; sono registrati i risultati presenti nel commit/documento.

| Esecuzione | Esito riportato |
|---|---:|
| Fase 3: prove iniziali 12 + collaudo 12 | **24/24 PASS** |
| Suite backend Python 3.13, esclusi 2 moduli SQLAlchemy | **7.063 ok / 1 fail** |
| Fail residuo | lo stesso `test_v3_rc84_import_paths`, SQLAlchemy 2.0.28 + Python 3.13 |
| Moduli SQLAlchemy, Python 3.11 | **49/49 PASS** |
| Replay default `BOTH` | 42 percorsi identici alla base `dc98413` |

Le 12 prove aggiuntive attraversano il ciclo vero e verificano:

- Claude `open_long` e `open_long_split` rifiutati e registrati come candidate;
- Claude `open_short_split` ammesso;
- nessuna trasformazione forzata LONG→SHORT;
- LONG residua ancora chiudibile via stop, TP, parziale e decisione di chiusura;
- modalità `BOTH`: DCA LONG e seconda gamba LONG restano possibili;
- DCA SHORT ammesso in SHORT_ONLY;
- Toro resta bidirezionale;
- S25 non apre su Falco neppure con autorizzazione Toro presente nell'ambiente di test.

Il documento dichiara inoltre invariati rispetto a `dc98413`: `brain.py`, `engine.py`, `long_s25.py`, `signals.py` e tutto `backend/v3`.

## Desiderato, implementato nel candidato, installato

- **Desiderato:** Falco scalp SHORT_ONLY reversibile; Toro Claude medio LONG/SHORT; Brain AI autonoma; PAPER soltanto.
- **Implementato e collaudato nel ramo:** gate Falco SHORT_ONLY, candidate shadow, protezione LONG residue, contatori per ciclo e test sopra descritti.
- **Installato/rilasciato:** nulla. L'interruttore non è presente nelle unità systemd e la sorgente VPS documentata resta `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`.
- **Invariato:** Toro, Brain, LIVE, capitale, leva, equity floor 450, SL/TP, funding, limiti, dashboard e servizi.

## Stato operativo, backup e chiavi

Ultimo stato operativo documentato, non controllato live in questa esecuzione: Falco/Toro `draining`, Brain `paused`, Brain exit `healthy`; tre pause e resume non autorizzato.

Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato. Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore VPS. RC84 PR #80 resta riferimento storico. Nessun segreto letto o pubblicato.

## Blocker e gate residui

La PR resta Draft e non è ancora release-ready senza:

1. revisione indipendente del commit esatto `f8332c9...`;
2. verifica futura che `DESK_S25_TORO_ENTRY_APPROVED` non sia attivo;
3. decisione sulle policy TP/R:R, guardrail di margin/leverage ed equity 450, ancora `POLICY_SHADOW`;
4. verifica read-only Bitget/filtri 4H e calendario XAU/XAG;
5. backup/rollback, preflight PAPER e opt-in unit Falco separata, senza rimuovere pause;
6. collaudo Brain dedicato, con NO_TRADE valido.

## Eseguito / preparato / rilasciato / ripresa

- **Eseguito:** collaudo locale documentato, correzione contatore per ciclo, 12 prove aggiuntive, suite e replay riportati.
- **Preparato:** PR Draft #92 all'HEAD `f8332c9...`.
- **Rilasciato/installato:** nulla.
- **Non approvato/non eseguito:** merge, deploy, Actions, modifica VPS/systemd/pause, restart/resume, reset, wallet, ordini, LIVE o API a pagamento.

Riprendere dalla PR #92 all'HEAD `f8332c92cc2bc4edee3ea7363f71f15a0a37a816`. Prima di qualunque proposta di rilascio, eseguire revisione indipendente sul commit esatto e chiudere i gate residui. Preservare PAPER, storici, learning ed EventJournal.

