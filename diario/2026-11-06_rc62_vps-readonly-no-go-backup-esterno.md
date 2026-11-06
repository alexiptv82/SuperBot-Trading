# RC62 VPS read-only — CI GREEN, backup offsite FAILED, nuove run NON pronte

**Data:** 2026-11-06, 21:14 UTC. **Fonte verificata:** GitHub Actions audit read-only `42295014067`, workflow `.github/workflows/v3-rc-readonly-runtime-gate.yml`; code CI precedente `42291292574`.

## Fatto
- **TUTTI i quattro job CI RC #62 verdi** sul commit `027307c`: `classics-rc`, `backend`, `frontend`, `v3-suite` (4073 PASS, 1 SKIP). HEAD ha ricevuto solo ulteriori **workflow read-only e documentazione**, niente trading strategy/deploy/worker modificati.
- Su VPS (nuovo audit): web `superbot` in PAPER e `running`; vecchi worker Falco, Toro, Brain `exited`. Falco storico con **6 OPEN PAPER**, Toro con **2 OPEN PAPER**, e loro pause attive.
- Web ancora collegato a directory Falco/Toro legacy; assenti tutte le variabili Brain `V3_JOURNAL_PATH`, `V3_RUN_ID`, `V3_BUDGET_DB_PATH`, `V3_HEARTBEAT_PATH`, `V3_PAUSE_FLAG_PATH`. La dashboard online **NON è ancora la V3 collegata a nuove run**.
- Brain V3 preparato in `/opt/superbot-v3-paper-runs/brain-v3-rc20261106` con equity **2000**, journal integrità OK, `pause.flag`, mandato **non approvato**. Il suo config SHA NON coincide con la PR #62; non ha il nuovo limite `max_open_risk_fraction=0.12`. **Non modificarlo in-place.**
- Codice della precedente preparazione VPS SHA `53b63b6e8`, non HEAD attuale.
- Backup locale presente `/opt/superbot-backups/rc-v3-20261106T150730Z`; restore rehearsal `42252417296` PASS, antichi Falco6/Toro2 preservati e verifiche SQLite PASS.
- **Backup esterno cifrato FALLITO**: `superbot-extbackup.service` failed, ExecMainStatus1, timer active; ultimo successo `2026-11-02T03:28:45Z`, stato con errore. Sentinella GitHub `42217335679` dice «backup del cervello non riuscito (nessuna finestra di fine ciclo verificata o file mancanti)». Cause alternative NON distinguibili ancora. Non bypassare il gate di fine ciclo né stampare log o segreti su GitHub.

## Decisioni utente immutate
Falco/Toro 1000/1000 PAPER, Claude consultato come in origine, SHORT intatti, soltanto LONG S25 e cambio trend advisory aggiuntivi. Brain 2000 PAPER, 75 USDT rischio stimato su350 margine, leva20–50, max rischio aperto12%, max margine totale55%, floor450. Dashboard unica V3 con tre schede più vecchia dashboard classici preservata.

## Prossimi gate
**NO-GO operativo** finché il backup offsite non torna affidabile con nuovo archivio ripristinabile. Poi nuovo Brain2k **PAUSED** con SHA/config/mandato coerenti, due nuove run classici **PAUSED** in directory separate, owner EXIT unico, binding web e test UI smartphone/desktop, consenso specifico di avvio. Non è stato fatto merge, deploy, modifica VPS, start/stop o reset durante l'audit.

Rapporto: `docs/v3/RC62-SINGAPORE-READONLY-GATE-20261106.md`, commit `14ac880dd8db106614a3daf4dbe32c90991a1a2c`. Runbook rivisto `docs/v3-RELEASE-CANDIDATE-BOOTSTRAP-RUNBOOK.md`, commit `8aa3d7c22620b2cf4905e3f347e5974f79ea3b02`.
