# TORO LONG — pre-registrazione immutabile dell'ipotesi P (funding estremo e recupero)

**Data della decisione:** 13 novembre 2026 (Europa/Roma). **Fase:** ricerca in sola lettura; **nessun test avviato, nessun deploy/merge**, nessuna modifica alle unità Falco/Toro/Brain.  
**Documento fonte:** `TORO-LONG-nuova-ipotesi-rapporto-Claude-2026-11-13.md` di Claude Fable 5.2, sezioni D–F (trasmesso dall'utente).  
**PR V1:** #96, BOCCIATA nel Passo 0. Questa pre-registrazione è su **ramo separato**, affinché il commit sia precedente a qualsiasi risultato della nuova ipotesi.  
**Stato del consenso:** l'utente ha trasmesso la richiesta Claude di confermare il Passo 0′ con precisazioni; questo documento fissa i criteri e **non costituisce autorizzazione a cambiare il rischio operativo o avviare LIVE/PAPER Toro**. Nessun run del Passo 0′ da eseguire prima del data-quality gate.

## 0. Correzioni vincolanti rispetto ai riassunti precedenti

1. **NON inserire filtro rischio/rendimento o target R:R nella regola d'ingresso P.** Claude specifica solo la distanza tecnica dello stop: **0,8–2,5 ATR**. Il precedente filtro R:R ≥1,3 della V1 NON si trasferisce alla P.
2. **Unico orizzonte primario: 24 ore**. Otto ore è analisi secondaria descrittiva, non può promuovere una strategia che fallisce a 24 ore.
3. **TRE controlli**: (i) LONG casuale sullo stesso simbolo e mese; (ii) LONG casuale con funding negativo ma senza innesco di prezzo; (iii) **identico innesco di prezzo senza condizione di funding**. Il controllo (iii) è il falsificatore della premessa che il funding aggiunga informazione. 1.000 semi per ogni controllo, con esposizione temporale e costi confrontabili; conservare semi/campioni/criteri di matching.
4. **Archivio di OGNI trade** e non solo medie: simbolo, timestamp decisione, timestamp funding *settled* già noto, prezzo ingresso (apertura candela successiva), uscita a 8/24h, PnL prezzo lordo, funding distinto, commissioni/slippage modellati separatamente, MAE/MFE, durata e regime, flag holdout, episodio e blocco giorno per bootstrap. SHA256 di dati e codice eseguito; risultati per mese e per simbolo.
5. **Numero di segnali mensili**: totale, per simbolo, e distribuzione mensile; indicare anche mesi senza segnale. Non confondere vantaggio 24h con volume di operazioni adatto allo scalp.
6. **Rischio operativo** non fa parte del Passo 0′: 12 USDT/trade, 24 USDT aperti è un'ipotesi della futura fase PAPER, non modifica il config della VPS oggi; 5 slot non impongono aperture. Limite perdita giornaliera residua e costi dovranno essere valutati prima di ogni apertura. Non toccare alcuna unit/strategia SHORT, Falco né Brain.

## 1. Universo, simboli hold-out e regola fissata prima dei risultati

La regola primaria Claude resta: ogni mese selezionare i **15 USDT perpetual più scambiati per volume negli ultimi 30 giorni**, calcolando volume e disponibilità **solo con dati precedenti al mese di decisione**, e **solo se la quotazione aveva già 365 giorni** a quel momento. Mai ricostruire l'universo storico con i 15 più scambiati del 2026 applicati al 2020 (survivorship bias). Se non si può ottenere volume storico per verificare questa selezione mese per mese, il data gate fallisce: **non usare l'ultimo top 15 corrente come scorciatoia**.

Per registrare da subito cinque simboli riservati, senza usare alcun risultato dell'ipotesi P, si congela un *pannello di riferimento per la selezione*, ordinato alfabeticamente e distinto dalla regola top 15 mensile:

`ADAUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, DOTUSDT, ETHUSDT, LINKUSDT, LTCUSDT, SOLUSDT, TRXUSDT, UNIUSDT, XLMUSDT, XRPUSDT`.

**Regola meccanica**, applicata ora e non modificabile: escludere i cinque simboli già osservati nel Passo 0 della V1 (`BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT`); scegliere i **primi cinque in ordine alfabetico** dal rimanente del pannello congelato.

**SIMBOLI HOLDOUT NOMINALI: `ADAUSDT, AVAXUSDT, BCHUSDT, DOGEUSDT, DOTUSDT`.**

Non sostituire un holdout per dati mancanti, scarso numero di trade, risultati negativi o scarsa liquidità. Uno holdout entra nelle osservazioni del mese **solo se** appartiene ai top 15 effettivi *di quel mese* ed era quotato da almeno 365 giorni; altrimenti registrare assenza. La soglia GO richiede tutti e 5 positivi e una copertura verificabile; se impossibile, **nessun GO**.

**Nota fondamentale:** “riservato” significa riservato all'**ipotesi funding P**; alcuni dei cinque potrebbero essere già stati studiati in esperimenti prezzo-only precedenti. Non rivendicare mai una verginità assoluta su tutta la storia del progetto.

## 2. Ipotesi P — regole originali, senza filtri aggiuntivi

- Serie: candele Bitget Futures **1H chiuse**, funding **regolato**; il tasso osservato deve avere timestamp settlement **<= momento della decisione**. Un tasso proiettato non ancora regolato NON soddisfa F1/F2.
- F1: ultimo funding regolato <0.
- F2: ultimo funding <= **10° percentile dei 90 giorni precedenti** per lo stesso strumento; il percentile deve essere calcolato **solo sui dati storici già disponibili a T**, escludendo il settlement T se richiesto per evitare autocampionamento: decisione di tie policy da codificare prima di esecuzione (non ottimizzabile sui risultati).
- F3: il minimo delle ultime 24 ore coincide con quello degli ultimi 7 giorni; dati disponibili entro la candela chiusa.
- Innesco entro 12 ore dal minimo: (T1) chiusura 1H > massimo delle tre candele precedenti; (T2) candela 1H rialzista (close>open).
- Veti: V1 ATR14 1H >95° percentile dei 30 giorni precedenti; V2 BTC ha candela ribassista di range>3ATR nelle ultime 3h; V3 1 ingresso già esistente nell'episodio (episodio finisce quando funding torna sopra propria mediana).
- Futura esecuzione: limit post-only alla chiusura del trigger, TTL 15min (solo per eventuale Passo 1/PAPER, **non** per simulare ingresso nel Passo 0′).
- Stop strutturale: minimo episodio −0,25 ATR; distanza tecnica tra **0,8 e 2,5 ATR**; altrimenti NO_TRADE. **NESSUN gate R:R**.
- Invalidazione episodio: funding regolato >= +0,01% oppure 24h trascorse.
- Correlazione futura: max 2 ingressi nello stesso intervallo 4h; il vecchio numero 40 USDT di rischio aperto nel report è in revisione e non viene attivato.

## 3. Ipotesi T di controllo e test storici

- T: BTC sopra SMA 50 giorni; simbolo 4H close>EMA200 e EMA50 4H crescente; ritracciamento 1H sotto EMA50 1H e chiusura sopra massimo candela precedente; stessi stop, orizzonti e costi.
- Test SOLO entrata su apertura della candela successiva al trigger, uscita **24h primaria**, **8h secondaria**, prezzo Bitget Futures, funding ai settlement pertinenti, nessun ordine di trading. La metrica primaria Claude: rendimento **lordo medio 24h con funding incluso**.
- Confronti casuali: 3 controlli di §0, 1.000 semi ciascuno; guardrail anti-lookahead; bootstrap a blocchi di giorni, raggruppamento giorni episodio, intervalli 95%.
- Esplorazione codice **2020–2023** soltanto per correttezza; validazione **2024–30 giugno 2025**; test finale **1 luglio 2025–13 novembre 2026**, una sola lettura del test finale dopo soglie bloccate. Per gli asset non quotati in parte di un periodo: NON inventare o estendere la storia.
- I cinque hold-out del §1 sono valutati per ultimi; non usare la loro performance per selezionare parametri; non modificare l'universo e il periodo dopo aver visto i risultati.
- **Osservazione Bitget in ombra per 8 settimane**, senza ordini, è una fase distinta e necessaria prima di ogni eventuale release.

## 4. Sei soglie GO invariabili (TUTTE obbligatorie)

1. **≥150 trade** ed **≥60 giorni-evento distinti**.
2. **Rendimento lordo medio 24h, funding incluso, ≥+25 bp (+0,25%)**; limite inferiore dell'**IC 95% >+10 bp (+0,10%)**.
3. Risultato positivo **sia in validazione sia in test finale**.
4. Performance **sopra il 95° percentile di tutti e tre i controlli**.
5. Nessun mese contribuisce >**30% del risultato** e rendimento totale resta positivo **rimuovendo il miglior 5% dei trade**.
6. Risultato positivo su **ognuno dei cinque simboli holdout** nominati al §1.

Se uno solo fallisce: **NO-GO**, nessuna modifica post-hoc delle soglie, dell'orizzonte, degli asset o dei filtri per “salvare” l'ipotesi. Il risultato non è una dimostrazione che tutti i LONG siano impossibili.

## 5. Gate DATI funding Binance ↔ Bitget prima del test dell'ipotesi

Fonte Bitget pubblica `/api/v3/market/history-fund-rate`: **ultimi 90 giorni**; il settlement varia per simbolo. Fonte Binance USDT perpetual: `/fapi/v1/fundingRate`. Storico Binance è una **PROXY** sul funding: non è il pagamento di funding reale su Bitget, e può essere diverso come intervallo/importo/segno.

**Limite dei dati**: 90 giorni di funding Bitget non consentono di calcolare retroattivamente il percentile mobile dei **precedenti 90 giorni** per T lungo tutto quel medesimo periodo. Quindi:
- Per il gate di *comparabilità tra mercati*, usare le distribuzioni 90gg **retrospettive** esclusivamente per diagnosticare corrispondenza cross-venue. Questo NON costituisce backtest del segnale né prova predittiva, né va riciclato nel modello temporale.
- Per ogni istante di osservazione decisionale (chiusura 1H) usare l'**ultimo funding regolato** su ciascun exchange; disallineamenti di settlement vanno registrati, non nascosti. Un evento “negativo ed estremo” su venue A richiede ultimo funding<0 e <=10° percentile empirico delle osservazioni di A nei 90 giorni. Lo stesso per venue B. Contare gli **eventi funding distinti**, non 8 copie della stessa liquidazione ripetute sulle candele 1H.
- **Soglia di coincidenza PREFISSATA adesso per la diagnostica proxy:** almeno **70%** degli episodi estremi-negativi Binance coincidono con episodi estremi-negativi Bitget nella loro validità oraria comune; per **ogni simbolo** almeno **60%**, almeno **10 episodi estremi Binance** osservabili e almeno **90% copertura** di istanti orari comparabili. Registrare precisione condizionata, matrice di confusione, conteggi e bootstrap per giorno, separatamente per simbolo.
- Se una soglia di questo gate fallisce, o se non si ricostruisce una storia affidabile 90d, **non dichiarare valida la proxy Binance per Bitget**. L'opzione è solo shadow con funding Bitget raccolto man mano oppure fonte storica alternativa con provenienza certificabile; non ritoccare le soglie di coincidenza.

**NOTA DI VALIDITÀ:** anche con gate coincidenza SUPERATO, il backtest 2020–2026 con Binance produce un risultato **surrogato**, non una prova di rendimento reale su Bitget. Non usare la proxy come se fosse funding incassato su Bitget. Il GO finale per Toro richiede successiva convalida 8 settimane shadow Bitget, plausibilità economica NETTA con costi e gestione rischio, e PAPER separato.

## 6. Criterio di arresto e isolamento

- Se P fallisce il Passo 0′, **stop alla ricerca di nuove varianti LONG puramente a regole in questa linea** (non “tutti i LONG saranno sempre perdenti”). T è il controllo predefinito, non un invito a moltiplicare esperimenti.
- Nessuna nuova strategia aggiunta all'ultimo momento; registrare positivi/negativi e conteggio di tutti i test.
- Nel Passo 0′ NON modificare risk config corrente di Toro. Per futuro PAPER proporre **12 USDT rischio per trade e 24 USDT rischio aggregato**, salvo approvazione specifica successiva; blocco nuove aperture prima che `perdita_giorno_realizzata + rischio_aperto_stimato + buffer_esecuzione` possa superare 30 USDT. Lo stop non garantisce massimo perdita in presenza di gap.
- NON toccare FALCO SHORT, le unit e la strategia originali; NON toccare BRAIN PAPER attivo sulla VPS Singapore; nessun trading LIVE, nessun deploy, nessun merge su branch operativo, nessuna modifica ai 2 hotfix Brain locali.
- Prima di qualunque esecuzione del nuovo Passo 0′: verificare che **QUESTO documento con tutti i sei GO, i 5 hold-out, i tre benchmark, il primary 24h e la soglia 70/60/10/90 sia committato e referenziato con SHA**, e verificare SOL V1 con il JSON originale. Se impossibile, NON AVVIARE il nuovo esperimento.
- Non eseguire GitHub Actions per questo protocollo se evitabile; usare test locali isolati, log e manifest con hash.

**FONTI UFFICIALI:**  
Bitget v3 market derivatives `https://www.bitget.com/docs/catalog/market/derivatives` (90gg funding).  
Binance USDT perpetual funding `https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data`.

**Questo file, e NON messaggi successivi, è la specifica pre-registrata del nuovo esperimento. Cambiamenti futuri richiedono una dichiarazione di nuovo esperimento, mai editing silenzioso di questo documento.**
