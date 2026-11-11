# 11 novembre 2026 — RC84 web PUBBLICA: preflight e script rollback PASS, NON PUBBLICATA

**Risultato effettivamente eseguito e verificato:** due verifiche sulla VPS Singapore, [run 42985516252](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42985516252) e [run 42985910821](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42985910821), entrambe **SUCCESS**. La prima è interamente read-only; la seconda ha copiato soltanto due script di rilascio in cartella tecnica **nuova e isolata** e lanciato `--preflight-only` con risultato PASS. Non è stato avviato `--publish-readonly`, non è cambiata la dashboard pubblica.

## Prove reali di readiness sulla VPS

- PINNED_BACKEND_AND_FRONTEND=PASS per la build RC84 esatta `0e29a73a36f668643da4088178bacb8616a45ac0`.
- HAWK_1000_PAUSED, BULL_1000_PAUSED e BRAIN_2000_PAUSED_EXIT_HEALTHY=PASS.
- LEGACY_UNCHANGED=PASS: vecchi engine e storici non toccati.
- PUBLIC_RC73_ROLLBACK_READY=PASS: web attuale funzionante, nome e percorsi di rollback disponibili, autenticazione SQLite del server identificata.
- RC84_PREVIEW_HEALTH_AND_AUTH=PASS: anteprima frontend+API attive su loopback, overview 401 senza login, POST Brain close 423.
- DISK_AND_ROLLBACK_ROOM=PASS.
- RC84_CUTOVER_READONLY_PREFLIGHT=PASS.
- Sintassi AST dei due script PASS; `RC84_PUBLIC_ROLLBACK_PREFLIGHT=PASS`; `RC84_PUBLIC_CUTOVER_DRY_RUN=PASS`.
- **NESSUN** servizio di trading, mandato Brain, `pause.flag`, data legacy, provider AI o credenziale sono stati modificati.

## Artefatti tecnici predisposti

- Ramo `work/paper-restart-prep-20261110`, commit sorgente `3eb600e82e4c835653cde5032e58faee545ba73d`, file:
  - `deploy/scripts/v3-rc84-public-readonly-cutover-preflight.py`
  - `deploy/scripts/v3-rc84-public-paper-readonly-cutover.py`
- I due script sono stati copiati e verificati in `/opt/superbot-v3-rc84-release-scripts/` sulla VPS, **non eseguiti in modalità pubblicazione**.
- Il secondo script, una volta esplicitamente autorizzato, prevede build backend dal codice PIN, riuso frontend preview RC84, backup SQLite auth con integrity_check/restoration check, preservazione vecchia immagine/container RC73 e build frontend, rollout in `TRADING_MODE=paper`, `V3_CUTOVER_READONLY=1`, new run mounts tutti :ro, nessuna nuova apertura, manual-close disabilitati finché i conti sono PAUSED, verifica API 401/423 e rollback in caso di errore. **Il percorso di deploy/rollback non è stato provato sul sito pubblico: la verifica fatta è un preflight, non una certificazione del cutover.**
- Workflow di pubblicazione predisposto ma **NON attivato**: `.github/workflows/v3-rc84-public-readonly-cutover-once.yml`, commit `c16280119b3920d41ea8058b14e22636507d94d3`. Il file trigger `deploy/v3-rc84-public-readonly-cutover.trigger` è stato verificato **ASSENTE** su main. Evitare di attivare finché non sia stata presa la decisione sul web pubblico.

## Blocco credenziali AI ancora aperto

- [run 42983972925](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42983972925) aveva riscontrato la presenza delle chiavi Claude/DeepSeek nei VECCHI container ma **assenza dei tre file secret per i NUOVI servizi**. Nessun trasferimento credenziali effettuato. Non fare estrazione/copia di chiavi da Docker a GitHub o ai log; segreti da provisionare con procedura approvata sulla VPS. Una bozza di migrazione automatica precedente è stata rimossa dal ramo.
- Tutti i bot restano PAUSED e Brain mandato approved=false; PAPER non sbloccato.

## Prossima decisione

1. Il rilascio pubblico RC84 **READONLY** è tecnicamente preparato, ma non equivale al trading e terrebbe temporaneamente disabilitato il tasto `Chiudi ora`: valutare l'esplicita autorizzazione prima di sostituire la pagina pubblica, preservando RC73 per rollback.
2. Collegare in modo sicuro Claude per Falco/Toro e DeepSeek per Brain, senza mostrare segreti; controllare credito dei provider prima dello sblocco.
3. Solo dopo prove e consenso distinto: abilitare singole chiusure PAPER con owner sani e rimuovere pause. Niente LIVE, backup remote age V2 fuori dal percorso critico.

**Non dichiarare la dashboard RC84 pubblicata finché il workflow di cutover non risulta SUCCESS con esito web reale.**
