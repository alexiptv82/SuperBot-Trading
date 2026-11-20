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
| Decisioni duplicate nello stesso slot | 0 | journal |
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

## 7. Backup: stato al 20/11/2026 (prova autorizzata)
- **Run Brain da proteggere:** dalla configurazione di deploy risulta `brain-rc-2000-20261106` in `/opt/superbot-v3-paper-runs/brain-v3-rc20261106/`. Quella cartella è leggibile **solo da root** (`drwx------` già sulla cartella padre): come utente non-root, senza sudo, non è nemmeno elencabile. **Prova di backup non eseguita.** Come da istruzione, nessuna altra cartella operativa è stata tentata.
- Per eseguirla serve una delle due strade, con consenso: (a) l'operatore lancia `python3 -m backend.v3.runner.run_backup --source <cartella run> --dest <nuova> --restore-test <nuova>` come root, in sola lettura sulla sorgente; (b) una lettura delegata (gruppo o ACL in sola lettura per l'utente di laboratorio sulla sola cartella della run).
- **Run Brain ≠ patrimonio storico.** Falco e Toro (`/opt/superbot-desk-data`), il DB dell'app e del pool sono coperti dall'extbackup esistente (age + repository privato `superbot-backups`), ma la sua installazione e il ripristino **non sono certificati**. La run Brain V3 e le tre run dell'Arena (`/opt/superbot-ai-arena-paper`, solo root; l'Arena ha un suo `backup.py`) **non sono coperte** dall'extbackup. La protezione generale **non è completa**.

## 8. Cifratura e copia esterna (proposta, senza nuovi costi)
- **Correzione (21/11):** la cifratura `tar | age` è in streaming, ma la fase precedente di backup crea COPIE IN CHIARO dei database. Le due fasi sono distinte: le copie in chiaro stanno in una cartella di lavoro 0700 e vengono cancellate dopo le verifiche. Procedura amministrativa circoscritta: `ops/brain-unico/backup/PROCEDURA.md`. Cifratura solo verso la chiave PUBBLICA già approvata (`/opt/superbot-extbackup/recipient.txt`); la privata resta sul PC del proprietario.
- Copia fuori dalla VPS: lo stesso repository privato `superbot-backups` tramite la deploy key di root già esistente: nessuna credenziale nuova. Da autorizzare: aggiungere la run Brain V3 (e le run Arena) ai percorsi dell'extbackup, e una prova di ripristino dal file cifrato sul PC.

## 9. Freschezza dei dati (requisito del GO)
- 15m su BTCUSDT confermato sull'API reale (sonda autorizzata, 20/11). 1m (monitor delle uscite), 1h e 4h usano la stessa funzione corretta: verificato con il CandleStore del runtime ed emulazione della selezione per chiusura (test). Conferma reale su 1m/1h/4h: facoltativa, con una sonda autorizzata.
