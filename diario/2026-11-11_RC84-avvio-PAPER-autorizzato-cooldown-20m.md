# 11/11/2026 — APPROVAZIONE UTENTE avvio 3 wallet PAPER + mandato Brain, cooldown sul server 20m ARMATO

## Stato effettivo alle 15:39 UTC (~16:39 Europe/Rome)

**L'utente ha autorizzato esplicitamente** l'avvio di Falco, Toro e Brain V3 esclusivamente PAPER, compresa l'approvazione del mandato simulato Brain; Fable 5.2 rimane OFF. Non è autorizzato alcun LIVE. Non modificare storici, capitali/rischio, release Fable o merge.

**Prova sul server Singapore, SUCCESS:** [GitHub Actions #43050477011](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43050477011). Verificato direttamente via SSH, registrato in log:
```
PAPER_PRESTART_THREE_WALLETS_PAUSED=PASS
PAPER_PRESTART_RC84_CODE_AI_AND_RISK=PASS
PAPER_PRESTART_BRAIN_EXIT_AND_MANUAL_CLOSE=PASS
PAPER_PRESTART_FABLE_DISABLED=PASS
PAPER_PRESTART_CLASSIC_AND_BRAIN_CAPITAL=PASS
PAPER_BRAIN_MANDATE_APPROVED_USER_AUTHORIZED=PASS
PAPER_THREE_PAUSE_FLAGS_STILL_PRESENT=PASS
PAPER_20_MINUTE_STARTUP_COOLDOWN_ARMED=PASS
PAPER_FABLE_REMAINS_OFF=True
PAPER_NO_ORDERS_YET=True
RC84_APPROVED_BRAIN_MANDATE_AND_20M_TIMER=PASS
```

**Importante:** questi log certificano **mandato Brain approvato + timer attivato**, NON che i tre siano già RUNNING. Il rilascio delle pause è pianificato sulla VPS **non prima di 20 minuti** dalla creazione del timer (circa 15:59 UTC / 16:59 Europe/Rome). Le aperture eventuali successivamente saranno solo PAPER, non garantite; NO_TRADE valido. La VPS riesamina tutte le protezioni al momento dell'attivazione e sblocca progressivamente Falco→Toro→Brain. Se healthcheck, proprietario exit, modello, limite di rischio, dir, PIN, PID, capitale, socket/web read-only o intervallo falliscono, rifiuta e lascia/ripristina pause.

## Identità/rischio e configurazione confermati

- Falco: NUOVA run `/opt/superbot-v3-paper-runs/classic-hawk-paper20261111`, capitale 1000 PAPER, chiave Claude presente in processo e nuova chiave confermata dall'utente con Termius.
- Toro: NUOVA run `/opt/superbot-v3-paper-runs/classic-bull-paper20261111`, capitale 1000 PAPER, chiave Claude in processo.
- Brain: NUOVA run `/opt/superbot-v3-paper-runs/brain-v3-paper20261111`, capitale 2000 PAPER, DeepSeek in processo; min20/max50 leva, floor450, max margin/trade 20%=400, risk open 12%=240, max margin totale55%, loss/margin 0.214285714... e ciclo 60m.
- Brain `mandate.json` è stato aggiornato **atomicamente** a `approved=true`, `approved_by=user-authorized-PAPER-2026-11-11` mantenendo intatta la firma `policy_hash` **a 16 cifre** secondo l'implementazione reale `BrainEngine._policy_hash`. Originale salvato in area privata del controller. I file preparatori `PREPARED_PAUSED_ONLY.json` sono storici; non vanno aggiornati per dichiarare uno stato operativo.
- Split exit-sidecar Brain e quattro unità V3 in servizio, vecchi classic container non in esecuzione; servizi legacy exit-only invariati. Web pubblica RC84 con «Chiudi ora» singolo PAPER su Falco/Toro/Brain, START/RESET/CLOSE_ALL ancora 423, tutti e tre data mount web `:ro`; nessuna modifica al frontend in questa fase.
- Fable 5.2 PR #82 separata, solo staging non attivo; né chiavi Anthropic sul processo Brain né flag Fable abilitati.
- Nessuna chiamata modello in fase preflight/mandato/timer, nessun ordine LIVE o PAPER emesso dall'azione di arming.

## Verifiche e correzioni

- Primo preflight [#43049910320](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43049910320) rifiutato correttamente **senza mutazioni di mandato/pausa**: l'operatore aveva ipotizzato erroneamente una firma SHA256 di 64 caratteri, mentre il motore usa il prefisso SHA256 di 16 caratteri. Corretto il controller per verificare la firma **esatta** calcolata sui parametri risk e riprovato.
- Secondo preflight [#43050205825](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43050205825) SUCCESS, con conferme PAPER/chiavi/risk/exit/conti, senza modifiche.
- Script root-private staged sotto `/opt/superbot-v3-paper-activation-20261111/activate.py`, dal ramo `work/rc84-paper-authorized-activation-20261111`, commit pinned `6aa8275496f43fcecc80ba1e0e9fc448d70379a8`, blob `287036c44d4f7b56b5fe14a822b5360644259dae`.
- Stato persistente root-only `/opt/superbot-v3-paper-activation-20261111/activation-state.json` (inizialmente `mode=armed_pause`), copia root-only mandato originale `original-brain-mandate.json`.
- Timer `superbot-v3-paper-authorized-unpause-20261111.timer` creato con `systemd-run --on-active=20min` eseguirà `python3 -I .../activate.py --unpause` come service one-shot. Controlla differenza oraria >= 20m e <= 90m, stato, identità dei PID e tutti i gate; ciascun wallet deve confermare heartbeat RUNNING entro finestra limitata, altrimenti vengono ripristinate pause e revocata l'approvazione del mandato per interrompere nuove aperture. Non forza chiusure delle posizioni eventualmente aperte: exit worker continua a gestirle.
- **Fermata d'emergenza autorizzata:** da SSH root, `python3 -I /opt/superbot-v3-paper-activation-20261111/activate.py --emergency-pause`, ferma timer se in attesa, riporta i tre `pause.flag` e `approved=false`, non chiude d'autorità posizioni aperte. Il pulsante «Pausa» della web resta volutamente disabilitato finché `V3_CUTOVER_READONLY=1`: non dire che l'utente possa usarlo dall'app!
- **Automazione ChatGPT di verifica una tantum:** `6af48c99fcec819190cd468c506523e7`, prevista intorno alle **17:11 Europe/Rome**, controlla effettivo esito timer e heartbeat via GitHub, non modifica trade o servizi. Workflow read-only creato su main `.github/workflows/rc84-paper-postcooldown-readonly.yml`; è attivato creando solo `deploy/rc84-paper-postcooldown-readonly.trigger` al momento della verifica. Non inventare successo in anticipo.

## Attività successive

1. Dopo scadenza cooldown, **verificare prova reale**: `activation-state.json mode=paper_running`, `pause.flag` assenti su tutti e tre, heartbeat `running` e fresco, exit service healthy, Brain `mandate.approved=true`, codice attivo RC84, Fable OFF, web chiusure singole.
2. Verificare numero effettivo PAPER OPEN/CLOSE, esposizione, protezione 450, cash/equity e uso AI senza pubblicare credenziali; non forzare slot.
3. Quando l'utente trova la prima posizione PAPER aperta e decide di chiuderla con «Chiudi ora», controllare esattamente un esito nel journal, storico e apprendimento, nessun ordine reale.
4. Non chiamare avvio definitivo prima di evidenze RUNNING. Non installare Fable, non fare merge/azioni LIVE.

L'azione di avvio futuro è demandata **al timer già effettivamente creato sulla VPS**; non è un'attività ChatGPT eseguita retroattivamente. Checkpoint aggiornato per ripresa chat.
