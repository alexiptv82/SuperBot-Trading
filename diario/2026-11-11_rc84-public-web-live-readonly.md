# 11 novembre 2026 — RC84 DASHBOARD WEB PUBBLICA LIVE, trading PAPER ancora PAUSED

**RILASCIO ESEGUITO E VERIFICATO:** [GitHub Actions run 42986928313](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42986928313), job 130410205110 completed SUCCESS, SHA trigger `134ef3cd67280c5f5182d59086e0eb1151f35e96`. Date UTC esecuzione 2026-11-11 08:25:32–08:25:59 (09:25 circa Europe/Rome). Eseguito **su autorizzazione esplicita dell'utente** a pubblicare la dashboard RC84 senza apertura trade; utente ha confermato che non c'erano posizioni aperte.

## Esito reale, non un semplice piano
- **RC84 è stata pubblicata sulla dashboard web già utilizzata**, backend PINNED `0e29a73a36f668643da4088178bacb8616a45ac0`, frontend dell'anteprima RC84 corrispondente; backend API e frontend ora allineati.
- Log verificati: `RC84_PUBLIC_ROLLBACK_PREFLIGHT=PASS`, `RC84_PINNED_PUBLIC_CANDIDATE_READY=True`, `RC84_AUTH_SQLITE_BACKUP_AND_RESTORE_CHECK=PASS`, `RC84_NEW_PAPER_WEB_GATES=PASS`, `RC84_PUBLIC_WEB_ROLLOUT=PASS`, `RC84_NEW_PAPER_RUNS_VISIBLE_UNDER_AUTH=True`, `RC84_NO_PAPER_UNPAUSE_OR_PROVIDER_CALLS=True`, `RC84_OLD_RC73_WEB_RETAINED_FOR_ROLLBACK=True`.
- Database di autenticazione originale salvato con backup SQLite + `integrity_check` e verifica apribilità, senza mostrare password/token in log. L'originale resta il DB usato dalla web.
- Preservato container web precedente `superbot-rc84-previous` con restart=no e frontend precedente `/opt/superbot-web/build.rc84-previous`; nuova web `superbot` con restart=always. **Non modificare manualmente questi nomi o percorsi prima dell'eventuale rollback**.
- Config nuova web: `TRADING_MODE=paper`, `DESK_MODE=paper`, `V3_CUTOVER_READONLY=1`, `V3_ALLOW_CLASSIC_SINGLE_CLOSE=0`, `V3_ALLOW_BRAIN_SINGLE_CLOSE=0`; three new run mounts read-only. START, RESET, CLOSE_ALL e anche single-close temporaneamente bloccati (nessuna posizione nuova).
- Falco `classic-hawk-paper20261111` 1.000 USDT, Toro `classic-bull-paper20261111` 1.000 USDT; Brain `brain-v3-paper20261111` 2.000 USDT. **PAUSE presenti su tutte e tre, Brain mandate.approved=false, zero cicli/trade PAPER verificati in preflight.** La pubblicazione non ha inviato ordini LIVE o PAPER.
- Servizi PAPER nuovi avviati nella fase precedente, ancora in pausa; Brain exit sidecar unico owner HEALTHY. Vecchi storici e dati rimasti separati e intatti.
- **Credenziali AI ancora NON collegate ai nuovi servizi**: solo presenza ANTHROPIC_API_KEY nei vecchi Falco/Toro e DEEPSEEK_API_KEY nel vecchio Brain Free, senza valori mostrati. La presenza non certifica credito API. Prima di rimuovere pause, provisionare in modo sicuro sulla VPS e verificare che gli engine AI non ricadano in fallback indesiderati.

## Primo tentativo e correzione
- Prima esecuzione [42986634893](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42986634893) FAILED **PRIMA di modificare la web pubblica** con `UnboundLocalError: local variable 'mounts'` nel percorso `publish()`. Erano stati creati solo una copia frontend temporanea e un backup auth DB; RC73 era ancora funzionante.
- Corretto conflitto di nome `mounts`→`live_mounts` nel ramo `work/paper-restart-prep-20261110` commit `894bdac51e070e4ebcc3d3230ba25f8341aafb1d`. Il retry ha recuperato esclusivamente il frontend temporaneo abbandonato dopo aver verificato RC73 e SHA copia, poi ha eseguito il vero cutover e i controlli, SUCCESS.
- Workflow pubblicazione `.github/workflows/v3-rc84-public-readonly-cutover-once.yml` corretto a commit `d360f085757b19b98033c3725bd627528254c593`; secondo trigger `134ef3cd67280c5f5182d59086e0eb1151f35e96`.
- PR #80 RC84 resta Draft, nessun merge del codice nei rami principali per trading; il rilascio web è stato realizzato dal codice candidato PINNED con procedura isolata.

## Prossimi passi — NON ancora autorizzati
1. Utente apre dashboard SuperBot (stesso indirizzo, stesso login) e conferma visibilità/estetica delle sezioni Falco/Toro/Brain e capitali nuovi; login senza test autenticato utente non è stato provato dal browser, ma i controlli 401/423 sono PASS.
2. Collegare Claude per Falco/Toro e DeepSeek per Brain ai **nuovi** servizi PAPER senza esporre credenziali in chat, nei repo o nei log. Evitare nuovi costi superflui; credito API da controllare prima dello sblocco.
3. Abilitare Chiudi ora di ogni nuovo portafoglio **solo quando l'exit owner è sano e ci sono davvero posizioni PAPER**; non attivare mutazioni bulk. L'utente desidera singole chiusure manuali con registrazione nell'apprendimento.
4. Solo su consenso esplicito futuro rimuovere pause, approvare mandato Brain, startup cooldown 15–30 min, NO_TRADE valido, no forzature di slot, e osservazione trade PAPER per 48h/7 giorni. Nessun LIVE.

**Stato finale:** DASHBOARD RC84 WEB PUBBLICA ONLINE; PAPER ENGINE SERVIZI ATTIVI MA PAUSED; ZERO NUOVI TRADE; AI KEY GAP APERTO; RC73 BACKUP RECUPERABILE.
