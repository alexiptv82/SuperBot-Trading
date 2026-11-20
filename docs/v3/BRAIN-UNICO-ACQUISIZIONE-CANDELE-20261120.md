# Acquisizione delle candele pubbliche 15m/1h/4h per la validazione (procedura, NON eseguita)

**Stato:** preparata e testata solo offline (`backend/tests/test_v3_acquire_candles.py`, finto endpoint). **Nessun download eseguito.** Serve l'autorizzazione del proprietario prima del primo comando con `--confirm-network`.

## Scopo
Fornire al Dataset Builder un archivio di candele con **provenienza verificabile**:
- per verificare in modo indipendente le feature degli snapshot (`--decision-candles`);
- per le etichette di mercato (`--candles`, solo 15m).

Senza questo archivio gli snapshot restano `snapshot_unverified` e le righe con etichette di mercato restano `market_data_unattested`.

## Fonte
- **Endpoint:** Bitget `GET https://api.bitget.com/api/v2/mix/market/history-candles`, con `productType=USDT-FUTURES` e granularità `15m`, `1H`, `4H`. È pubblico e non usa chiavi.
- **Stessa funzione del runtime:** lo strumento chiama `backend.v3.lab_tools.fetch_candles.fetch_rows`, la stessa del Brain. Si ferma senza scrivere se le righe derivate dalle risposte grezze non coincidono con quelle del runtime.
- **Limite:** prova che i file sono ciò che Bitget ha risposto, non che Bitget abbia ragione. Il volume è `baseVolume`, la colonna 5, come nel runtime.

## Simboli e periodo
- **Simboli:** gli 8 del runner, cioè BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, BNBUSDT, DOGEUSDT, ADAUSDT, LINKUSDT.
- **Inizio:** primo istante di decisione da validare **meno 37 giorni**. Il runtime tiene circa 30,4 giorni di candele a 15m, 31,5 a 1h e 36,2 a 4h, e lo snapshot registra la finestra esatta usata.
- **Fine:** ultimo istante di decisione **più l'orizzonte massimo delle etichette**, oggi 24 ore. Mai oltre l'istante di acquisizione: le candele aperte non si scaricano mai.

## Dimensione stimata (`--plan`, nessuna rete)
| Periodo | File | Richieste | Righe | Byte (dati + grezzi) |
|---|---|---|---|---|
| 47 giorni (es. 15/10 – 1/12) | 24 | ~272 | ~47 400 | ~12 MB |
| 106 giorni (es. 1/10 – 15/1) | 24 | ~568 | ~106 800 | ~27 MB |

Le richieste sono distanziate di almeno 90 ms, con nuovi tentativi su 429/5xx: pochi minuti in tutto.

## Destinazione
Una directory **nuova**, mai sovrascritta, fuori dal repository e fuori dai dati del bot. Proposta: `~/brain-unico-lab/data/candles-<AAAAMMGG>/`, nella home dell'utente di laboratorio, senza privilegi. Il repository è pubblico, quindi l'archivio non va committato.

## Contenuto dell'archivio
| File | Cosa contiene |
|---|---|
| `15m/<SIMBOLO>.jsonl`, `1h/…`, `4h/…` | dati derivati, valori come stringhe esatte |
| `<tf>/candles_meta.json` | provenienza dichiarata, con intervallo |
| `raw/<tf>/<SIMBOLO>/<n>.json` | ogni risposta grezza della fonte |
| `candle_manifest.json` | `manifest_id`, fonte, strumento e commit git, istante di acquisizione, per ogni file l'elenco delle richieste (URL completi) e lo SHA-256 di **ogni** file |

## Controlli
Sono eseguiti dal builder (`candle_provenance.check`), con verdetti separati.
- **Integrità:** ogni file è elencato nel manifest con hash coincidente; nessun file mancante né in più.
- **Provenienza:** richiede tutte queste condizioni:
  - la fonte è l'endpoint atteso;
  - ogni URL corrisponde a simbolo e granularità del suo file;
  - ogni file **viene riderivato** dalle sue risposte grezze e coincide;
  - ci sono solo candele chiuse all'acquisizione;
  - lo SHA-256 del manifest coincide con un'**ancora esterna**.
- **Coerenza delle feature:** `snapshot_verify` controlla il digest e ricalcola le feature con un'implementazione propria.
- **Requisito separato, l'attestazione del journal e delle decisioni:** Fase 0 (`attestation.py`), con ancora propria.

Ognuno di questi requisiti è necessario e nessuno sostituisce gli altri. Finché uno manca, i dati sono conservati ma **non** presentati come training certificato.

## Ancora esterna (a cura dell'operatore)
Lo strumento stampa `MANIFEST_ID` e `MANIFEST_SHA256`. **L'operatore**, non l'agente, li registra in un canale suo, per esempio un commento firmato nella Issue o un file tenuto da lui. Poi crea il file delle ancore, `{"<manifest_id>": "<sha256>"}`, da passare con `--candle-anchors`. L'ancora vale quanto la sua registrazione: non è una firma crittografica.

## Controllo incrociato facoltativo
Un secondo scaricamento, qualche ora dopo, in una nuova destinazione con `--compare-with <primo archivio>`. Il manifest registra candele confrontate e differenze. È un'informazione dichiarata: le differenze vanno indagate, perché Bitget può aver rivisto dei volumi.

## Passi (dopo l'autorizzazione)
1. `python3 ops/brain-unico/candles/acquire_candles.py --start <AAAA-MM-GG> --end <AAAA-MM-GG> --out <DIR_NUOVA> --plan`: solo la stima, da riportare al proprietario.
2. Con autorizzazione: lo stesso comando con `--confirm-network`.
3. L'operatore registra l'ancora.
4. Il builder gira con `--decision-candles <DIR> --candle-anchors <ANCORE>` (e `--candles <DIR>/15m` per le etichette). I verdetti nel rapporto sono `candle_archive_integrity`, `candle_provenance` e `feature_consistency`.

## Autorizzazioni richieste
| Attività | Serve consenso |
|---|---|
| Esecuzione con `--confirm-network`, cioè traffico di rete verso Bitget dalla macchina di laboratorio (la VPS) | sì |
| Scelta di periodo e destinazione | sì |
| Registrazione dell'ancora | dell'operatore, per definizione |
| Accesso a storici privati, journal o backup | non richiesto da questa procedura; resta soggetto alla Fase 0 e al consenso separato |
| Spesa | nessuna: dati pubblici gratuiti |
