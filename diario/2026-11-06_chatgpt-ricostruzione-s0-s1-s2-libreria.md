# SuperBot V3 — Ricostruzione tecnica S0/S1 e prova integrata S2 — 6 novembre 2026

**Stato:** consegna ricostruita e verificata in isolamento; **NON** recupero binario degli ZIP originali; nessun merge, deploy o riavvio.

## Recupero Library
Gli ZIP originali sono nella Libreria ChatGPT `/SuperBot-Trading`:
- `SuperBot-V3-Supervisore-S0-6-Servizi-2026-11-06.zip`, library_file_id `libfile_96f439c5281c8191b270c7ccdf1d97eb`, 14129 byte, SHA256 storico `99788dafe1e09d24ae1a61da58b959e5a55c19b294c9cee84acce51753473d14`.
- `SuperBot-V3-Supervisore-S1-Evidenze-2026-11-06.zip`, library_file_id `libfile_fb5ffe4f6714819192bd0737305e4bb4`, 21550 byte, SHA256 storico `221c42b3c67c5826bda30bb97e532c0a073441bca16f5fa9d823fa5f6e8bf8ff`.

Entrambe le materializzazioni dal Files tool sono state rifiutate per path raw non autorizzato; lettura del contenuto zip non disponibile. Non cancellare né sovrascrivere gli originali.

## Ricostruzione separata (NON byte-identica)
A partire dalla baseline ZIP `e25c8dd` e dai sorgenti S2 `SuperBot-V3-S2-Provenienza-Gate-2026-11-06.zip`, ricostruiti `backend/v3/supervisor/trace.py` e `evidence.py`. Coprono S0 read-only (decisioni+outcome ufficiale), S1 con osservazioni append-only e risoluzioni, e proiezione conservativa S2. Sono moduli opt-in, **non attivati nel runner**.

**Test:** 10/10 nuovi end-to-end (compreso S0→S1→S2 HTTP autenticato con journal reale, NO_TRADE, scarti e vera chiusura PAPER con calcolo outcome ufficiale); 350/350 mirati inclusi journal, L1, freno giornaliero e chiusura manuale. Due test S2 storici che pretendono 503 per moduli assenti esclusi, poiché ora i moduli ci sono; nota nel rapporto. Da /tmp: 10/10.

**NON eseguiti:** confronto con originale S0/S1, le loro suite storiche 31/83, suite completa da 6k, Jest, CI sul branch GitHub, deploy/VPS o benchmark live.

## Nuovi file salvati nella Libreria ChatGPT
- `/SuperBot-Trading/SuperBot-V3-S0-S1-RICOSTRUITI-S2-Prova-2026-11-06.zip`, SHA256 `18bfe54790d2b7301c64593e86d012cff5f46a81a028a754b0fe7b8627e337a4`, library_file_id `libfile_2a4a4a2373e881919ac46de3df95f24e`.
- `/SuperBot-Trading/RAPPORTO_SuperBot_V3_Ricostruzione_S0_S1_2026-11-06.md`, library_file_id `libfile_294fc3c87ff88191bcf29e7bf6d5c308`.

**Next:** usare gli originali se si sblocca l'accesso ai byte; altrimenti revisionare la ricostruzione sul branch di integrazione con PR #57/#61, aggiungere test mancanti e CI. Sempre PAPER e nessun merge/deploy senza l'OK dell'utente.
