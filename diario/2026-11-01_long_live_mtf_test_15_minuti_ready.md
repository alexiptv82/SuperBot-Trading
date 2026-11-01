# 2026-11-01 — SuperBot LONG Live MTF test 15 minuti: pacchetto autonomo

L'utente autorizza una prova breve da 15 minuti del laboratorio LONG WebSocket Bitget, prima di passare alla progettazione dell'integrazione in osservazione. NON autorizza modifiche operative o deploy; condizione economica/PAPER invariata.

ChatGPT ha preparato `SuperBot_Long_Live_MTF_Test_15_Minuti_01.zip` SHA256 `11f4907042b4d5b2f619f9b051bb86f5b058508fdec96fb167842ac0b7c89cf6` derivando dalla versione LIVE MTF Capture Lab01. Runner modificato SOLO a `capture_mtf.py --minutes 15 --output ...`; `capture_mtf.py`, `verify_capture.py`, `pack_results.py`, fixtures e 35 test originari restano byte-identici. README aggiornato e aggiunto test che fissa durata. Sorgenti immutati dal laboratorio originale.

Verifiche offline eseguite: unittest 36/36 PASS; `bash -n run_network.sh` PASS; `capture_mtf.py --help` espone flag `--minutes`; 11/11 SHA256 manifesto, ZIP CRC OK. Nessun frame live raccolto nel nuovo test. Ritento `socket.getaddrinfo('api.bitget.com',443)` fallito [Errno -3] Temporary failure in name resolution (DNS) da questa sessione.

Modalità autorizzata SOLO READ-ONLY, ambiente di ricerca con rete, NON VPS di produzione. L'utente può eseguire lo ZIP con `bash run_network.sh`: 900 secondi di cattura dopo preflight/warmup e 36 test, più tempi addizionali per setup, verifica e zip. Output `SuperBot_LONG_LIVE_MTF_RESULT_*.zip` da ricaricare per audit ChatGPT.

Condizione per proseguire: quality gate della raccolta 15m superato, 10/10 canali ACK e dati con ricezione osservata, no contaminazione futuro; poi preparazione integrazione **shadow soltanto** di LONG V6.1.1 per classici + Advisor Brain, senza ordini. 15m NON prova redditività, rollover 1H/4H, esecuzione o qualità per Paper. LONG V6.1.1/harness R1-R2 congelati, Brain/Falco/Toro/SHORT invariati. REAL_EXECUTION=UNVERIFIED, ECONOMIC_EVIDENCE=INSUFFICIENT, PAPER_ELIGIBLE=NO. Nessun merge/deploy.