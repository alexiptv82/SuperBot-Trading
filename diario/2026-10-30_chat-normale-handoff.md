# Chat normale — passaggio da Work, 30 ottobre 2026 (Europe/Rome)

## Presa in carico isolata
L'utente ha riportato l'ultimo messaggio di Work: Work ha registrato il mandato ma **non ha ancora implementato** la revisione periodica delle posizioni; Work e' temporaneamente indisponibile per limite di utilizzo. L'utente chiede di continuare in questa chat e conferma che gli archivi di ripresa sono in GitHub e Library.

Chat normale ha riletto LEGGIMI, SINCRONIZZAZIONE-WORK-CHAT, MANUALE-OPERATIVO, STATO e checkpoint Library, verificando GitHub. Branch Work dichiarato work/brain-position-review-20261030 **non pubblicato** al momento del controllo; possibili modifiche locali Work NON toccate. Per evitare sovrascritture, nuovo owner temporaneo chat normale **solo** sul ramo distinto `work/brain-position-review-chat-20261030`, base `895b34a64058b1321ba5ad372e8de435f3e7fec0`. Quando Work torna, deve rileggere questo checkpoint e confrontare le proprie modifiche locali prima di qualunque integrazione.

Prima fase mirata: valutazione periodica autonoma delle posizioni aperte anche a scanner vuoto, con AI in worker, verifica posizione/versione/prezzo/scadenza, riserva budget condivisa, output **consultivo** e audit idempotente. Non attribuire alla prima fase la capacita' di eseguire una chiusura AI: la gestione attiva richiede transazione PAPER distinta con guardrail, prove di resilienza e contratto con l'app. Non alterare classici, wallet o storico; test di regressione e CI prima di qualunque merge.

Permessi: preparazione e test offline gia' autorizzati; **nessun merge, deploy, reset, API pagata, accesso VPS, ordini o apertura di seconda istanza** autorizzato in questo passaggio. PAPER permanente.
