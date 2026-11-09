# SuperBot V3 — 09/11/2026 — Dopo prima CI verde: analisi rami e decisione di composizione RC84

## Stato verificato
- PR #80 Draft `cursor/rc84-running-stop-health-telegram-20261108` head `0e29a73a36f668643da4088178bacb8616a45ac0`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`, non mergeata.
- Prima GitHub Actions offline TEST ONLY #1: **SUCCESS** dallo screenshot GitHub dell'utente, **2/2 jobs** (backend Python3.11, frontend Node22), durata 6m12s, 2 artefatti. Numeri esatti dei test NON letti nei report GitHub, come da diario precedente.
- [Commento GitHub con decisione di composizione](https://github.com/alexiptv82/SuperBot-Trading/pull/80#issuecomment-6750139725).

## RC79 PR #76: read-only, ma modulo non integrato
- PR #76 `[DRAFT][OFFLINE] RC79 — diagnosi post-trade PAPER read-only`, HEAD `35ba0c471986e90510cd4e19c24d8f0f76d8934d`, divergent rispetto RC84: base comune `52c21b5ea219bb864b8748ba1b2cfe109349a2e7`; RC79 +4 commit non inclusi; RC84 +61 commit.
- File esclusivi a #76: `backend/v3/observability/post_trade_review.py` (analisi pura), `backend/tests/test_v3_rc79_post_trade_review.py` (15 test locali sintetici segnalati), `docs/v3/RC79-POST-TRADE-READONLY-HANDOFF.md`, `diario/2026-11-07_chatgpt_rc79_offline.md`. Nessuna modifica diretta a API, strategie, runner, rischio, stato, dashboard.
- Funzioni: aggrega parziali per identità, evidenzia perdita > margine, coppie e direzione coincidenti su wallet diversi, possibili stop superati **solo con fonti verificate**, non inventa diagnosi d'ingresso errato; `can_autolearn=False`, `can_trade=False`, default `evidenza_insufficiente`. Anche i -122.63/-226.86 ARB usati nei test sono fixture, non accesso VPS.
- Limite decisivo: **nessun adapter reale al Journal V3 Brain né lettura degli storici dei classici / integrazione dashboard**. Non diventerebbe funzione visibile appena cherry-pickato.
- **Decisione proposta:** non mescolare la PR #76 nella RC84 CI-green, ma pianificarla come miglioramento successivo **in modalità read-only**, con adapter verificato e test su copie immutabili; conservare PR #76 intatta.

## Main e le due PR F0 #30/#31
- Confronto RC84→main: **2 commit esclusivi di main**, da PR #30/#31 F0 (già merged), file aggiunti soltanto `.github/workflows/f0-restricted-status.yml`, `f0-restricted-tests.yml` e `ops/f0/{README.md,restricted_status.py,provision_account.sh,install_public_key.sh,test_restricted_status.py}`.
- Sono diagnostica VPS non-root via SSH forced-command, secret F0 dedicato, workflow con `workflow_dispatch` e `schedule` quotidiano; non toccano la logica di trading. Non sappiamo se la configurazione sul server e il secret siano attivi ad oggi; README è la fotografia della proposta, non uno stato VPS verificato.
- **Decisione proposta:** tenere questi componenti su main, NON portarli nel branch RC84 solo per uniformare la genealogia. Futuro eventuale merge V3 su main manterrà naturalmente i file F0, previa revisione separata degli effetti e dei workflow.

## Trigger main: precisazione
`v3-stop-paper-workers.yml` e `v3-vps-inventory.yml` hanno `push` `branches: [main]` **con filtri `paths`** rispettivamente su `deploy/v3-stop.trigger` e `deploy/v3-inventory.trigger`; un qualunque merge main NON basta da solo ad attivarli. Evento manuale `workflow_dispatch` presente. Controllare comunque tutti i trigger prima di un futuro merge. **Nessun merge oggi**.

## Prossimo lavoro raccomandato
1. Recuperare dal GitHub run #1 vero **run_id REST** mediante URL completo del run o `gh run list` con credenziali autorizzate; consultare i due artifact per conteggi pytest/Jest esatti, distinguendo xfail/deselected.
2. Collaudo **UI autenticata web/browser con server locale sintetico/effimero** che esponga tre wallet Falco, Toro, Brain, posizioni e PnL, close singola manuale con coda e reject 409, alert stop e claim `pending/conflict/unknown`, indisponibilità Brain, mobile responsive/Android browser se possibile. Nessun server o bot vero, nessun invio trade.
3. Review release safety: password bootstrap statica nel workflow staging pubblicato (non riportare valore), backup off-host restore, Brain handover legacy→sidecar su VPS solo previa autorizzazione e preflight READ-ONLY, rischio stop OHLC periodici vs stop continuo. Definire RC unica pinned prima di ogni release.
4. Ogni nuova run rimane **solo PAPER**, capitale Falco/Toro 1000 + Brain 2000 USDT, storico intatto, consenso esplicito successivo.

**NO MERGE, DEPLOY, ACCESSO VPS, RESTART, RESET, ORDINI.**
