# 20/11/2026 (3) — Claude: acquisizione candele (interrotta), duplicazione corretta, stati del dataset, memoria nell'app

**Ramo:** `integration/brain-unico-20261119` @ `8e03235d`, prima `3f1c5b9f`. Nessun deploy, nessuna modifica ai servizi VPS, nessun parametro attivo, nessuna spesa. L'unica attività di rete sono state l'acquisizione autorizzata e l'installazione di strumenti di sviluppo nella home.

## 1. Acquisizione autorizzata delle candele: interrotta in sicurezza, nessun archivio
**Prima di eseguire** ho aggiunto i limiti rigidi richiesti, ognuno coperto da test e mutazioni (14/14):
- 350 tentativi HTTP complessivi, retry compresi;
- archivio massimo di 100 MB;
- periodo massimo di 47 giorni, nessuna data futura;
- solo gli 8 simboli e 15m/1h/4h;
- costruzione in una cartella temporanea, resa definitiva solo a controlli superati.

**`--plan`:**

| Voce | Valore |
|---|---|
| Periodo | 2026-10-04 → 2026-11-20 00:00 UTC (47 giorni, già trascorsi) |
| File | 24 |
| Richieste stimate | 272 (limite 350) |
| Dimensione stimata | ~11,8 MB (limite 100 MB) |
| Destinazione | `~/brain-unico-lab/data/candles-20261120`, nuova, utente non-root |

**Esecuzione, una sola.** Dopo **24 tentativi HTTP** si è fermata sul controllo di coerenza, con `derivation_differs_from_runtime:15m:BTCUSDT`: le righe ricavate dalle risposte grezze non coincidevano con quelle del runtime. **Nessun archivio scritto**, nessun dato conservato. Resta solo `candles-20261120.ABORTED.json`: `archive_written=false`, `http_attempts=24`. **Non esistono quindi manifest ID né SHA-256 da registrare.**

**Causa probabile:** la derivazione filtrava per finestra della singola richiesta, il runtime per il periodo complessivo. Una fonte che restituisce candele fuori dalla finestra richiesta fa divergere le due regole: il meccanismo è dimostrato con un finto endpoint, ma **non è confermato sui dati reali**.

**Correzione `2c07f7a9`:**
- la derivazione usa la regola del runtime, sia nell'acquisizione sia nella verifica di provenienza;
- il rapporto di interruzione ora riporta gli istanti divergenti e gli esiti dei tentativi HTTP.

**Nessun nuovo download.** Per riprovare serve una nuova autorizzazione; la destinazione già usata è bloccata, quindi servirà un nome nuovo.

## 2. Gate di pubblicazione
`~/brain-unico-lab/tools/gate_publish.sh` pubblica solo se:
- suite V3 con `rc=0`, riepilogo presente, nessun fallito né errore;
- test del builder verdi;
- test Jest del frontend verdi.

**Collaudo:**
- 8 esiti simulati: suite fallita, interrotta, senza riepilogo, errore di collezione, builder fallito o senza riepilogo, frontend fallito;
- una **suite reale** con un test-sonda fallito: bloccata;
- in uso: ha **bloccato `c768a6f4`**, perché il test RC84 sull'inventario delle rotte non conosceva la nuova rotta di lettura. Corretto in `8e03235d` e pubblicato.

## 3. Difetto di duplicazione: classificato e corretto
| | |
|---|---|
| Innesco | riavvio del runner nello stesso slot, dopo un ciclo intero o parziale |
| Effetto | ogni simbolo senza posizione veniva deciso di nuovo con un nuovo istante e nuovi id: chiamate e costi AI raddoppiati, campioni correlati nel training, possibile riapertura nello stesso slot di un simbolo chiuso nel frattempo |
| Non causava | doppie posizioni sullo stesso simbolo, perché i simboli con posizione aperta erano già esclusi |
| Gravità | media: costo e qualità dei dati, nessun superamento dei limiti di rischio |
| Correzione | deduplicazione per slot dal journal anche in modalità `cycle`, quando il chiamante passa lo slot. Il runner cablato passa lo stesso slot che usa per decidere quando girare. Dopo un ciclo parziale si decidono solo i simboli mancanti |
| Prove | difetto documentato senza slot, corretto con slot; ciclo parziale; nessuna doppia apertura né riapertura nello stesso slot in entrambe le modalità |

## 4. Modalità per simbolo: verifiche prima della promozione
| Verifica | Esito |
|---|---|
| Deduplicazione dopo riavvio | sì, anche a metà slot |
| Doppie aperture | nessuna, nemmeno dopo una chiusura nello stesso slot |
| Coerenza slot / istanti | istanti dentro lo slot e non decrescenti; altrimenti nessuna decisione |
| Freschezza delle candele | età del dato 0 contro ≥ 700 s; candela chiusa durante il ciclo vista. **Da misurare sui dati reali** (serve l'acquisizione) |
| ExitService / RiskManager | il writer serializzato del sidecar ricontrolla dopo l'AI con il proprio orologio; traccia sempre prima dell'apertura; uscite e rischio non importano la traccia |
| Persistenza della memoria | deduplicazione e tesi ricostruite dal journal dopo il riavvio |
| Chiamate e costi AI | una chiamata per simbolo per ciclo in entrambe le modalità, zero dopo un riavvio nello stesso slot. Possibile richiesta di candele in più quando una candela chiude durante il ciclo |

Non è attivata sulla VPS: il cablaggio resta `cycle`.

## 5. Dataset Builder: verificato / non verificato / escluso
Ogni riga ha `data_status`:

| Stato | Significato |
|---|---|
| `verified` | candidata al training; **non** è un'autorizzazione |
| `unverified` | manca solo un'attestazione o una provenienza |
| `excluded` | difetto strutturale |

Il riepilogo ha i conteggi per stato e `training_authorized: false`. Lo schema rifiuta uno stato incoerente. Nessuna riga viene cancellata.

## 6. Memoria e apprendimento nell'app SuperBot
Integrati nella schermata esistente **"V3 · 3 bot"** (Overview) della PWA SuperBot, non in una pagina separata:
- **Endpoint `GET /api/v3/brain/memory`:**
  - sessione obbligatoria, sola lettura;
  - collegamenti **validi** secondo la regola canonica, con catena di hash;
  - snapshot mancanti e non validi, NO_TRADE conservate, aperture senza traccia valida;
  - tesi e reingressi in osservazione;
  - avanzamento della raccolta verso le soglie dell'Issue #113, cioè 300 esempi e 20 giorni per lo shadow, 1000 e 45 per valutare una promozione;
  - sempre `training_authorized=false` e `model_active=false`;
  - nessuna feature, numero di rischio o testo del modello.
- **Tre sezioni nuove:**
  - Memoria decisionale, con le ultime decisioni e lo stato della loro traccia;
  - Tesi e reingressi;
  - Apprendimento.
- **Isolamento:** se la memoria non risponde, il resto della schermata resta intatto.
- **Funzionalità esistenti preservate:** posizioni, profitti, trade chiusi, chiusure manuali, stato del Brain, risultati per strategia.
- **Collaudo:** Node 20 installato nella home con checksum verificato e dipendenze dal `yarn.lock`, senza script. Jest **129/129**, build di produzione compilata in una cartella temporanea (`frontend/build` intatta).
- **Difetto trovato dal test e corretto:** un codice `__proto__` faceva cadere il rendering del pannello. Le traduzioni ora usano solo chiavi proprie.

## Prossimi passi
- Nuova autorizzazione per **una** acquisizione delle candele, con destinazione nuova.
- Dashboard: aggiungere lo stato della perdita giornaliera (latch P0) e il riepilogo dei quattro requisiti del dataset, quando esisterà un rapporto del builder.
- Piano della release candidate PAPER integrata.
