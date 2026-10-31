# SuperBot LONG — Bitget Subminute Feasibility 01
Data: 2026-11-01 (Europe/Rome); AI: ChatGPT; ricerca dati pubblici in modalità solo lettura.

**Premessa:** SuperBot LONG V6.1.1 e TC02.4 R1/R2 Patch01 congelati come riferimenti; nessuna modifica a sorgenti, bot, branch operativi, VPS, wallet o trading.
Frozen LONG V6.1.1 SHA256: 0c1ff499673aa5923444b66baae26cb5f98009973a3ea19fee27a8b620bd686e.
Frozen TC02.4 R1/R2 Patch01 SHA256: 3342022e94c5e852062a7f24f235d12f3d4fa70b368b86b6a5a88a694cc8ad36.

Ricerca Bitget documentata:
- v3 GET /api/v3/market/fills = ultimi 100 trade pubblici; non è storico completo, non dimostra bid/ask ed eseguibilità.
- v3 GET /api/v3/market/orderbook = snapshot bid/ask con qty e timestamp.
- WS pubblico wss://ws.bitget.com/v3/ws/public: books1, publicTrade, kline 1m; cattura raw, timestamp locali, schema per trades WS p/v/T/S/i.
- Data download www.bitget.com/data-download pubblica storici trades e depth; verificare tipo, copertura e granularità effettivamente esportati. Non inventare received_at per dati storici.

Prova rete locale realmente eseguita: 4 richieste REST read-only BTCUSDT ed ETHUSDT (fills + orderbook), 0 successi, tutti con errore DNS risoluzione api.bitget.com. Nessun dato di mercato autentico raccolto in questo ambiente. Il log originale dell'errore è nel pacchetto.

**Artefatti CONSEGNATI in chat:** SuperBot_Long_Bitget_Subminute_Feasibility_01.zip SHA256 6fd5efcf6618a1c471974e4aed4cc4d91e6d70a2b1d0af8dac42f66a9098b905, 12/12 manifest internal hashes PASS, fresh unzip test PASS. Report REPORT_FATTIBILITA_BITGET_01_2026-11-01.md; Prompt PROMPT_GROK_BITGET_SUBMINUTE_ACQUISITION_01.md.

Il pacchetto include read-only recorder REST/WS, inspector offline di CSV/ZIP storici, documentazione, 18/18 test unitari con fixture synthetic solo nei test, log reale errori DNS, quality report e SHA manifest. Nessuna API key, nessun accesso privato o ordine. WS capture non testata su rete reale e quindi NON validata operativamente.

Gate: PUBLIC_SUBMINUTE_CHANNELS_DOCUMENTED YES; REAL_BITGET_DATA_CAPTURED_HERE NO; DATA_PROVENANCE_VERIFIED NO; REAL_EXECUTION UNVERIFIED; ECONOMIC_EVIDENCE INSUFFICIENT; PAPER_ELIGIBLE NO.

Prossimo passo: audit indipendente Grok del codice collector, poi esecuzione di una breve sonda pubblica e registrazione WS su ambiente in rete autorizzato, esportazione raw/hash e nuovo audit ChatGPT; nessun merge/deploy e nessuna promozione Paper.