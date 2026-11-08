# RC84 — Classic RUNNING stop feed API/UI + Telegram post-commit (08/11/2026)

## Azione autorizzata e perimetro
Utente: «perfetto possiamo procedere..» dopo la review di RC82. ChatGPT ha sviluppato **solo su branch isolato**; nessuna autorizzazione merge/deploy/restart/reset/VPS, nessuna azione live/PAPER, nessun backup storico toccato.

**GitHub:** [PR #80 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/80), branch `cursor/rc84-running-stop-health-telegram-20261108`, base PR #79 RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`, HEAD iniziale PR `05935707b651de3e89fb35509ec708ad901ed282`. PR #77/#78/#79 restano Draft e i rispettivi branch non sono stati modificati.

## Interventi
1. `backend/v3/observability/classic_running_stop_health.py`: pura lettura del heartbeat del runner, discriminando `portfolio`, `exec_mode=paper`, heartbeat fresco (<=60s), ultimo ciclo concluso con esito OK entro 36m, schema `stop_feed` timeframe 15m, `bar_ms=900000`, `new_exposure.blocked_symbols` e per ogni posizione aperta status/checked. Restituisce `observed` solo per ultima osservazione, non «certificato»; gli altri stati `degraded/stale/unverified` sono fail-visible. `stop_certified=False`, `quote_coverage=False` sempre.
2. `backend/v3_api.py`: `_classic` sceglie stop health maintenance RC80 (exit_only) o running classic (heartbeat proprio) in base al worker/telemetria/posizioni. Nessuna API di mutazione.
3. `frontend/src/components/ClassicStopNotice.js`: presenta modello RUNNING 15m OHLC, scadenza/stato e blocchi nuovi ingressi, avvertendo che i controlli sono periodici ogni 15m scalp / 30m altri più la durata del ciclo, nessuna protezione stop exchange/tick-by-tick e wick della barra di ingresso non riprodotto. Con zero posizioni e feed bloccato l'allarme resta visibile. RC80 1m maintenance non altera testo.
4. `frontend/src/pages/Dashboard.js`: errore di Brain status/trades NON nasconde allarmi Falco/Toro già disponibili via `/api/v3/overview`; fallimento overview azzera vecchi health.
5. `frontend/src/pages/Overview.js`: ogni endpoint può fallire separatamente, l'overview dei classici resta se la risposta principale è valida; dati Brain mancanti mostrano avviso e non inventano PnL zero o autorizzano pulsanti manual-close.
6. `backend/desk/cli.py`: notifier Telegram «CHIUSO» dopo `_prove_protective_close` + `save_account` + `save_state`; errori notifier vengono ignorati senza rollback del conto.
7. Test backend/Jest: `backend/tests/test_v3_rc84_running_stop_health.py`; 3 regression test in `backend/tests/test_v3_rc82_active_paper_stops.py`; ampliati `ClassicStopNotice.test.js`, `Overview.test.js`, `ThreePortfoliosNavigation.test.js`.
8. Handoff nel branch RC84 `docs/v3/RC84-RUNNING-STOP-ALERTS-TELEGRAM-HANDOFF-20261108.md` con comandi suggeriti.

## Evidenza e limiti
- **Sorgenti scritti e PR Draft creata**, nessuna suite backend, frontend o build effettivamente eseguita da ChatGPT in questo incarico (runtime container senza accesso rete al repo GitHub privato). Non affermare PASS prima di test esterni su SHA esatto. Necessaria verifica indipendente offline e code review, possibile con Grok/Claude.
- La telemetria RUNNING è solo informativa; NON cambia strategia/rischio/SL/TP/cadenza 15/30 minuti/AI, e non garantisce stop intrabar. Non è il monitor RC80 di manutenzione.
- Brain RC83 code audit 4.849 PASS dichiarati Claude, ma worker di uscita non distribuito/certificato VPS. `--legacy-exits-disabled` è solo asserzione, non disabilitazione automatica: handover single-owner da verificare.
- Backup off-host/restore, UI browser autenticato, integrazione compatibilità RC74/RC82/RC84, VPS preflight READ-ONLY, deploy controllato, reset e nuova run PAPER 1000/1000/2000: ANCORA DA FARE con mandato distinto, storici preservati.

## Passo successivo
1. Assegnare a Grok/Claude collaudo OFFLINE su SHA PR #80, test mirati + regressioni e frontend completa + build, nessun file cambiato; restituire log, difetti, SHA.
2. ChatGPT verifica risultati e, se serve, correzioni minime sulla PR #80; no merge automatico.
3. Solo allora preparare piano preflight VPS read-only/backup/off-host e gate release, con consenso utente separato.

**No merge, no deploy, no VPS, no restart, no reset, no trading orders.**
