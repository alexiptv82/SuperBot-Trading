# SuperBot LONG — design R1/R2 audit ChatGPT, 2026-11-01

**Ambito:** solo revisione della proposta Grok, NESSUNA PATCH applicata.
Input SuperBot_Long_TC024_R1_R2_Design_Only.zip SHA256 87534c9bf1f07e8aeb03f8ed10b30d2b24f4343d1b1a6be981e38fda5275a121; ZIP CRC OK, manifesto 5/5.
19 test del pacchetto rieseguiti su TC02.4 immutato: 18 PASS, 1 FAIL (d01 R1 confermato).
R2 design d16/d17 usano stesso event_id e ottengono ALREADY_TERMINAL, pertanto non provano isolamento modalità. Sonda separata con ID distinti: ENTRY legacy e strict in stesso ledger in entrambi gli ordini.
Ulteriori 7 test avversariali design-only: 1 PASS, 5 FAIL e 1 ERROR su codice vecchio (attesi, specifica ancora da realizzare). La prova di latenza da quote receipt è già verde e deve restare verde.

**R1** disegno di commit esclusivamente da tick grezzi è sensato ma test d01 importa _ENTRY_CAPABILITY a livello modulo: se patch rimuove simbolo, l'intera suite fallisce all'import. Correggere test con import di modulo + hasattr/getattr senza indebolire l'asserzione.
**R2** definire binding di mode per LabLedger anche con register_pending/consume chiamati prima delle funzioni mode-aware; read-only mode; prima del mismatch nessuna scrittura nemmeno protocol error. Aggiungere test cross-mode con due event_id, entrambi gli ordini, reason LEDGER_MODE_MISMATCH, snapshot identico dopo tentativo.
**Timing** il design attuale cita ts >= pending_receipt + latency, ma deve richiedere ts >= max(as_of, candidate_available, pending_received, quote_received) + latency, oltre a quote_available <= quote_received <= ts < valid_until; ricontrollare al commit.

Verdetto: DESIGN APPROVABILE CON CONDIZIONI, PATCH NON AUTORIZZATA; richiedere design revision e test aggiornati prima di patch. Nessun freeze, economic evidence INSUFFICIENT, real execution UNVERIFIED, PAPER_ELIGIBLE NO.
Materiali scaricabili in chat: REVISIONE_INDIPENDENTE_DESIGN_R1_R2_2026-11-01.md; TEST_INTEGRATIVI_DESIGN_R1_R2.py; PACCHETTO_REVISIONE_DESIGN_R1_R2_PER_GROK.zip (SHA256 9c881f80a94ade3828b55c7bc086ede7dc4eb9e1c0e69a9755773f2a61355bc9).
Il motore LONG V6.1.1, Brain, Falco, Toro, SHORT e protezioni invariati. Nessun merge, deploy, trading o azione VPS.