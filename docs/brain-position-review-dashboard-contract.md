# Revisione posizioni nel contratto servizio/app

31 ottobre 2026. Preparazione PAPER, nessun rilascio.

Il servizio pubblica account.position_review nello snapshot v2. mode deriva dalla configurazione corrente del supervisor (off/paper); senza supervisor esplicito è unknown. Il valore non è ricavato da una vecchia azione registrata.

status è none, recorded o unavailable. last contiene ts_ms, reviewer_checked, proposals ed executed. Le righe provengono dall'ultimo evento SQLite ai_position_review_observed già committato; massimo dieci proposte e dieci esecuzioni. reviewer_checked indica ricezione del secondo parere, non accordo su tutte le azioni. executed è l'unica fonte per dichiarare una chiusura o aggiornamento stop avvenuti.

Il lettore app controlla schema, timestamp non futuro, azioni consentite, limiti di righe e motivazioni. Telemetria malformata diventa unknown/unavailable senza invalidare il saldo. Snapshot vecchi privi del campo restano compatibili. La UI rende motivazioni come testo React, distingue proposte ed esecuzioni, e su dati scaduti presenta lo stato come storico senza dichiarare abilitazione corrente.

Verifiche locali: 90 test servizio +21 subtest (suite precedente89 più prova telemetria), 5 test contratto servizio/app, 16 test reader/API +8 subtest. Python3.12.14. CI remota da verificare sul relativo HEAD; nessuna prova browser/VPS o chiamata AI pagata inclusa.
