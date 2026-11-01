# 2026-11-01 — Audit indipendente SuperBot LONG Bitget Research 05.1

Ambito: audit offline dello ZIP utente, nessuna modifica a LONG V6.1.1, harness R1/R2 congelato, Brain, Falco, Toro, SHORT, wallet, VPS, capitale, né trading PAPER/LIVE.

Input SuperBot_Long_Bitget_Subminute_Research_05_1.zip SHA256 `765533606c0a58d04e90b9812d2e6b2a1e28a36f5ffb01aafc0114c9d9401bdc`. CRC ZIP OK; manifesto 16/16 hash PASS; 17 file totali incluso manifesto; nessun self-hash.
Preserved R04 SHA256 `730231866e8436007a1ae8efb1b2bcbffdb49a53e4b10e947413df41ceb450d9`, preserved R05 SHA256 `11777f050a25c9d64e0f3ab3ea46fb953bfbe38ae45dc150fa8b503500623360` entrambi corrispondenti ai riferimenti. Nessuna nuova acquisizione Bitget.

Test originali riprodotti 39/39 PASS (15 adversarial, 3 write, 8 failclosed, 1 connect OSError, 12 indipendenti R04) e fault injection recorder end-to-end separata PASS: una sola fase write; connect OSError una sola fase network. PYTHONPATH impostato su cartella code dello ZIP.
Rielaborazione fresca dai 33791 raw frame del preserved R04: 31717 BBO, 3634 trade, 391 duplicati marcati, 30 ACK, 581 kline, 1463 frame publicTrade. Quattro output books/trades/quarantine/summary identici byte-per-byte a R05.1.

Nuovi 11 test indipendenti del boundary parser: 4 PASS, 1 FAIL, 6 ERROR sul R05.1 invariato. Rest top-level list/null causa AttributeError; books1 wrapper list causa AttributeError; timestamp string lunghissimi causa ValueError prima della quarantena; una linea JSONL esterna non valida abortisce intera normalizzazione e lascia output parziali; conversione format(float,'f') può convertire 1e-7 in 0.000000 e mettere in quarantena un numero positivo senza spiegazione di precisione. Nessuno di questi input avversariali è stato osservato nei raw R04.

Verdetto: R05.1 valido per reprocessing dei raw R04 già archiviati; pipeline nuove catture ancora NOT_READY per fail-closed del parser envelope e output atomici. REAL_EXECUTION UNVERIFIED, ECONOMIC_EVIDENCE INSUFFICIENT, PAPER_ELIGIBLE NO. Frozen engine/harness invariati.

Artefatti creati in chat: PACCHETTO_AUDIT_BITGET_RESEARCH05_1_PER_GROK.zip SHA256 `9336db12a4326c7693044f0abc9ac51054a0f6561c3e95dc17ab8d5c5a7cb897`, REPORT `AUDIT_INDIPENDENTE_BITGET_RESEARCH_05_1_2026-11-01.md`, nuovo script `TEST_INDIPENDENTI_BITGET_R051_BOUNDARY.py`, risultati e `PROMPT_GROK_BITGET_RESEARCH_05_2_2026-11-01.md`. Prossimo Research05.2: patch MINIMA solo ingest/parser/atomic output, no nuova cattura, poi nuovo audit prima di promuovere pipeline.