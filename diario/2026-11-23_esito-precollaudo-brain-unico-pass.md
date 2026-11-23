# 2026-11-23 — Pre-collaudo Brain Unico eseguito: PASS (Termius)

## Evidenza proprietario
- Screenshot Termius 05:52 ora Italia, output finale esatto: `ESITO PRE-COLLAUDO: TUTTI PASS (mandato non approvato; 72 ore non avviate; unita' nuove rimosse dal rollback)`.
- Esecuzione dal comando root preparato da Claude: `00-precollaudo-completo.sh` per integrazione `3440340289fdd23398f57390238daf8da3eb3fa9`; script orchestratore presente al commit `e4864d80cbe67f88c8a812f7b50e43a9e5a85d20`.
- Screenshot: uscite ferme diventano NON sane; riavvio rende SANE; servizio vecchia run invariato; runner halted per mandato, `approved:false`, 0 spese AI e 0 aperture; heartbeat recente; tutti i controlli dopo riavvio PASS; rollback nuove unità OK, journal conservato, vecchie unità e container invariati.
- **7b rollback web non eseguito**: dashboard attiva non toccata; NON confondere con test di web deploy.
- **Stato post-test**: due nuove unità rimosse dal rollback, run nuova preservata e ancora in pausa (pause.flag), mandato non approvato; 72h PAPER non avviate.
- L'output è stato letto nello screenshot dell'utente; log operativo locale indicato da Claude: `/home/superbot-agent/precollaudo-esiti/precollaudo.log`. Claude può leggerlo e registrare evidenze ulteriori senza fare un nuovo audit.

## Prossimo passo vincolante alla priorità del proprietario
- **Niente altri backup / test di ripristino PC o Android bloccanti per questo PAPER**, deroga documentata solo per denaro virtuale.
- Claude deve preparare il rilascio minimo a due parti: (a) reinstallare dalla run esistente i servizi Brain Unico senza duplicare/azzerare il journal; (b) pubblicare dashboard già esistente `/brain-unico` con API lette dalla run `brain-unico-paper-rc1` e abilitare chiusura manuale PAPER con conferma, senza aprire API mutative non necessarie.
- Confermare modalità PAPER esclusiva, exit service sano, pausa/ripresa, fail-closed, limiti profilo B, budget DeepSeek; verificare che il cutover web non rompa login, storici e rollback.
- **Non attivare mandato/trading 72h senza approvazione separata e esplicita**: dopo piano eseguibile breve e verifiche di collegamento dashboard chiedere consenso finale al proprietario.
- Claude resta consulente esterno; `deepseek-flash` è l'AI principale già configurata nel runner. Non dichiarare Claude come secondo modello automatico senza implementazione.
- Valutazione prima 72 ore = principalmente tecnica; analisi profitti/perdite con test prolungato successivo.

## Persistenza
- Questo registro salva esito e nuova decisione per la ripresa tra chat. Non equivale a certificazione del restore esterno né ad avvio operativo.