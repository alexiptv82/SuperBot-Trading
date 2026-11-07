# SuperBot V3 — RC #62 checkpoint operativo: Brain 2.000, Falco/Toro 1.000 PAPER

**Data:** 6 novembre 2026. **Stato:** sviluppo e preparazione isolata; **NO-GO per sbloccare i bot**. Nessun trading LIVE.

## Capitale approvato dall'utente
| Run nuova | Capitale iniziale | Perimetro | Stato |
|---|---:|---|---|
| Falco | 1.000 USDT | PAPER, indipendente | Nuovo storage e worker **non ancora creati/avviati** |
| Toro | 1.000 USDT | PAPER, indipendente | Nuovo storage e worker **non ancora creati/avviati** |
| Brain | **2.000 USDT** | PAPER, indipendente | Preparato sulla VPS, **in pausa**, mandato NON approvato |

I vecchi dati sono storici: Falco 6 posizioni e Toro 2 ancora registrate aperte nelle run legacy fermate. Non sono posizioni della nuova V3; non chiudere, azzerare o importare queste posizioni nel nuovo capitale.

## Brain: risultato verificato direttamente nella VPS Singapore
- Run PAPER nuova: `/opt/superbot-v3-paper-runs/brain-v3-rc20261106`.
- Runner e servizio EXIT sono **spenti**; validatore read-only `exit_worker --validate-only` ha confermato la run.
- `journal.db`, `budget.db`, `runner_config.json`, `mandate.json` con `approved=false`, `pause.flag`, `PREPARED_PAUSED_ONLY.json` sono nella nuova directory (verifica del workflow dedicato, non assunzione).
- Il profilo `backend/v3/runner/runner_config_brain2000_paper.json` differisce dal default da 1.000 **soltanto** per il campo `initial_equity: 2000`.
- Nuovo `prepared_config_guard.py`: il runner split e il servizio EXIT rifiutano l'avvio con profilo da 1.000 su run preparata da 2.000; non altera le vecchie run sintetiche senza marker.
- **Limiti invariati**: rischio singolo 2% (= 40 USDT del capitale iniziale), rischio aperto 5% (= 100 USDT), margine massimo per posizione 10% (= 200 USDT), margine totale 30% (= 600 USDT), minimo equity 450 USDT. Avviso giornaliero 35%, stop 50%. Le perdite effettive dipenderanno da equity aggiornata, stop, costi e quote del motore; non interpretare questi importi come perdita garantita.

## Classici: integrazione codice su RC, nessun restart
- Da PR #58 integrato `backend/desk/long_s25.py` + golden fixture/test, collegamenti S25 a `desk/cli.py`. S25 **OFF** senza `DESK_LONG_S25=1`.
- Da PR #59 integrato comando `close_position.flag` per singolo trade PAPER, con stato esito in `state_v2.json` e capability `close_position` nel battito.
- L'integrazione è stata adattata all'attuale `desk/cli.py` V3, preservando la logica preesistente di **chiusura LIVE**; il comando singolo nuovo rifiuta il LIVE. Non creare un secondo writer.
- La richiesta di preparare automaticamente le nuove directory Falco/Toro è stata bloccata dai controlli di autorizzazione: **NON ESEGUITA**, non considerare i due portafogli pronti alla partenza.
- Lo storage di Falco/Toro dovrà essere **nuovo**, in pausa, indipendente da `/opt/superbot-desk-data/hawk` e `/opt/superbot-desk-data/bull`. `desk.cli` usa `PaperAccount(Limits(start_equity=1000))` se `state_v2.json` non esiste, ma verificare i limiti effettivi con il ramo RC e il comando di avvio prima di eseguire worker.

## VPS: altri fatti verificati
- Container web `superbot` già PAPER, in esecuzione e con restart policy `always`. Attualmente **monta le vecchie directory** Hawk/Bull/Brain. Per la dashboard V3 serviranno mount nuovi, percorsi ambiente nuovi e smoke-test della sessione.
- Container legacy `superbot-desk-hawk`, `superbot-desk-bull`, `superbot-brain-free` sono fermi con restart policy `no`, come risultava dall'ultimo inventario.
- Backup manuale con verifica tar, SQLite e prova restore: `/opt/superbot-backups/rc-v3-20261106T150730Z`, preservato.
- `superbot-extbackup.service` risulta FAILED: il backup esterno ricorrente **non va presentato come funzionante**; diagnosticare e ripristinare prima del rilascio definitivo.

## Gate rimasti da completare, in ordine
1. CI della RC comprensiva dei test per classici, frontend e V3. Il benchmark di profitto **non** è un gate pre-avvio; stop/contabilità/recovery sì.
2. Preparare senza reset **due directory nuove in pausa** per Falco/Toro; verificate in PAPER con 1.000 USDT e stato iniziale vuoto. Backup degli storici immutabile.
3. Installare/sorvegliare il sidecar EXIT Brain su nuovo volume; **un solo owner** OPEN/CLOSE, test arresto/restart, lettura heartbeat, manual-close, stop durante AI lenta.
4. Preparare container Falco/Toro da sorgente RC, isolati, senza API/credenziali LIVE né Anthropic; confermare regime rules-only e policy. Non avviare vecchi container.
5. Collegare dashboard web ai **nuovi percorsi**, mai agli storici, preservando il web esistente fino al cutover. Test sessione da browser/telefono.
6. Riparare `superbot-extbackup.service`; confermare backup esterno e rollback. Solo a gate superati, approvare mandato Brain per run esatta, e rimuovere `pause.flag` delle run nuove con monitoraggio PAPER.
7. Nessun merge su `main` / `rule-pool` o riavvio legacy non controllato. Tutto SHADOW/optional (scanner, quality monitor, S25) resta OFF salvo comando consapevole.

**Decisione attuale: Brain 2k PREPARATO, Falco/Toro RC CODICE INTEGRATO, rilascio operativo ancora NO-GO.**
