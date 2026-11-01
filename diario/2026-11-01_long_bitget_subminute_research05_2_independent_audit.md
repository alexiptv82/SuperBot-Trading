# 1 novembre 2026 — Audit indipendente Bitget Subminute Research 05.2

**Input:** SuperBot_Long_Bitget_Subminute_Research_05_2.zip; SHA-256 `2e0df73c5593319c07274d32104d52a106a2651132a58488bd3c43c69516ccae`; ZIP CRC PASS; manifest SHA256SUMS **18/18 PASS**, senza self-hash.
Archivio incorpora immutable preserved_R04.zip SHA `730231866e8436007a1ae8efb1b2bcbffdb49a53e4b10e947413df41ceb450d9`, R05 SHA `11777f050a25c9d64e0f3ab3ea46fb953bfbe38ae45dc150fa8b503500623360`, R05.1 SHA `765533606c0a58d04e90b9812d2e6b2a1e28a36f5ffb01aafc0114c9d9401bdc`. Nessuna nuova cattura Bitget.

**Test riprodotti:** suite R05.2 38/38 PASS, regressioni indipendenti R04 12/12 PASS. I vecchi 11 test indipendenti R05.1 NON allegati allo ZIP ma disponibili in chat: 10 PASS, 1 ERROR (normalize_books1_frame([1,2]) solleva AttributeError). Nuovi 5 test indipendenti R05.2 di ChatGPT: 3 PASS, 1 FAIL e 1 ERROR.

**Replay raw indipendente:** estratti 33791 frame dal preserved_R04 e rigenerati 31717 BBO, 3634 trade, 391 duplicati, 30 ACK, 581 kline e quarantena 0. Quattro output R05.2 rigenerati identici byte-per-byte.

**Nuova criticità P1 del publisher:** con un precedente summary `complete=true`, avviare un secondo run con 2 libri e forzare OSError sul 2° os.replace lascia il nuovo books1 già pubblicato mentre summary precedente continua a dichiarare complete=true con 1 libro. Non atomicità multi-file già dichiarata, ma certificazione del vecchio summary non fail-closed: non approvare consumo automatico senza invalidazione o versioning atomico. Nuova suite test_i02 FAIL.
**P2:** API diretta normalize_books1_frame accetta erroneamente envelope tipo list con AttributeError (test_i01 ERROR, anche caso già presente negli 11 test R05.1). Tre controlli ulteriori PASS: book valido, kline/ACK con SHA corrotto rilevati nella seconda passata di riconciliazione.
**Nota minore:** except OSError in normalize_full incrementa write_errors anche per errori di lettura; non emerso nel campione R04.

**Verdetto:** Research05.2 parzialmente validato, funzionante per rielaborazione R04 integra; NON pronto per nuove catture non presidiate. Il quote-age/BBO continuity study sui dati R04 può avanzare in parallelo solo esplorativamente, senza backtest o eseguibilità dichiarata. REAL_EXECUTION UNVERIFIED, PROVENANCE_EXTERNAL_VERIFIED NO, ECONOMIC_EVIDENCE INSUFFICIENT, PAPER_ELIGIBLE NO.

**Artefatti in chat:** AUDIT_INDIPENDENTE_BITGET_RESEARCH_05_2_2026-11-01.md; PROMPT_GROK_BITGET_RESEARCH_05_3_2026-11-01.md; TEST_INDIPENDENTI_BITGET_R052_REGRESSIONI.py; PACCHETTO_AUDIT_BITGET_RESEARCH05_2_PER_GROK.zip SHA `e34b748467bb952a37c84440355398bdec2d70dff08d9fef5ebd228285391810`, manifesto proprio 4/4. Suggerita patch MINIMA R05.3 della sola data pipeline, nessuna nuova raccolta.

LONG V6.1.1, harness R1/R2 sintetico congelato, Brain, Falco, Toro, SHORT, wallet, capitale, VPS invariati. Nessun merge/deploy/trading PAPER/LIVE.