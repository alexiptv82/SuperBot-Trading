# 2026-11-07 — Manual close PAPER, profit protection evidence, legacy run release gate

## Richiesta operativa dell'utente
- Possibilità di **chiudere ogni singolo trade** manualmente da dashboard per Falco, Toro e Brain, indipendentemente dalla strategia d'ingresso.
- Le chiusure manuali in profitto devono diventare **esempi riconoscibili di profit-taking** per la futura analisi AI ("accettare un profitto sufficiente") e non sparire come stop o TP meccanici.
- Utente segnala posizioni ancora aperte da circa 4 giorni con alto P&L visibile; desidera incassare e poi nuove run PAPER **Falco 1000 / Toro 1000 / Brain 2000 USDT**, storico preservato.

## Verifica codice — prima del miglioramento
- **Classici** `backend/desk_view.py:command_close_position` e `backend/desk/cli.py:_check_close_position_flag` supportano il comando su singola posizione anche con `pause.flag`, **a condizione che il worker compatibile giri**. Le richieste scadono dopo 10 min. `_close_for_user` scrive `closed_by="utente"`, record di trade nel JSONL e log di apprendimento.
- Il classico `close-all` scriveva nel trade `why="chiusura manuale"`, ma **senza `closed_by="utente"`** nel percorso PAPER.
- `_market_prices` leggeva, se il feed falliva, `last_prices` senza verificarne l'età. Quando un bot è fermo da giorni questo rischia un P&L PAPER inventato. Non inviare un comando di close-all a un worker storico senza verifica.
- **Brain**: API `POST /api/v3/brain/close`, conferma singola oppure tutte, il worker gestisce `close_request.json` anche in `pause` quando è in esecuzione; `close_paper(reason="manual")` scrive journal append-only con prezzo, quantità, fees, P&L, regime/strategy label; outcome `is_manual=True`. Non è una modifica del modello. Il `brain_view/view.py` **esclude** i trade manuali dal suo scoreboard di strategie autonome: scelta corretta per non attribuire all'AI il timing dell'utente, ma occorre un'analisi separata per apprendere il compromesso di profitto.

## Migliorie isolate PR #62 (NO DEPLOY)
Commits per questa richiesta fino a `447a9536311a50a8439a8d6f2bea98a2c70acf6d`:
- `5efcdcca`: `_market_prices` verifica timestamp e prezzo finito/positivo: candela 15m recente (<=30min), ultimo prezzo cached (<=2min). Una chiusura su prezzo stale/non valido NON viene eseguita. `_close_for_user` etichetta `manual_learning=profit_protection_example | loss_reduction_example | break_even_example` dal P&L NETTO, oltre a `closed_by=utente`. Il close-all PAPER usa lo stesso percorso della chiusura individuale. I percorsi LIVE conservano l'attuale gestione ordini.
- `e728806`: il normalizzatore storico classici espone l'etichetta.
- `47b9c44`: API V3 espone l'etichetta per le chiusure classiche e la DERIVA da `is_manual` + net PnL per Brain, SENZA modificare journal/decisioni o chiamare AI.
- `107b97f`: la dashboard mostra "Profitto protetto manualmente · esempio per AI, non strategia convalidata".
- `789d6bc`: prova di prezzo stale di 4 giorni e controllo prezzi positivi/validi; assert close-all PAPER conserva `closed_by` e label.
- `f0f2529`: test Brain manual positive vs negative/breakeven, senza confondere il `strategy_id` dell'apertura.
- `447a953`: regression tests UI per etichette su classici e Brain.
- **CI HEAD `447a953`** run `42353201748`: backend SUCCESS, frontend SUCCESS, suite V3 **4075 PASS, 1 SKIP**, job classics-rc ancora in progress al momento del checkpoint. NON inventare successo totale finché non finisce.

## Limiti importanti / prima della chiusura effettiva
- **NON SONO STATE CHIUSE POSIZIONI e NON SONO STATI MODIFICATI FILE DELLA VPS.** La verifica di profitto è la segnalazione dell'utente, non un prezzo attuale confermato dal sistema. Ultimo audit Singapore 6 novembre: workers Falco/Toro exited, `pause.flag` esistenti; vecchie 6 posizioni Falco e 2 Toro ancora OPEN. La dashboard web è ancora vincolata ai volumi legacy e non alle nuove run.
- Backup esterno cifrato servizio `superbot-extbackup.service` **FAILED**, ultimo successo documentato 2 novembre, benché il backup locale e restore rehearsal delle vecchie 6+2 siano PASS. Questa è una condizione **NO-GO** per mutate dati e liberazione di run.
- Prima di chiudere le vecchie posizioni occorrono: riparazione backup esterno e restore in percorso isolato; inventario corretto dei trade ancora effettivamente aperti, quotazioni fresche certificate, prova che solo un worker gestisca le uscite e che non apra mai nuovi trade; chiusure una per volta/serializzate con esito richiesto e P&L riconciliato, archiviazione vecchio run e snapshot POST-close. NON scrivere `close_position.flag` se i workers sono spenti o non compatibili; NON accendere vecchi bot, NON azzerare la run legacy in-place.
- La nuova run usa directory distinte: Falco 1000, Toro 1000 con **Claude + SHORT invariati, S25 LONG e segnale trend**; Brain 2000 PAPER con profilo rischio singolo 75 su350 margine, totale 12%/55%, leva20–50, floor450, mandato unsigned, PAUSED. Storico precedente disponibile in sola lettura per studio. Integrazione Brain con memoria classici da verificare separatamente.
- Per una vera strategia AI di "profitto sufficiente" servono dati dopo l'uscita (`post-exit`), confronto osservativo con l'alternativa HOLD, regimi e costi, e test walk-forward SHADOW. Il solo profitto manuale positivo **non prova** che chiudere fosse la scelta migliore né deve forzare uscite future.

**Stato:** feature e protezione sviluppati su PR DRAFT; CI parzialmente verificata; VPS PAUSED e NO-GO per close/reset/start fino ai gate di sicurezza.
