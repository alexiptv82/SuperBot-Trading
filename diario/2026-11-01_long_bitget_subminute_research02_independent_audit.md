# SuperBot LONG — audit indipendente Bitget Subminute Research 02
Data 2026-11-01; review ChatGPT; solo ricerca offline.

Input: SuperBot_Long_Bitget_Subminute_Research_02.zip, SHA256 553c460ab42b77fe7d24bb8355a15988f0cd0c853daef80b20118096f8199c70. ZIP CRC OK, 29/29 manifesto SHA256 valido e senza self-hash. Nessuna patch applicata.

Verifiche indipendenti: 866/866 raw WS sha PASS; 811/811 books1 e 162/162 trades raw→normalizzato identici in ordine e campi; BTC books 388, ETH books 423, BTC trades 102, ETH trades 60; 20 frame kline (10 per simbolo), 6 ACK; RTC frames da 2026-11-01T00:00:53.911Z a 00:01:18.802Z, circa 24.891 secondi. Quote positive, spread non incrociato, timestamp locali monotoni; NTP clock sync non verificato. Nessuna candela 1m chiusa confermata.

R01: reconciled 100 BTC REST +100 ETH REST+50 BTC WS, 250/250 e zero scarti; 16 file operativi preservati byte-per-byte dal ZIP originale, ma non inclusi originale REPORT_BITGET_SUBMINUTE_RESEARCH_01.md e SHA256SUMS.txt. Quindi preservazione INCOMPLETA.

Nuovi controlli offline: 26 gate, 22 PASS / 4 FAIL (4 gates negativi = R01 full preservation, clock sync, closed-kline, >=60 sec BBO). Nuovi 7 casi avversariali schema malformed al normalizer: 0 PASS/7 FAIL, accetta REST/WS prezzo o size negativo, NaN/Inf, timestamp invalido, lato mancante e exchange time > frame receipt (ultimo da quarantinare fino a clock sync). Individuata inoltre anomalia nel codice collector ws_capture_r02.py: OSError nei write book/trades finiscono nel ramo normalize, non write; non osservato nella cattura corrente.

Provenance raw interna/forma Bitget verificata, ma nessuna attestazione indipendente origine esterna, continuità pluriminuto o sincronizzazione. ESITO: R02 parzialmente validato come acquisizione, NO replay LONG, REAL_EXECUTION UNVERIFIED, ECONOMIC_EVIDENCE INSUFFICIENT, PAPER_ELIGIBLE NO.

Artefatti prodotti in chat: AUDIT_INDIPENDENTE_BITGET_SUBMINUTE_RESEARCH_02_2026-11-01.md, PROMPT_GROK_BITGET_SUBMINUTE_RESEARCH_03_2026-11-01.md, AUDIT_BITGET_RESEARCH02_INDEPENDENT_CHECK.py, AUDIT_BITGET_RESEARCH02_TEST_RESULTS.json, AUDIT_BITGET_RESEARCH02_NORMALIZER_ADVERSARIAL.py, AUDIT_BITGET_RESEARCH02_NORMALIZER_ADVERSARIAL_RESULTS.json. Pacchetto PACCHETTO_AUDIT_BITGET_RESEARCH02_PER_GROK.zip SHA256 1c50c3681f4bc2309b1ac08e0eff59d8f548cbbcd85a06b76e316197a49bedc9, manifest 6/6 OK.

Prossimo lavoro delegabile a Grok: Research03 SOLO collector/normalizer data-quality, preserve full R01, strict validation/quarantine, error phases, WS capture piu lunga e metadati clock. Non variare LONG V6.1.1, simulatore frozen TC02.4 R1/R2, Brain, Falco, Toro, SHORT, VPS, wallet, capitale. Nessun merge, deploy, ordini, PAPER o LIVE.