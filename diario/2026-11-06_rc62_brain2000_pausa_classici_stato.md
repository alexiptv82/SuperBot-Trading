# Checkpoint 6 novembre 2026 — Brain 2.000 PAPER preparato, RC62 avanzata

## Decisione utente
Confermati **2.000 USDT PAPER per Brain**, **1.000 USDT per Falco** e **1.000 USDT per Toro**. Conservare lo storico e le 6+2 posizioni PAPER rimaste nelle vecchie run; tre portafogli indipendenti, nessuna ricostruzione di SuperBot.

## Lavoro effettivamente eseguito
- **PR #62 DRAFT**, branch `work/v3-release-candidate-gpt6-20261106`. File opt-in `backend/v3/runner/runner_config_brain2000_paper.json`: differisce dal default `runner_config.json` soltanto per `initial_equity=2000`. Mantiene 2% rischio per trade, 5% open risk, floor 450, avviso 35%, stop 50%, DeepSeek e parametri invariati. Cinque test nuovi.
- `prepared_config_guard.py`: su run preparate il runner Brain sidecar e l'exit worker devono leggere **la stessa** config del journal/marker di preparazione. Profilo 1000 su run 2000 -> rifiuto prima di avviare owner; sei test nuovi, passati su CI.
- **VPS Singapore**: workflow `v3-rc-brain2000-paused-preparation.yml` [run 42267383080] ha creato la run `/opt/superbot-v3-paper-runs/brain-v3-rc20261106`; stdout verificato: `RUN_PREPARED_PAUSED`, `validated_existing_brain_run`, `BRAIN_NEW_RUN_CONFIRMED=2000 PAPER PAUSED MANDATE_UNAPPROVED`, `LEGACY_DATA_UNTOUCHED=YES`, `NO_WORKER_STARTED=YES`. Journal e budget nuovi, mandato non approvato, pausa presente. **Non è un deploy operativo**, non è stato avviato alcun worker.
- Audit read-only VPS [run 42266824471] conferma: web `superbot` ancora su vecchi bind mount hawk/bull/brain; container legacy fermati e restart=no; web running restart=always; `superbot-extbackup.service` risulta FAILED. Il backup manuale /opt/superbot-backups/rc-v3-20261106T150730Z e la prova di restore restano validi. Nessun backup offsite corrente certificato.
- **Classici, codice RC soltanto**: PR #58 S25 opt-in (`DESK_LONG_S25=1`, default OFF) + fixtures/test incorporati; PR #59 chiusura singola PAPER incorporata nel `desk/cli.py` già corrente senza sostituire il percorso precedente di chiusura LIVE. Il comando nuovo singolo non opera in LIVE. Test S25/classici aggiunti come job `classics-rc` di `v3-dashboard-ci`.
- La preparazione automatica di **nuove directory Falco/Toro in pausa** è stata **bloccata dai controlli di autorizzazione della piattaforma**. Nessuna directory classici nuova è stata dichiarata creata; non aggirare il blocco né procedere con il vecchio `reset_portfolio.flag`.

## Prove
- CI V3/dashboard a HEAD `2ff8f7d6` verde: 4053 passed + 1 skipped su Python 3.11, backend API e React build pass. Precedenti commit della RC #62 verdi.
- CI dopo integrazione classici è stata avviata, ma l'esito dell'ultimo job classici va **verificato**, non presunto. Le suite offline su profitti non sono il gate per sbloccare PAPER; contabilità, stop, ownership, recovery sì.

## Prossimi blocchi prima del GO
1. Completare CI del ramo attuale (incluso S25/desk) e affrontare eventuali fallimenti.
2. Creare nuovi storage PAPER in pausa per Falco/Toro con percorso distinto dagli storici (autorizzazione operativa appropriata necessaria); non riprendere le 6+2 posizioni legacy.
3. Installare/sorvegliare unico sidecar EXIT Brain, verificare lock OPEN/CLOSE, kill/restart e disponibilità stop indipendentemente dal modello AI; poi collegare il runner alla nuova run.
4. Ricostruire mount dei container classici e del web dashboard sulle **nuove directory**, non su quelle legacy; prova sessione da telefono.
5. Diagnosticare e ripristinare backup automatico esterno `superbot-extbackup.service` prima del rilascio finale; verificare nuovamente il backup e il rollback.
6. **Solo dopo**, con mandato Brain della run specifica approvato esplicitamente e tutti e tre i servizi in PAPER, togliere pause flag delle nuove run e monitorare.

**Stato reale:** Brain 2.000 PAPER PREPARATO MA IN PAUSA; Falco/Toro codice RC aggiornato, storage nuovo e worker non avviati; **NO-GO al rilascio operativo**. Nessun merge su main/rule-pool, nessun reset storico o deploy dei tre bot.
