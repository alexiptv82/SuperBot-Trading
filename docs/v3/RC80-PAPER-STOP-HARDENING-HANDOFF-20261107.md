# RC80 handoff — protezione PAPER verificabile, ancora spenta

Leggi prima `diario/2026-11-07_rc80-paper-stop-hardening.md` su **questo** branch. Il ramo canonico `diario` non contiene RC80.

## Identità

| | |
|---|---|
| Branch | `cursor/rc80-paper-stop-hardening-31c4` |
| Parte da | PR #75 `b6eaa173c12c241647f89f730e1430a841cade3a` (`cursor/rc78-paper-stop-offline-31c4`) |
| Quella base parte da | RC77 `52c21b5ea219bb864b8748ba1b2cfe109349a2e7` |
| PR prevista | bozza verso `cursor/rc78-paper-stop-offline-31c4`, non verso `main` |
| Diario canonico | non toccato, `85e84cc485001b9c81ff392c5668114034f73eac` |
| PR #76 e #74 | non modificate |

Il nome `work/v3-rc80-...` dell'incarico non è stato usato: i workflow VPS del tree scattano su nomi `work/v3-rc*` esatti. Questo branch `cursor/` non coincide con nessun filtro `push` o `pull_request` letto nel tree (89 workflow). Nessun file in `.github/workflows` è stato modificato.

## Cosa è cambiato

`backend/desk/paper_stop_monitor.py` e il tick di `backend/desk/exit_only.py`.

`stop_protection` nel heartbeat:

- `off` — opt-in assente
- `unverified` — processo appena partito, nessun prezzo ancora letto
- `idle` — opt-in acceso, nessuna posizione
- `covered` — ogni posizione aperta ha una barra 1m fresca e coerente
- `partial` — solo una parte
- `blind` — nessuna
- `blocked` — claim, lock o chiusura manuale da riconciliare

`ready` continua a voler dire che il worker di chiusura manuale è in piedi. Non significa che gli stop siano coperti.

Una barra è fresca solo se timestamp, open, high, low e close sono numeri finiti, il close è dentro high/low, il timestamp non è nel futuro ed è entro 120 secondi. Il timestamp è l'apertura della candela. Il wick non è un prezzo di chiusura.

## Liquidazione, non una policy nuova

`liq_price` e `_close` sono quelli di `backend/desk/engine.py`. Priorità sul prezzo fresco: liquidazione, stop, take profit, come `on_bar` su una barra degenere. La liquidazione registra `-(margine + fee di apertura)`. Una chiusura manuale o di stop oltre quel livello può registrare una perdita più grande del margine, mentre il cash restituito non scende sotto zero. RC80 non cambia questi conti. Lo documenta e lo testa.

## Prove

Solo locali:

`PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider backend/tests/test_v3_rc80_paper_stop_hardening.py backend/tests/test_v3_rc78_paper_stop_monitor.py backend/tests/test_v3_classic_exit_only.py`

**56 passed, 0 failed.** Nessuna run di GitHub Actions è stata lanciata da questo branch. Non citare una CI verde.

## Rischi aperti

- Il percorso manuale non usa `classify_candle`. Una candela numericamente recente ma OHLC incoerente può ancora chiudere una richiesta manuale.
- `mismatch` non si ripara da solo.
- Età misurata sull'apertura della barra, non sull'ultimo trade.
- Il wick intra-bar non chiude.
- Se la scrittura di `paper_stop_health.json` fallisce, lo stato di quel tick resta nel valore ritornato ma il processo successivo può non vedere la transizione.
- Il controllo del lock via `/proc/self/fd` è quello di Linux.
- Backup esterno non certificato. Brain non deployato. Nessuna attestazione VPS dopo RC77.
- Opt-in spento di default. Non deployare e non accendere.

## Review `6713923063` — patch sullo stesso branch

Parent review: `9dedf5dc9ea0586e854afc59ebc050f9574f62c0`.

- **P0-A** `_prove_writer_lock`: il path non basta. Il test `test_open_but_unlocked_fd_is_not_ownership` apre l'fd senza flock mentre un altro processo tiene `LOCK_EX` e deve ricevere `ownership_lock_required` senza chiudere.
- **P0-B** chiave `symbol + id + open_ms`. I parziali (`partial` o motivo con «parzial») non sono chiusure terminali. `resolved` richiede anche il learning. Claim senza `open_ms`: `unproven`.
- **P1-C** non è un cambio di `_close` né di leva/size. Ammissione dati: barra 1m chiusa soltanto. Wick documentato come non-fill. La dashboard non mostra ancora questo limite.
- **P1-D** errore di scrittura health → `telemetry_failed`, nessuna chiusura, nessuna dichiarazione `covered`. `stop_certified` è sempre false. `protection_alarm` è il lettore fail-visible. UI non toccata: gate residuo prima di qualunque attivazione.

Il diario canonico non va aggiornato da questo branch.

## Review `6720701115` su `b64519346cbe0c928cd29d3e9d57c619b472ac78`

P0-E: `find_same_closure` accoppia una riga di `trade_history.jsonl` e una di `learning_log.jsonl` con lo stesso `close_ms`, `why` e numeri economici. Due `close_ms` o un netto diverso non risolvono il claim.

P0-F: `assess_restart` è in sola lettura. Lo snapshot passato al worker non viene riscritto né usato per rimettere una posizione chiusa. La discendenza è append-only più una chiusura provata per ogni posizione sparita. `publish_recovery_snapshot` scrive un manifesto nuovo accanto, con hash dell'antenato e dei file correnti. Corruzione o antenato diverso bloccano l'avvio. Un manifesto assente, se la discendenza torna, non toglie la protezione alla posizione rimasta.

Prova locale del caso a due posizioni: BTC chiuso, ETH aperto, byte del backup uguali prima e dopo il restart, seconda chiusura di ETH possibile. Non è CI GitHub.

## Review `6720918518` su `34a4abe6ac80b5d65bfc12fbfdbe40d131124b4d`

`terminal_closure_status` non accetta una coppia buona se nello storico o nel learning esiste un altro terminale diverso per la stessa `symbol/id/open_ms`. Duplicati identici restano. I file non vengono ripuliti. Il restart con quel conflitto risponde `close_not_proven` e non tocca il backup.
