# 10 novembre 2026 — Gate minimo PAPER Brain V3: VPS Singapore, riscontro diretto

**Esito:** sola lettura completata; **NO AVVIO**, **NO MERGE**, **NO DEPLOY**. Obiettivo ora: ripartire in PAPER senza introdurre un ulteriore percorso di sicurezza non essenziale.

## Evidenze GitHub Actions
- [Run 42893620386](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42893620386), HEAD `efd37f66839803f22da6cc38493383a421261569`: job audit riuscito; osservazione alle 20:16 UTC del 10/11 (21:16 Europe/Rome). Script read-only `deploy/scripts/v3-vps-inventory.sh`, aggiornato su `main` SHA `33858512ff8bc92414cc8e79ee854eca52264412`, trigger dedicato, nessun altro workflow avviato da quel commit.
- [Run 42893962748](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42893962748), HEAD `749e9b53446b64e135ae549dbfc6403367969b00`: diagnostica mirata per soli limiti leva, job success; nessuna scrittura VPS.

## Dati osservati senza leggere o mostrare segreti
- **Falco/Toro:** entrambi fermi, PAPER, 0 posizioni aperte, file storico/apprendimento presenti. Lo snapshot locale **RC77** ha coincidenza SHA-256 per tutti i file elencati dal manifesto, sia con i file correnti Hawk/Bull sia con le copie. Manifesto annota `restore_rehearsal=PASS` e `source_data_unchanged=True`; NON è stata ripetuta una nuova prova di restore né attesta backup fuori VPS.
- **Brain V3:** cartella run `brain-v3-rc20261106` presente; `runner_config.json`, `mandate.json`, `PREPARED_PAUSED_ONLY.json`, `journal.db`, `budget.db`, `pause.flag` presenti. Database con header SQLite valido (solo header, non integrity_check). Marker PAPER/pausa coerente con config hash e run_id; capitale `2000`, floor `450`; mandato `approved=False`, marker `mandate_approved=False`. Mancano `heartbeat.json`, `exit_heartbeat.json`: nessun runner attivo dimostrato.
- **Leva:** il predicato `min_leverage==20` e `max_leverage==50` è **FALSO** sulla configurazione della run; il controllo successivo ha restituito `UNSET` sia per min sia per max perché lo script stampa il valore **solo se di tipo intero**. Quindi potrebbero essere assenti, null o non-interi: **non dedurre il valore preciso senza un'ulteriore lettura**. Il profilo candidato nel repository RC84 `backend/v3/runner/runner_config_brain2000_paper.json` definisce invece leva min 20 max 50, equity 2000 e floor 450. Non correggere a mano la run vecchia: l'hash/mandato/event journal potrebbe diventare incoerente. Preparare solo con OK una **nuova run PAPER separata** con configurazione approvata e storico vecchio intatto.
- **Web:** container `superbot` attivo, `TRADING_MODE=paper`, `DESK_MODE=paper`, `V3_CUTOVER_READONLY=1`; env per run Brain configurato e volume montato; `V3_ALLOW_BRAIN_SINGLE_CLOSE=0` (non abilitato). Questi flag verificano una configurazione PAPER dell'app, NON garantiscono da soli impossibilità di chiamate LIVE da ogni futuro esecutore.
- **Servizi:** in elenco soltanto `superbot-v3-falco-exit.service` e `superbot-v3-toro-exit.service`, attivi. Nessun servizio Brain V3 in quell'elenco; non certifica che nessun processo indipendente possa aprire file, ma assenza di heartbeat indica che la run non opera.
- Nessun ordine, reset, installazione, riavvio, merge o cambiamento di dati PAPER è stato eseguito.

## Decisione per avanzare senza altre settimane di sicurezza
1. **Gate dei classici:** backup locale RC77 verificato; posizioni zero; PAPER dichiarato. Restano da validare nella proposta di rilascio: immagini/motori corretti rispetto alle strategie con Claude e LONG/trend, single-writer e modalità *paper-only* dell'esecutore. I vecchi classici sono spenti: riavviarli senza il rilascio appropriato rischia di far tornare la vecchia strategia.
2. **Gate Brain:** nuova run PAPER preparata separatamente dai dati storici; config 2000 USDT / floor 450 / leverage 20–50x/ rischio approvato; mandato esplicito, servizio di apertura/uscita e handover con unico proprietario; no-live enforcement. Senza mandato non si avvia.
3. I backup remoti age V1/V2 e le rifiniture cosmetiche restano un workstream separato; non subordinare sperimentazione PAPER a tali rifiniture, ma conservare lo snapshot corrente e la possibilità di fermare i motori.
4. Prima di qualsiasi avvio o merge chiedere **OK distinto**; l'utente aveva autorizzato soltanto diagnostica in sola lettura.

**Status al termine:** Falco/Toro pronti come dati/snapshot, motori spenti; Brain V3 predisposto ma mandato non approvato e profilo leverage non dimostrato; NO PAPER RUN ATTIVA.
