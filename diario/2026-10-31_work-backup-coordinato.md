## 31/10/2026 11:59 Europe/Rome — Backup coordinato Brain PAPER verificato offline

FATTO/PREPARATO: utente conferma completamento degli aperti e incarico LONG ad altra AI. Prompt autonomo gia' disponibile in claude/prompt-long-engine-2026-10-31.md sul ramo diario: motore LONG isolato, ingressi/uscite/invalidation, SHORT preservato, consiglio Brain non vincolante, test causali e confronto fuori campione.

Nuovo ramo work/brain-coordinated-backup-20261031, base c23a0699ead68420d03d8c7d3399fc6766884f66, HEAD 854f03e733195a9ffa06184b24855c97660a8edc. Aggiunti recovery_bundle.py, 15 test dedicati, guida operativa e CI offline. Backup coordinato di wallet/eventi/budget AI persistito, registri teaching/lezioni/dedup comandi, inbox esplicita anche esterna e notifiche. Lock non bloccanti di tutti gli owner, BEGIN IMMEDIATE di tutti i database, SQLite backup con WAL incluso, copie DELETE/connessioni chiuse, inventario/hash/integrita'/identita'. File durevoli non mappati fanno fallire. Nessun arresto o avvio implicito.

Restore solo in directory nuova, conto/eventi/memorie preservati. Tutte le notifiche pending/inflight diventano uncertain; conferme pending/processing diventano needs_reconciliation. Un vecchio backup non puo' conoscere consegne successive: nessun reinvio automatico, ID e storici conservati. RESTORE.json indica ready_to_start=false. Inbox ripristinata in control/operator.sqlite3: percorsi servizio/app da configurare insieme. Il vecchio BrainService.backup e i workflow operativi restano invariati; non dichiarare inclusione automatica delle code nel backup esterno esistente.

TEST: locale Python3.12 84 PASS +6 subtest, inclusi15 recovery. Conto temporaneo reale con apertura, chiusura manuale profittevole, conferma e memoria -> backup -> restore -> uguaglianza integrale stato/journal; code senza replay, owner attivi, WAL e writer inbox, destinazione esistente, file mancanti/extra/manomessi, symlink/traversal. CI41194852380 SUCCESS su Python3.10/3.11, test e guardia dei componenti esistenti PASS. Prima prova recovery aveva evidenziato sidecar WAL nelle copie SQLite: corretto usando journal DELETE e chiusura esplicita prima del manifesto; nessun test indebolito. Preparazione locale iniziale priva di pytest: dipendenze isolate in scratch, nessun ambiente operativo modificato.

RILASCIATO: nulla. Nessun merge/deploy/reset/servizio/VPS/messaggio Telegram reale/API AI pagata. Solo sorgenti su ramo di lavoro; conti esistenti, classici e SHORT preservati.

APERTO: packaging installazione e inclusione nella retention esterna cifrata, topologia/mandato/provider/modelli/prezzi/budget/credito/destinazione definitivi, collaudo PWA autenticata/feed/Telegram e staging/restore operativo prima di esame finale all'avvio. Restano analisi multitimeframe estesa, ricercatore strategie e validazione fuori campione: non dichiarati completati. Dati futuri holdout non disponibili oggi; codice/test verdi non sono evidenza economica. LONG resta all'altra AI, senza integrazione implicita.

PROSSIMO: completare analisi/ricerca sperimentale secondo mandato e dati causali, poi confezionare installazione coordinata su versioni fissate; confermare configurazione reale e riconciliare costi/azioni successivi a qualsiasi backup prima di avvio. Nessun nuovo permesso di deploy inferito.
AI: ChatGPT Work

---

