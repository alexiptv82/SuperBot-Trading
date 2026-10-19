# Manuale operativo — come si lavora su SuperBot Trading

Scritto il 19/10/2026 da Claude, verificato sul repository e sul server in quel giorno. Serve a **qualunque AI** (ChatGPT o Claude) per lavorare da sola, con gli stessi strumenti dell'altra. Leggi prima `LEGGIMI.md` (regole inviolabili) e `STATO.md`. Se qualcosa qui non coincide con ciò che vedi dal vivo, vale ciò che vedi: correggi il manuale.

## 1. Chi ha accesso a cosa

- **Repository:** `alexiptv82/superbot-trading` su GitHub, **pubblico**. Ramo predefinito `main`. **Nessuna protezione dei rami**: chi ha scrittura può fare push ovunque, quindi le regole le rispettiamo noi.
- **Chi scrive:** i commit di Claude hanno autore "Claude"; quelli di ChatGPT risultano a nome dell'account dell'utente (`alexiptv82`); i workflow committano come "SuperBot CI". Per capire chi ha fatto cosa: i commit di Claude portano in fondo il trailer `Co-Authored-By: Claude ...`; **i commit di ChatGPT portano in fondo la riga `AI: chatgpt`**; e il diario riporta sempre l'autore.
- **Il server:** una AI non entra direttamente sul server. Lavora **solo tramite i workflow di GitHub Actions**, che si collegano a Singapore con il Secret `SINGAPORE_SSH_PRIVATE_KEY` (il contenuto della chiave non si legge mai). Quindi: *scrivere un workflow o un file trigger e fare push = poter agire sul server*. Questa è la "stessa abilità" di cui parla l'utente, ed è identica per le due AI.
- **Secret esistenti (solo i nomi):** `SINGAPORE_SSH_PRIVATE_KEY`, `SSH_PRIVATE_KEY` (Strasburgo, solo per HI-TV/inventario: non usare per SuperBot), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `ANTHROPIC_API_KEY`, `DESK_MODE` (deve restare `paper`), `DESK_DAILY_LOSS_PCT`, e le chiavi Bitget per bot (`BITGET_HAWK_*`, `BITGET_BULL_*` di trading; `BITGET_RO_HAWK_*`, `BITGET_RO_BULL_*` di sola lettura). **Non si stampano mai.**

## 2. I rami

| Ramo | A cosa serve | Regola |
|------|--------------|--------|
| `main` | **App** (backend FastAPI in `backend/`, frontend React in `frontend/`) e il suo deploy (`.github/workflows/deploy.yml`) | Un push su `main` fa partire il deploy dell'app, **tranne** se tocca solo `.github/workflows/**`, `deploy/**` o file `.md` |
| `rule-pool` | **Bot Hawk/Bull** (`backend/desk/`), pool di regole, e **tutti i workflow operativi** con i loro file trigger in `deploy/` | Qui si lavora per i bot e per i controlli |
| `diario` | Questo diario | Nessun workflow parte da qui |
| `work/backend-singapore-audit` | Archivio del lavoro di ChatGPT sulla migrazione parziale (17–18/10) | **Non unire. Non rilanciare i workflow `work-app-link-*`** |
| `stable/app-2026-10-12`, `stable/bot-2026-10-12` | Punti stabili a cui tornare | Mai push |
| `v0.5` | Vecchia versione | Mai toccare |
| altri (`pwa-dashboard`, `risk-profiles`, ecc.) | Vecchi lavori | Lasciare stare. `pwa-dashboard` alimenta lo staging a Strasburgo |

`main` e `rule-pool` hanno **storie diverse** (46 commit solo su `main`, 100 solo su `rule-pool`): non fare merge tra i due senza averlo concordato con l'utente. In `rule-pool` `backend/server.py` ha un bug (manca l'import di `Request`): **l'app si distribuisce sempre dal codice di `main`**, e anche il workflow `superbot-sg-deploy.yml` di `rule-pool` fa il checkout di `main`.

## 3. Come funzionano i workflow

- **Meccanismo "trigger file":** quasi tutti i workflow operativi partono quando si modifica un file `deploy/<nome>.trigger` e si fa push su `rule-pool`. Convenzione: scrivere nel file la data UTC e un motivo breve (`date -u +%FT%TZ` + testo), poi commit e push.
  ```bash
  git checkout rule-pool && git pull --rebase origin rule-pool
  echo "$(date -u +%FT%TZ) <motivo>" > deploy/sg-bots-check.trigger
  git add deploy/sg-bots-check.trigger
  git commit -m "check: <motivo>

  AI: chatgpt" && git push origin rule-pool      # (Claude usa il suo trailer Co-Authored-By)
  ```
- **`[skip ci]`** nel messaggio del commit impedisce qualunque esecuzione. Va messo ogni volta che si modifica un file senza volerlo eseguire. Alcuni workflow partono **anche quando si modifica il loro stesso file** (per esempio `desk-paper-preflight`, `desk-paper-restore-claude`, e i `work-app-link-*`): per modificarli senza eseguirli serve `[skip ci]`.
- **Dove si leggono i risultati:**
  1. molti workflow scrivono un file `deploy/<nome>-output.txt` sul ramo `rule-pool` (es. `superbot-sg-check`, `sg-bots-check`, `sg-hardening-check`, `strasburgo-inventory`): si legge con la lettura file del repository;
  2. altri pubblicano **annotazioni** nel run (es. `desk-status`, `desk-diag`): `gh api repos/alexiptv82/superbot-trading/check-runs/<id>/annotations`;
  3. i log completi dei job spesso **non sono scaricabili** dagli ambienti delle AI: per questo i nostri workflow scrivono l'esito in un file.
- **Collegamento SSH sicuro:** i workflow rinforzati usano una chiave host verificata. Per `ssh`/`scp`: `known_hosts` costruito dalle righe `PUB ...` di `deploy/sg-hardening-check-output.txt`, con `StrictHostKeyChecking=yes`. Per `appleboy/ssh-action`: `fingerprint: SHA256:sNv9lNqWbZFf2Pm5ChIubeQKV5TzKfUWNlGPzCJg96s` (è l'impronta **ECDSA**: le impronte ED25519 e RSA non funzionano con quell'azione). Se il server cambia chiave, i deploy si fermano: non è un guasto, va rigenerata l'impronta con `sg-hardening-check`.
- **Concorrenza:** solo `deploy.yml` (app, su `main`) ha un gruppo di concorrenza. Per tutti gli altri deploy (bot, pool, `superbot-sg-deploy`) **non lanciarne due insieme e non lanciarne uno mentre un altro è in corso**: controllare prima i run attivi.

## 4. Il catalogo dei workflow (cosa si può lanciare)

Classificazione fatta da nomi e intestazioni il 19/10. **Prima di lanciarne uno che non conosci, leggi l'intestazione del file.**

**A. Sola lettura — si possono lanciare liberamente:**
`superbot-sg-check` (app, nginx, HTTPS, bot, log), `sg-bots-check` (stato dei bot, pagine, test chiavi Bitget di lettura senza importi), `sg-hardening-check` (riavvii, chiavi host, prova dei backup; lascia copie di backup vere sul server), `desk-status`, `desk-diag`, `desk-mode-check` (conferma che i bot sono in paper), `desk-attivita`, `desk-claude-finestra`, `desk-confronto`, `desk-analista`, `desk-esaminatore`, `desk-macro-effect`, `desk-calendario-check`, `pool-status`, `pool-probe`, `strasburgo-inventory`, `sg-precheck`, `vps-capacity-audit`, `vps-diagnostics-readonly`. I laboratori di ricerca (`breadth-lab`, `crosssec-lab`, `funding-lab`, `strategy-lab`, `edge-scan`, `risk-sim`, ecc.) girano su GitHub senza toccare il server.

**B. Con effetto — serve l'OK esplicito dell'utente (in chat) prima di lanciarli:**
- `desk-deploy` (trigger `deploy/desk-deploy.trigger`): **redeploy di Hawk e Bull**. Fa prima un backup verificato del cervello (`deploy/scripts/backup_brain.py`; se fallisce non tocca niente), tiene l'immagine precedente come `superbot-desk:rollback-<data>` e controlla a fine corsa che i due bot siano su. **Regola inviolabile n. 1.**
- App: `deploy.yml` su `main` (push o "Run workflow") **oppure** `superbot-sg-deploy.yml` (trigger `deploy/superbot-sg-deploy.trigger` su `rule-pool`): entrambi costruiscono e distribuiscono l'app dal codice di `main`. Backup SQLite verificato prima; immagine precedente tenuta come `superbot:prev`; controllo di salute a fine corsa (diventa rosso se l'app non risponde). Pochi secondi di indisponibilità. Non tocca i bot né il cervello. `TRADING_MODE` è fisso a `paper`.
- `pool-deploy` (runner paper del pool; backup verificato di `pool.db` prima).
- `desk-schedule` (modifica `deploy/claude-schedule.json`, il calendario delle finestre in cui il bot può consultare l'API di Claude; nessun riavvio).
- `superbot-restart`, `desk-remove-pause`, `desk-snapshot`, `webauthn-reset` (azzera le credenziali dell'impronta digitale: l'utente dovrà registrarla di nuovo), `desk-stop-legacy`.
- **Emergenza**, da usare se qualcosa va storto: `desk-pause-now` (scrive il flag di pausa, come il tasto Pausa dell'app: niente nuove aperture, le posizioni aperte si chiudono da sole) e `desk-stop-containers` (ferma i container senza rimuoverli, si riavviano con `desk-deploy`). Se i bot fossero in live e andasse male, ferma l'utente dalla app; poi se ne parla.

**C. Mai senza ordine esplicito e ripetuto dell'utente:**
`live-selftest` (apre posizioni con **soldi veri** su Bitget, importo minimo), qualsiasi cambio di `DESK_MODE`, qualunque modifica a strategia, soglie, limiti di rischio, prompt, o ai file del cervello.

**D. Rimossi o da non usare:** i workflow di migrazione dati `sg-migrate-assets`, `sg-pool-migrate`, `sg-cutover` sono stati **cancellati il 19/10** (un rilancio avrebbe sovrascritto database e pool vivi con copie vecchie; restano nella storia di git). Il vecchio `deploy.yml` di `rule-pool` (Strasburgo) e `staging-deploy` riguardano Strasburgo: non rilanciarli. I `work-app-link-*` stanno solo nel ramo archivio.

## 5. Il server (Singapore) — dove sta cosa

- Server: OVH, `51.79.205.82`, 2 vCPU, ~3,8 GB di RAM (poca: i deploy dei bot controllano che ci siano almeno 700 MB liberi). Accesso solo via workflow.
- App: container `superbot` (porta 8002 dell'host → 8001), dati in `/opt/superbot/data` (database SQLite `superbot.db`), frontend in `/opt/superbot-web/build`, nginx sulle porte 80/443, certificato Let's Encrypt (rinnovo automatico) per `superbot-trading.duckdns.org`.
- Bot: container `superbot-desk-hawk` e `superbot-desk-bull` (immagine `superbot-desk:singapore`), dati nei volumi `/opt/superbot-desk-data/hawk` e `/opt/superbot-desk-data/bull` (qui c'è il **cervello**: `trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl`; poi `state_v2.json`, `heartbeat.json`, `claude_schedule.json`, flag di comando).
- Pool: container `superbot-pool`, dati in `/opt/superbot-pool-data` (`pool.db`).
- Backup: `/opt/superbot-backups/` (database app, pool, cervello dei bot; si tengono le ultime 10). Strumenti di backup copiati in `/opt/superbot-tools/`. **Sono sullo stesso server**: non proteggono dalla perdita del server (aperto: backup esterno).
- Ponte temporaneo del 18/10 (`superbot-desk-api`, porta locale 18002): non più usato, da ritirare con OK dell'utente.
- Strasburgo (`51.91.109.45`): condiviso con **HI-TV, da non toccare mai**. SuperBot lì è fermo (container con `restart=no`, non cancellati: servono per tornare indietro) tranne `superbot-staging`.

**Come funziona il bot** (dettagli nel codice, `backend/desk/`): cicli ogni 30 minuti (15 in alcune fasi), controllo comandi ogni 5 secondi; `signals.py` calcola gli indicatori, `engine.py` il conto paper e i limiti, `brain.py` le chiamate all'API di Claude (il "cervello" consulta Claude solo nelle finestre del calendario; fuori finestra decidono le regole), `learning.py` il registro di apprendimento, `market_context.py` funding/OI/long-short/notizie, `notifier.py` Telegram. **Attenzione al doppio senso:** "Claude" nel bot è l'API di Anthropic che il bot consulta; "Claude" in questo diario, quando indica un'AI che lavora, è l'assistente che sta in chat con l'utente. Non c'entrano l'uno con l'altro.

## 6. Procedure tipiche

**Controllare che tutto sia sano** (sola lettura): trigger `deploy/superbot-sg-check.trigger` → leggere `deploy/superbot-sg-check-output.txt`; poi `deploy/sg-bots-check.trigger` → `deploy/sg-bots-check-output.txt`. Cosa guardare: container `Up`/healthy, `/api/health` ok in paper, bot online con cicli recenti, `DESK_MODE=paper` su entrambi, nessun errore nuovo nei log.

**Rilasciare una modifica all'app** (con OK dell'utente se cambia il comportamento): modificare su un ramo di lavoro, verificare i test, unire in `main` (push), seguire il run di `deploy.yml`, poi lanciare `superbot-sg-check` per verificare. Ritorno indietro: ricreare il container dall'immagine `superbot:prev`.

**Rilasciare una modifica ai bot** (sempre con OK esplicito): modificare in `rule-pool`, far passare la CI (`desk-ci`), poi scrivere `deploy/desk-deploy.trigger`; a fine corsa verificare con `desk-status`/`sg-bots-check` che i due bot siano in paper, la versione sia quella attesa e le posizioni intatte. Ritorno indietro: immagine `superbot-desk:rollback-<data>` o punto stabile (`stable/bot-2026-10-12`); i dati si ripristinano solo se serve e con l'utente, partendo da `/opt/superbot-backups/bots-*`.

**Tornare a Strasburgo** (solo emergenza grave): su DuckDNS rimettere `51.91.109.45`, a Strasburgo `docker start superbot` e riattivare il servizio del tunnel. Il database là è fermo all'ultima copia del 19/10 mattina.

## 7. Trappole già incontrate

- Il repository è pubblico: niente saldi o importi del conto Bitget negli output committati (i controlli già lo evitano, stampano solo OK/errore).
- Le chiavi Bitget sono limitate a un IP: da un server nuovo Bitget risponde "Invalid IP" (errore 40018). Si aggiunge l'IP nella gestione delle chiavi su Bitget (lo fa l'utente).
- La pagina Live dell'app in paper mostra volutamente zeri e non legge il saldo (guardia introdotta il 15/10: i numeri veri solo se server e bot sono davvero in live).
- `StrictHostKeyChecking=no` e `cp` di un database SQLite in uso sono due errori già corretti: si usano la chiave host verificata e l'API di backup di SQLite (`deploy/scripts/backup_app_db.py`).
- Un check che non può fallire non verifica niente: provare ogni controllo anche con un caso che deve fallire.
- Dopo qualunque modifica ai workflow: validare lo YAML e controllare che non ci siano trigger che partano da soli per sbaglio.
- Un workflow di SSL per `hitvprime` ha già lasciato una configurazione in nginx: **non toccare mai domini e nginx di HI-TV**.
