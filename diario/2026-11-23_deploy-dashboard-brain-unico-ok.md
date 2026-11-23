# 2026-11-23 07:41 CET — Installazione Brain Unico e dashboard su VPS: SUCCESSO

## Evidenza diretta da screenshot Termius del proprietario
- Script unificato di deploy su VPS Singapore completato con riga finale: `ESITO AVVIO: PRONTO PER L'ATTIVAZIONE PAPER (mandato NON approvato, nessun trade)`.
- `BRAIN_UI_RESULT=SUCCESS_UI_BRAIN_UNICO` e `PASS 3 interfaccia Brain Unico pubblicata (PWA invariata, backup e rollback pronti)`.
- `BRAIN_UI_PWA_IDENTITY_FILES=PRESERVED` e `BRAIN_UI_ROLLBACK_READY=/opt/superbot-web/.brain-unico-webui-previous`.
- Backup web immediatamente precedente verificato: `/opt/superbot-v3-backups/brain-unico-webui-before-20261123T063924Z/build`.
- Servizio uscite `USCITE: SANE`; runner `halted:mandate_not_approved`; `approved:false`; nessuna spesa AI; nessuna apertura; heartbeat recente.
- `PASS 4 controlli`, `PASS pausa attiva`, `PASS` vecchia exit run invariata, `PASS` Falco/Toro/Arena/Brain storico e container invariati.
- Non è ancora stata mostrata o verificata da proprietario la nuova schermata dell'app sul telefono; non c'è ancora un trade PAPER.
- Codice di deploy verificato nel repository branch `integration/brain-unico-20261119` commit `9b1532780fe61ba36a28df9130bccb6190b396ac`.

## Prossimi passi, in ordine
1. Proprietario apre app SuperBot sul telefono (o pagina HTTPS esistente), fa refresh e verifica login, Brain Unico schermata principale, equity 2000 USDT, storico e controlli; invia screenshot.
2. Se la UI è corretta, proprietario fornisce **consenso separato esplicito** all'avvio in PAPER 72 ore con profilo B e DeepSeek Flash. Comando già preparato `sudo sh /root/brain-unico-avvio/80-paper.sh attiva "<Nome>"`; non eseguirlo prima del consenso.
3. Misurare salute, PnL netto, perdite e drawdown, qualità delle decisioni, costi AI, memoria, gestione chiusure manuali. Test iniziale 72h tecnico, non prova redditività.
4. Non ripetere backup avanzati o studi P0 già chiusi. Restore da chiave privata differito SOLO per PAPER virtuale.

Questo checkpoint documenta risultati visibili a ChatGPT sullo screenshot, non una nuova prova diretta SSH.