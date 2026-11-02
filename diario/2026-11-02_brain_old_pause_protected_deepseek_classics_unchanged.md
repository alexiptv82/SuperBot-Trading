# 2026-11-02 — Direttiva utente: sospendere Brain AI precedente per ridurre consumi DeepSeek

**Richiesta**: l'utente considera bocciato Brain libero attuale dopo drawdown riferito circa 50% e vuole interrompere la sua attività AI H24 fino al lancio della versione nuova rules-governed. Classici Falco/Hawk e Toro/Bull devono rimanere operativi e invariati, perché prevalentemente rules-only. Vuole inoltre Rescue OVH Singapore per aggiungere chiave SSH Termius, senza perdita di dati.

## Scelta operativa sicura

- Preferire **PAUSA PROTETTA del solo Brain attivo** tramite `pause.flag` sulla cartella dati corretta (solo dopo verifica versione e source), **NON** `docker stop` immediato: se ci sono posizioni PAPER aperte, gli stop/target locali gestiti nel loop si fermerebbero assieme al container. Pausa evita aperture e nuovi cicli AI del Brain, mantenendo protezione price-based, heartbeat, stato e storici. Non cancellare dati e non resettare portafoglio.
- Il codice del Brain Free V2 deploy target `e0021488b47e8b245954a708b139bc4785a4b644` in `backend/director/brain_free/runtime.py` legge `(self.store.root/'pause.flag').exists()` come `state['paused']`, chiama `protect(...)` anche quando paused, e programma nuove model call solo se `not state['paused']`. La revisione `work/brain-completion-20261031` mantiene il comportamento. Brain Pilot (`rule-pool/backend/director/brain_pilot/pilot.py`) usa la sua `pause.flag` per impedire le chiamate AI e nuove esposizioni. Una chiamata già in-flight e diagnostiche saldo/API sono possibili; verificare che le richieste AI si fermino veramente e che non girino legacy AI separati.
- Deployment V2 Free registrato GitHub Actions run **40689858961** (2026-10-28, success), e altri deploy app dopo. Quindi workflow `.github/workflows/brain-free-reframe-pause.yml` legato al V1 SHA `a914803a...` non va riutilizzato senza nuova validazione runtime; il vecchio workflow potrebbe rifiutare o riferirsi a versione non attuale.
- È ancora **NON ATTESTATO** quale Brain Free/Pilot/legacy sia ora writer nel VPS Singapore. Non creare indiscriminatamente file pause su molte directory né arrestare container con nomi simili. Accertare da Termius/OVH console dopo accesso e verificare heartbeat/pausa. Un servizio `superbot-ai` shadow potrebbe essere indipendente: solo diagnostica prima di considerare costo DeepSeek azzerato.
- Classici Falco/Toro: non toccare pause.flag, container, env né deploy; salvaguardare protezione assoluta 450 USDT e storico. Il Rescue mode per recuperare accesso root SSH **riavvia temporaneamente l'intera VPS**, quindi interrompe anche classici. Prima del Rescue, verificare posizioni aperte e natura di stop locali vs exchange; in PAPER gli stop locali richiedono processo attivo. Non dichiarare che i classici restino attivi durante Rescue.

## Stato esecuzione

Al 2026-11-02 nessuna sessione SSH/VPS disponibile e il tentativo precedente di workflow per installare chiave Termius è stato bloccato dai controlli; quindi **NON È STATO INVIATO ALCUN COMANDO DI PAUSA** e consumo DeepSeek non è ancora dichiarabile interrotto. L'utente ha fornito chiave pubblica ED25519 per Termius, privata mai condivisa. Accesso root su Singapore richiede autorizzazione chiave attraverso Rescue/procedura provider; non è stato eseguito.

## Sequenza proposta

1. Verificare nella dashboard quante posizioni Brain e classici sono aperte e se i livelli di protezione sono soltanto locali. Fare backup di stato e storici prima di un arresto totale.
2. Recuperare accesso SSH Termius, se proprio necessario con Rescue in finestra sicura (tenendo conto del fermo temporaneo di tutti i bot).
3. In modalità normale elencare i container e verificare il vero Brain writer e la sua directory. Applicare pausa persistente solo a esso, senza docker stop; verificare `paused=true`, loop/stop locali vivi, nessuna nuova richiesta DeepSeek. Se Brain è flat e la gestione locale non serve, eventuale stop mirato + restart policy dopo altra verifica.
4. Lasciare Falco e Toro invariati. Al rilascio Brain rules-governed, fare backup e migrarlo con controllo ristretto e autorizzazione separata; non riattivare il Brain precedente.

**Gate**: BRAIN_AI_PAUSE_REQUESTED=YES; BRAIN_AI_PAUSE_EXECUTED=NO; BRAIN_RUNTIME_OWNER_VERIFIED=NO; CLASSICS_CONFIG_UNCHANGED=YES; RESCUE_STARTED=NO; PAPER_NEW_BRAIN=NO; PR26_DRAFT_NO_MERGE; PR27_DRAFT_NO_MERGE.