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
| Ultima candela chiusa scaricata (feed) | integrato | **da confermare sull'API reale** con una sonda autorizzata |
| Istante per simbolo | opzione di laboratorio, **non cablata** | decisione del proprietario dopo il collaudo |
| Dataset Builder: quattro requisiti, verificato / non verificato / escluso | integrato | nessun training |
| Laboratorio LLM (#123) | isolato, nessun provider | non fa parte del percorso di trading |
| App: schermata Brain Unico, memoria, storico | integrato | la build va prodotta al rilascio |

## 2. GO/NO-GO prima del deploy (tutti necessari)
1. Zero P0 aperti; Issue #124 chiusa formalmente.
2. Suite V3, builder e Jest verdi sul commit da rilasciare, con il gate di pubblicazione.
3. Sonda del feed (≤ 3 tentativi) che confermi la candela appena chiusa con le nuove finestre.
4. Backup e restore del journal e dei dati Brain **attestati**: oggi l'extbackup non è certificato. Senza questo, NO-GO.
5. Mandato di rischio approvato per la nuova run. Le decisioni sul profilo di rischio v2 restano del proprietario; senza mandato il motore rifiuta ogni apertura.
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
- Vista storica dell'Arena nell'app: da integrare dal ramo dell'Arena senza toccarne il runtime.
- Profilo di rischio v2: decisioni numeriche.
