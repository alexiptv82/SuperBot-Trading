# 2026-11-01 — Audit finale pacchetto di accettazione R1/R2 consolidato

**Solo revisione documentazione/test — nessuna patch autorizzata o applicata.**

Input caricato nella chat: SuperBot_Long_R1_R2_Consolidated_Acceptance.zip, SHA256 debdbfad4373a6692dbe5c624519d2993ad61d5aabb2a3e5051c004cb940f763, ZIP CRC OK, SHA256SUMS 6/6 OK (7 file incluso manifesto).
Revisione del disegno: SPEC_ACCETTAZIONE_R1_R2.md, 21 test auditati, 6 test mode, matrice, piano di implementazione/rollback, risultati pre-patch e checksum.

Riproduzione indipendente su TC02.4 ORIGINALE, SHA256 archivio 2abf78ca525592ce77dca1b35c3fe56dbf5ddcbb7f1046edfcc4d4031f65d801:
- 21 test test_design: 17 PASS / 4 FAIL (d01 vecchio bypass capability, d09 qty missing strict, d19 e d20 mix ledger in due ordini con IDs diversi).
- 6 test del mode: 6 ERROR attesi, API non ancora implementata.
- Runner completo TC02.4: 163/163 PASS (82 baseline originali e 21 legacy migrati). Baseline V6.1.1 ZIP SHA 0c1ff499673aa5923444b66baae26cb5f98009973a3ea19fee27a8b620bd686e invariata.

**Verdetto: CONTRATTO DI ACCETTAZIONE APPROVATO**, patch NON autorizzata in questa fase; non è certificazione che R1/R2 siano già risolti. Il contratto definisce unico ENTRY costruito da PENDING + tick grezzi, rimuovere _ENTRY_CAPABILITY e _commit_validated_entry, strict qty obbligatoria; mode del ledger read-only e atomico, reject LEDGER_MODE_MISMATCH senza scritture; timestamp di tentativo non confuso con timestamp exchange, quote source availability/received e TTL esclusivo.

Note da verificare nell'implementazione autorizzata: mode-binding alla prima invocazione mode-aware anche se fallisce per input non validi, e riuso di PENDING preregistrato genericamente senza falso ALREADY_PENDING. Usare 27/27 test acceptance e 163/163 regressioni per gate post patch, contando legacy separatamente; audit indipendente dopo patch prima di qualsiasi freeze.

Report scaricabile in chat: AUDIT_FINALE_CONTRATTO_R1_R2_CONSOLIDATO_2026-11-01.md, SHA256 cf2f94b120bcb698654ad7b6831f462bed489ec916f38c63e5367af167e2ab11.

REAL_EXECUTION UNVERIFIED; ECONOMIC_EVIDENCE INSUFFICIENT; PAPER_ELIGIBLE NO. LONG V6.1.1, Brain, Falco, Toro, SHORT, VPS, wallet, capitale e protezioni invariati; nessun merge, deploy, trading o ordini.