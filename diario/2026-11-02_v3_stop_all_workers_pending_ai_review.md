# SuperBot V3 — Checkpoint prima dello spegnimento generale (2026-11-02)

Decisione dell'utente: sospendere tutti i servizi trading PAPER e tutti i worker AI/shadow, per evitare chiamate ai provider mentre si progetta V3. Mantenere disponibile se possibile la dashboard per consultazione. Non modificare configurazioni, wallet o storico. Non cancellare nulla.

Stato verificato dall'utente durante la chat:
- Pool: container superbot-pool fermato e backup ripristinabile PASS, in /opt/superbot-pool-backups/20261102T125929Z; 291 trade chiusi e 1 open nel journal storico, PR #28 non distribuita.
- Brain Free: nell'ultima diagnosi riportata era paused=True con 0 open PAPER, Shadow in pausa senza nuove model call; lo stato odierno deve essere verificato, come gli eventuali worker secondari.
- Falco e Toro: precedentemente running, app con controlli Pausa. Non ancora verificato stop/pausa successiva.
- Nessuna operazione remota eseguita da ChatGPT: non dispone di SSH nel contesto di questa chat.

Procedura concordata: prima inventario Docker e stato PAPER, identificazione inequivoca di tutti i worker (Hawk, Bull, Brain Free/Pilot/Shadow e servizi AI); poi sospensione e stop mirato dei soli worker, backup consistente dello storico e controllo che non partano nuove chiamate AI. Evitare di fermare dashboard, reverse proxy o altri progetti. Nessun riavvio automatico fino a decisione esplicita.

Nuovo design da valutare con due AI indipendenti (prompt già consegnati): cervello centrale con DeepSeek H24 e Claude di supporto selettivo; tre wallet PAPER indipendenti da 1000 USDT ciascuno; Brain portfolio con decisioni AI adattive nel rispetto di hard risk; classici per regole; memoria comune di trade, errori, contesto e feedback manuale; app unificata con apertura, pausa, chiusura singola/parziale e teaching; validazione controfattuale e fuori campione; confronto omogeneo per rischio e costi. Risposte delle due AI non ancora ricevute e modifiche architetturali non ancora approvate al deploy.
