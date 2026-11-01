# 2026-11-01 — SuperBot LONG Bitget Subminute Research 04 audit indipendente

**Scope:** review dati e strumenti offline. Non toccare LONG V6.1.1, simulatore TC02.4 R1/R2, Brain, Falco, Toro, SHORT, protezioni wallet, VPS, PAPER o LIVE.

Input utente: SuperBot_Long_Bitget_Subminute_Research_04.zip SHA256 730231866e8436007a1ae8efb1b2bcbffdb49a53e4b10e947413df41ceb450d9. CRC ZIP PASS. 15/15 manifest SHA256 PASS, 33791/33791 raw-frame hash PASS. Originali Research01/02/03 preservati come ZIP hash congruenti (R01 6a0e66200183c5a2f4ae0bc51008919ac5a52662ac008090ec2674950eca319f, R02 553c460ab42b77fe7d24bb8355a15988f0cd0c853daef80b20118096f8199c70, R03 9b89d6f0a3161f0cfc480719a3de959a2381fda6dc8de42815ca561a63eabf00).

Analisi indipendente di tutti i frame: 31717 books1 validi, BTC11322 ETH20395; 1463 frame publicTrade contenenti 3634 record, BTC2366 ETH1268, di cui 391 duplicati per (symbol,trade_id), preservati e segnalati; 581 frame kline; 30 ACK di sottoscrizione (10 books1) amministrativi. 31717/31717 BBO e 3634/3634 trade normalizzabili offline, zero quarantene dati market. Nessun book crossed/locked e nessun ts exchange futuro rispetto al receipt sul campione.

Finestra acquisizione ~603s in 5 sessioni con reconnect, BBO span BTC597.305s ETH597.541s; gap >1s BTC24 (max2471ms), ETH11 (max2373ms). Delta ricevuta–exchange mediana ~21ms NON prova NTP/latenza certificata; clock locale receipt-mono delta stabile al millisecondo. Nessuna prova di closed 1m, solo L1 non certifica eseguibilità e non è storico economico per multi-TF.

Tests R04 riprodotti: 18/18 PASS con PYTHONPATH=code, di cui 3 write-fault NON end-to-end (2 su classi finte, 1 text search), senza PYTHONPATH fallisce import. Suite ChatGPT 12 nuovi casi: 2 PASS, 9 FAIL, 1 ERROR. Difetti su input costruiti: books missing/bogus ts accettato, bool receipt, exchange timestamp > receipt, book nested malformed lancia IndexError, locked book, instType spot classificato futures in books e trade, bool receipt su trade, subscribe ACK classificato empty_book quando inviato al normalizer. Sui raw R04 non si sono rilevati questi input anomali.

Fault injection runtime effettivo su capture() con WebSocket fake e OSError su ff.write: stesso errore segnalato due volte ('write' e 'network'), WRITE_ERROR_PHASE_UNIQUENESS FAIL. Normalizzati derivati nell'audit (non presenti nel ZIP Grok) e hash propri; NO nuova cattura dati. Data provenance interna coerente ma non verificata esternamente.

Gate: RAW_INTERNAL_INTEGRITY PASS, RAW_BBO_TRADE_RECONCILIATION PASS su R04, BBO_TEMPORAL_COVERAGE MEASURED 10min, NORMALIZER_ADVERSARIAL_STRICTNESS FAIL, WRITE_ERROR_PHASE_UNIQUENESS FAIL, CLOCK_SYNC_EXTERNALLY_VERIFIED NO, CLOSED_1M_EVIDENCE NOT_VERIFIED, PROVENANCE_EXTERNAL_VERIFIED NO, LONG_CAUSAL_REPLAY_READY NO, REAL_EXECUTION UNVERIFIED, ECONOMIC_EVIDENCE INSUFFICIENT, PAPER_ELIGIBLE NO.

Artefatti chat: AUDIT_INDIPENDENTE_BITGET_SUBMINUTE_RESEARCH_04_2026-11-01.md; PROMPT_GROK_BITGET_SUBMINUTE_RESEARCH_05_2026-11-01.md; PACCHETTO_AUDIT_BITGET_RESEARCH04_PER_GROK.zip SHA256 067737b3dde755dc8ff8d4eeb630f2724c33d4f21ea96250bdbf36adf7094eb5, manifesto 12/12 OK; contiene 31717 BBO e 3634 trade normalizzati offline, script/test/fault injection e report.

Prossimo Grok Research05 = fix MINIMO solo normalizer/recorder e packaging normalizzato, re-test sui raw R04, niente strategia LONG o reinvenzione di quote; nuova cattura solo se utile, nessun deploy. Audit indipendente prima di eventuale replay causale.