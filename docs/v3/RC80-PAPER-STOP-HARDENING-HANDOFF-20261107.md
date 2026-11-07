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
