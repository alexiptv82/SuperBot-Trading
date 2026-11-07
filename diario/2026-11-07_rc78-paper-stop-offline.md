# RC78 — monitor PAPER di stop/take-profit, solo offline

**NON SINCRONIZZATO SUL RAMO CANONICO `diario`.**

Puntatore per un'altra AI: lo stato più nuovo di RC78 è questo file insieme a `docs/v3/RC78-PAPER-STOP-OFFLINE-HANDOFF-20261107.md`, sul branch `cursor/rc78-paper-stop-offline-31c4`. Il ramo canonico `diario` resta fermo al commit `85e84cc485001b9c81ff392c5668114034f73eac` (7 novembre 2026, 20:00:54 CET, checkpoint RC77). Questa voce è pronta da copiare lì, in coda, senza riscrivere la storia RC77.

## Base e pubblicazione

- Base di codice: `origin/work/v3-rc77-post-arb-close-backup-20261107` @ `52c21b5ea219bb864b8748ba1b2cfe109349a2e7` (7 novembre 2026, 19:59:08 CET). È il commit operativo dell'audit/backup RC77, non `main` (`fb38267433235780e5f22a335837139cf5ec4211`, 3 novembre) e non il diario.
- Branch di lavoro: `cursor/rc78-paper-stop-offline-31c4`. Non è stato modificato `main`, né il ramo `diario`, né i branch `work/v3-rc*`.
- Nessun deploy, merge, restart, ordine, nuova run, accesso VPS o `workflow_dispatch`.
- I workflow VPS nel commit RC77 partono solo su push di rami nominati (`work/v3-rc77-post-arb-close-backup-20261107`, altri `work/v3-rc*`, `rule-pool`, `main` con path di trigger). Nessuno ha un filtro `cursor/**` o un push senza filtro di branch. Questo branch non modifica file in `.github/workflows`.

## Decisione

Il worker `backend/desk/exit_only.py` della RC73, in manutenzione, consuma solo `close_position.flag` e `reset.flag`. I container legacy restano spenti, quindi `PaperAccount.on_bar` non gira. RC78 non riaccende quei container e non cambia strategia, size o leva.

La protezione è un opt-in spento di default: `DESK_PAPER_STOP_MONITOR=1` insieme a `DESK_MODE=paper`. L'import, l'avvio del processo e un eventuale deploy futuro non lo accendono. Quando è acceso, gira nello stesso lock dell'exit writer, dopo la chiusura manuale, con pausa obbligatoria e container legacy dimostrati fermi. Prezzo: chiusura 1m fresca entro 120 secondi, la stessa regola già usata dall'exit-only. Nessuna rete nei test; nessuna chiamata a Claude, Telegram o exchange nel percorso di protezione.

Priorità sul prezzo fresco, uguale a una barra degenere di `on_bar`: liquidazione, poi stop, poi take profit. Il fill e il netto passano da `PaperAccount._close`. Una seconda gamba pendente non viene eseguita, perché aggiungerebbe margine. Una richiesta manuale già in corso (`.work`) o un claim `paper_stop_protect.work` non vengono rieseguiti al restart.

## Liquidazione PAPER — confine, non nuova policy

La formula esistente non è stata cambiata. Per una chiusura `liquidazione`, il netto registrato è `-(margine + fee di apertura)` e il cash restituito è 0. Una chiusura manuale o a mercato oltre quel livello registra il netto pieno del gap, che può essere peggiore del margine (è il caso ARB del 7 novembre: uscita oltre lo stop e oltre la liquidazione teorica). I test confrontano i due esiti sullo stesso motore. Non è stata introdotta una nuova regola economica.

## Prove offline

Comando, dalla root del branch, senza rete e senza secret:

`PYTHONPATH=.:backend python3 -m pytest -q -p no:cacheprovider backend/tests/test_v3_rc78_paper_stop_monitor.py backend/tests/test_v3_classic_exit_only.py`

Risultato: **37 passed, 0 failed** (22 nel file RC78, 15 nella suite exit-only già presente). Prezzi sintetici in directory temporanee. Coperti: long/short stop e take profit, prezzo dentro la banda, pausa, live rifiutato, tick ripetuto, priorità della chiusura manuale, flag manuale scaduto, conflitto di lock, quote assenti/stale/nan/future, claim interrotto non rieseguito, opt-in spento, seconda gamba non riempita, gap oltre liquidazione con la policy già esistente.

## Cosa resta spento

- Backup esterno: all'audit RC77 delle 18:55 UTC il servizio risultava `exit-code`. Non è stato toccato.
- Brain: PR #74 solo offline, sidecar non deployato. Nessuna nuova run 1000/1000/2000.
- Questo monitor non è in esecuzione sulla VPS. Non c'è una nuova attestazione live dopo le 18:59 UTC del 7 novembre 2026.
- Attivarlo richiede un OK separato, la variabile esplicita sul processo già in pausa e i gate di backup. Non è pronto per la produzione.

## Prossimo passo, dopo OK

1. Copiare questa voce sul ramo canonico `diario` senza riscrivere RC77.
2. Non deployare il monitor insieme a quel copia-incolla.
3. Prima di una nuova run PAPER: backup esterno certificato, poi eventuale accensione esplicita del monitor sui soli processi exit-only già in pausa, con un audit read-only successivo autorizzato a parte.
