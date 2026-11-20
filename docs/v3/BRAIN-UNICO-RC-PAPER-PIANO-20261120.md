# Brain Unico: piano della release candidate PAPER (bozza, nessun deploy)

**Stato:** preparazione. Ogni passo operativo richiede il consenso del proprietario: deploy, servizi VPS, mandato e parametri attivi, ancore, accessi alla Fase 0. Base: `integration/brain-unico-20261119` @ `095a0432`, cioè suite V3 5310, builder 157, Jest 137, 0 falliti.

## 1. Contenuto della RC
| Area | Stato nel ramo | Note |
|---|---|---|
| Daily loss P0 #124 (latch persistente, ricostruzione dopo riavvio) | integrato | scenario 10:00/10:01/10:02 coperto |
| Prezzi mancanti fail-closed (#121) | integrato | |
| Traccia causale di ogni decisione (snapshot v2, NO_TRADE comprese) | integrato, cablato `required` | nessuna apertura senza traccia |
| Copertura valida (regola canonica = Dataset Builder) | integrato | |
| Deduplicazione per slot dopo un riavvio | integrato, cablato | difetto di duplicazione corretto |
| `thesis_id` e anti-reingresso | integrato, **solo `observe`** | blocco solo dopo E0 e approvazione |
| Ultima candela chiusa scaricata (feed) | integrato | confermato sull'API reale il 20/11 |
| Istante per simbolo | opzione di laboratorio, **non cablata** | decisione del proprietario dopo il collaudo |
| Dataset Builder: quattro requisiti, verificato / non verificato / escluso | integrato | nessun training |
| Laboratorio LLM (#123) | isolato, nessun provider | non fa parte del percorso di trading |
| App: schermata Brain Unico, memoria, storico | integrato | la build va prodotta al rilascio |

## 2. GO/NO-GO prima del deploy (tutti necessari)
1. Zero P0 aperti; Issue #124 chiusa formalmente.
2. Suite V3, builder e Jest verdi sul commit da rilasciare, con il gate di pubblicazione.
3. ~~Sonda del feed~~ **fatta il 20/11** (2 tentativi): ultima candela chiusa presente, pagine contigue.
4. Backup e restore del journal e dei dati Brain **attestati**. Strumento pronto: `backend/v3/runner/run_backup.py` (backup a caldo in sola lettura, catena verificata, manifest, prova di ripristino in cartella nuova). Da eseguire sulla cartella reale con consenso, più cifratura e copia fuori dalla VPS. Senza questo, NO-GO.
5. **Profilo di rischio definitivo approvato dal proprietario.** Le soglie storiche WARN 35 % / HALT 50 % e i valori di `runner_config_brain2000_paper.json` NON sono automaticamente quelli del Brain Unico (studio v2 in attesa di decisione). Poi il mandato di rischio approvato per la nuova run. Le decisioni sul profilo di rischio v2 restano del proprietario; senza mandato il motore rifiuta ogni apertura.
6. Exit service sidecar sano e indipendente, verificato in pre-collaudo.
7. Piano di rollback provato: commit precedente e build web precedente conservati.

## 3. Deploy (solo con consenso, descrizione)
- **Backend:** runner in modalità sidecar con `trace="required"`, `ReentryPolicy(observe)` e deduplicazione per slot; nuova run id, senza riusare né cancellare journal storici. Falco, Toro, Arena e Brain storico restano intatti.
- **Web:** build di produzione dal commit della RC, copiata con lo script di cutover esistente. Il service worker carica le pagine prima dalla rete: alla prima apertura dopo il deploy l'app mostra la schermata Brain Unico **senza reinstallazione**, perché il manifest non cambia.
- **Nessun cambio** a `DESK_MODE` (resta `paper`), alle soglie 35 %/50 % e al pavimento 450.

## 4. Collaudo PAPER (proposta: 14 giorni)
| Misura | Atteso | Fonte |
|---|---|---|
| Aperture senza traccia valida | 0 | `/api/v3/brain/memory` |
| Copertura valida delle decisioni | ≥ 95 % (gli snapshot in ritardo sono misurati, non nascosti) | memoria |
| Decisioni duplicate nello stesso slot | 0 | memoria (`duplicate_slot_decisions`, slot = `cycle_minutes` del runner; senza configurazione: "non verificabile", mai 0) |
| Catena di hash del journal | integra | memoria (`chain_ok`) |
| Exit service / heartbeat | sempre sano; nessuna uscita persa | heartbeat |
| Daily loss | latch persistente; nessuna apertura dopo HALT | journal / heartbeat |
| Reingressi "che sarebbero stati bloccati" | solo misurati | memoria (tesi) |
| Spesa AI | entro il tetto giornaliero | stato Brain |

Al termine: rapporto con i numeri, nessuna promozione automatica. L'addestramento resta subordinato ai quattro requisiti del dataset e alle soglie dell'Issue #113 (300 esempi e 20 giorni per lo shadow).

## 5. Rollback
Si ripristina il commit precedente del runner e la build web precedente. Il journal è append-only: nessun dato si perde, e la nuova run resta come storico.

## 6. Aperto, con decisione del proprietario
- Sonda del feed e ancora dell'archivio delle candele (`candles-20261120T064955Z-95a00e9b`).
- Istante per simbolo: dopo il collaudo, e con la freschezza misurata sui dati reali.
- Anti-reingresso `enforce`: dopo E0 e approvazione.
- Vista storica dell'Arena: integrata in sola lettura (`/arena`, opt-in); la chiusura dell'Arena resta nel suo ramo.
- Profilo di rischio v2: decisioni numeriche.

## 7. Backup: stato al 21/11/2026
- **Prove reali sulla VPS**, eseguite dal proprietario come root, senza trasferimenti, con il branch `claude/extbackup-storici-20261121`:
  - backup cifrato creato;
  - dopo il ripristino, catena, numero di eventi e testa verificati per i journal obbligatori: Brain V3 1058, DeepSeek 1260, Qwen 1281, MiniMax 1306;
  - integrità tecnica verificata.
- **Esiti separati** (commit `f60b90d6`): **0** = certificato; **1** = difetto tecnico, che è NO-GO; **3** = integro ma **non certificato semanticamente**. L'esito 3 conserva l'archivio, ma non è un successo.
- **Falco e Toro:** decisione del proprietario del 21/11, vedi la sezione 10.
- **Aperto:**
  - ~~archivio di 117 MB oltre il limite di GitHub~~: risolto nel branch `claude/extbackup-storici-20261121` @ `75a714be`. Ci sono due archivi separati, `indispensabili` (database + Brain V3 + Arena, solo esito 0) e `storici` (Falco/Toro e altri, esito 0 o 3), con file cifrati divisi in parti da 90 MiB, verificate una per una, e retention per componente. 74 test da non-root; prova reale da autorizzare;
  - installazione dell'extbackup aggiornato in produzione, con consenso;
  - ripristino dal file cifrato sul PC del proprietario.

## 8. Cifratura e copia esterna (proposta, senza nuovi costi)
- **Correzione (21/11):** la cifratura `tar | age` è in streaming, ma la fase precedente di backup crea COPIE IN CHIARO dei database. Le due fasi sono distinte: le copie in chiaro stanno in una cartella di lavoro 0700 e vengono cancellate dopo le verifiche. Procedura amministrativa circoscritta: `ops/brain-unico/backup/PROCEDURA.md`. Cifratura solo verso la chiave PUBBLICA già approvata (`/opt/superbot-extbackup/recipient.txt`); la privata resta sul PC del proprietario.
- Copia fuori dalla VPS: lo stesso repository privato `superbot-backups` tramite la deploy key di root già esistente: nessuna credenziale nuova. Da autorizzare: aggiungere la run Brain V3 (e le run Arena) ai percorsi dell'extbackup, e una prova di ripristino dal file cifrato sul PC.

## 9. Freschezza dei dati (requisito del GO)
- 15m su BTCUSDT confermato sull'API reale (sonda autorizzata, 20/11). 1m (monitor delle uscite), 1h e 4h usano la stessa funzione corretta: verificato con il CandleStore del runtime ed emulazione della selezione per chiusura (test). Conferma reale su 1m/1h/4h: facoltativa, con una sonda autorizzata.

## 10. Componenti indispensabili e storici (decisione del proprietario, 21/11/2026)
| Classe | Componenti | Backup | Training |
|---|---|---|---|
| **Indispensabili per Brain Unico** | run Brain V3 attiva, 3 run Arena (journal V3), DB dell'app e del pool | obbligatori; integrità tecnica e catene V3 rigorose; un difetto è NO-GO | solo con i quattro requisiti del Dataset Builder |
| **Storici classici** | Falco (`hawk`), Toro (`bull`) | conservati integralmente, **non certificati semanticamente** (esito 3): contabilità e storico di Toro non riconciliati con lo stato | **esclusi**: `semantic_not_certified` in `eligibility.py`; le righe restano nel dataset |
| **Altri storici** | Brain storico (`desk-data/brain`), Brain libero, Brain adattivo, `ai-data`, run V3 preparate | conservati; non bloccano i componenti indipendenti | solo con attestazione |

**Anomalie registrate** di Falco e Toro, dalla prova del 20/11. Sono importi PAPER, non saldi reali:
- **Falco:** cassa + salvadanaio superano capitale + risultati di 21,13 USDT.
- **Toro:** stessa differenza, di 39,08 USDT.
- **Toro:** 25 trade nello stato, 55 nello storico della run, di cui 30 solo nello storico.

Il motore toglie dalla cassa al massimo margine + commissione d'apertura (`engine.py`). L'ipotesi è compatibile con il segno delle differenze, ma non è verificata. **Nessuna ulteriore indagine** senza una nuova richiesta del proprietario. Per Falco e Toro i dati originali non si modificano.
