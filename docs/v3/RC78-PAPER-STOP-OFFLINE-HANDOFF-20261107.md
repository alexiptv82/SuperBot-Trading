# RC78 handoff — protezione PAPER di stop, solo offline

**Leggi prima il puntatore** `diario/2026-11-07_rc78-paper-stop-offline.md` su questo stesso branch. Quel file è la voce di diario. **Non è sul ramo canonico `diario`.**

## Dove siamo

| Pezzo | Ref | Stato |
|---|---|---|
| Codice base | `52c21b5ea219bb864b8748ba1b2cfe109349a2e7` su `work/v3-rc77-post-arb-close-backup-20261107` | Ultimo commit operativo RC77, 7 novembre 2026 19:59:08 CET |
| Diario canonico | `85e84cc485001b9c81ff392c5668114034f73eac` su `diario` | RC77 alle 20:00:54 CET. Non aggiornato da questo lavoro |
| `main` | `fb38267433235780e5f22a335837139cf5ec4211` | 3 novembre 2026. Non è la base di RC78 |
| Questo lavoro | branch `cursor/rc78-paper-stop-offline-31c4` | Offline. Nessun merge, nessun deploy |

RC77 resta il fatto operativo precedente: audit [42403639118](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42403639118) alle 18:55 UTC con Falco 0 e Toro 0 PAPER, Brain in pausa; backup locale [42403863492](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42403863492) e verifica [42403956859](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42403956859) PASS; backup esterno ancora `exit-code`. Nessuna di quelle run è stata ripetuta qui. Non esiste un'attestazione VPS nuova.

## Perché questa base

`main` non contiene l'exit-only RC73 né lo stato RC77. Il ramo `diario` non contiene il codice. I branch `work/v3-rc*` sono la linea che ha davvero girato gli audit. RC78 parte dall'HEAD RC77 e non riscrive quei branch: il diff contro `52c21b5` è solo il monitor, i test e questi documenti.

Integrazione: la protezione è chiamata da `ExitOnlyWorker.tick` dopo le chiusure manuali, solo se l'ambiente vale esattamente `DESK_PAPER_STOP_MONITOR=1` e `DESK_MODE=paper`. Senza quella variabile il tick resta quello della RC73. Non c'è un secondo processo e non c'è un workflow nuovo.

## Sicurezza del publish

Nel tree RC77 ogni workflow che parla con la VPS ha il branch scritto per intero (`work/v3-rc77-post-arb-close-backup-20261107`, altri `work/v3-rc*`, `rule-pool`, oppure `main` più un path `deploy/*.trigger`). Non c'è un `push` senza filtro di branch e non c'è un glob `cursor/**`. I `pull_request` di quel tree puntano a `main` (solo path della dashboard Brain) o a `work/v3-brain-f2-grok`. Questo branch non modifica `.github/workflows`. La PR, se aperta, ha come base il branch RC77, così il diff non è il salto enorme verso `main`.

## File

- `backend/desk/paper_stop_monitor.py` — decisione e apply, inerti all'import.
- `backend/desk/exit_only.py` — hook opt-in nello stesso lock; rifiuto di avvio se esiste `paper_stop_protect.work`.
- `backend/tests/test_v3_rc78_paper_stop_monitor.py` — prezzi sintetici, fixture temporanee.
- `diario/2026-11-07_rc78-paper-stop-offline.md` — voce pronta per il diario canonico, non ancora copiata.

## Comportamento verificato dai test

Comando eseguito in locale:

`PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider backend/tests/test_v3_rc78_paper_stop_monitor.py backend/tests/test_v3_classic_exit_only.py`

**37 passed, 0 failed** (22 RC78 + 15 exit-only esistenti). Nessun failed rimasto.

Il monitor spento non chiude uno stop già attraversato e non interroga il feed. Acceso, chiude long e short su stop e take profit, ignora il prezzo interno alla banda, rifiuta pausa assente e `DESK_MODE=live`, non duplica il tick successivo, lascia la priorità alla chiusura manuale, scarta un flag manuale vecchio e poi applica lo stop, si ferma se il lock di directory è occupato o se un `.work` manuale è da riconciliare, non ripete un claim interrotto, non esegue la seconda gamba e non modifica `lessons.md` né `errors.md`. Lo storico e il learning crescono solo in append.

## Liquidazione

`liq_price` e `_close` non sono stati modificati. Il test mostra che un gap oltre la liquidazione, chiuso come `liquidazione`, registra `-(margine + fee di apertura)`, mentre la stessa uscita come chiusura manuale a prezzo di gap registra una perdita più grande del margine. È il comportamento già in `backend/desk/engine.py`. RC78 lo riusa quando il prezzo fresco ha superato `liq`. Non definisce una policy nuova.

Limite noto: il monitor usa l'ultima chiusura 1m valida, non il massimo/minimo di una barra 15m. Un wick già rientrato non fa scattare lo stop. La manutenzione RC77 era un prezzo rimasto oltre lo stop per giorni: quello è il buco coperto, non il wick intra-bar.

## Gate ancora aperti

- Non è in produzione e non va deployato solo perché i test locali sono verdi.
- Backup esterno non riparato.
- Brain PR #74 non deployata. Nessuna run nuova.
- Accensione sulla VPS: solo con OK esplicito, processi legacy fermi, pausa presente, opt-in sul processo exit-only, e un audit successivo autorizzato. Questo handoff non è quell'autorizzazione.
