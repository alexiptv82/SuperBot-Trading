# 20/11/2026 — Claude: copertura affidabile, validazione indipendente, thesis_id, etichette degli esiti

**Ramo:** `integration/brain-unico-20261119` @ `5c2edfcaa4d64a50f0a1496515ec64bb9d8caf87` (prima `a5a92040`). Solo laboratorio: nessun deploy, servizio, restart, parametro attivo, spesa o chiamata a provider.

| Passo | Commit | Suite V3 offline |
|---|---|---|
| Base | `a5a92040` | 5147 |
| Copertura, tempi, prestazioni | `14f42c40` | 5184 |
| Validazione indipendente | `d63e31a8` | 5205 |
| `thesis_id` e anti-reingresso | `1193ffaa` | 5224 |
| Etichette degli esiti per il laboratorio | `5c2edfca` | **5235**, 0 falliti |

I test del Dataset Builder (134) passano dopo ogni passo. Ogni passo è un commit singolo: si annulla con `git revert`.

## 1. Integrità della copertura (verifica 1 del proprietario)
**Problema trovato, più grave di quanto segnalato.** Il controllo di ritardo dell'adattatore guardava solo gli eventi scritti *dopo* la decisione; il Dataset Builder guarda anche quelli scritti *prima*. Con un ciclo di 8 simboli e un modello lento, in modalità sidecar le aperture e le uscite portano l'ora reale: le decisioni dei simboli successivi risultano scritte oltre la finestra. Il builder rifiutava snapshot che l'adattatore accettava, e una copertura per id avrebbe riportato il 100 %.

**Correzione:**
- **Regola canonica unica.** `assess_link` (in `decision_snapshot_v2.py`) controlla:
  - catena di hash;
  - hash, istante, simbolo, azione e stato della decisione;
  - ordine decisione < snapshot < apertura;
  - ritardo della decisione o dello snapshot;
  - formato dei valori;
  - auto-attestazione vietata.

  È la stessa regola del builder: 6 scenari incrociati danno lo stesso verdetto.
- **`trace_coverage` conta solo i collegamenti validi.** Elenca gli snapshot mancanti e quelli invalidi con il motivo, e le aperture prive di un collegamento *valido*. Con la catena di hash rotta, nessun collegamento è valido.
- **Il ritardo non si rifiuta più in scrittura.** Lo snapshot viene scritto con esito `recorded_decision_written_late` o `recorded_snapshot_written_late` e non conta come valido. Rifiutarlo avrebbe trasformato un fatto di qualità in un record mancante e bloccato aperture.

## 2. Istanti e provenienza (verifica 2)
Ora gli istanti restano separati:

| Istante | Campo | Natura |
|---|---|---|
| Riferimento della decisione | `decision_ts_ms` | istante del giro |
| Riferimento dei dati | `feature_asof_ms` | chiusura dell'ultima candela usata |
| Taglio dei dati | `snapshot_captured_at_ms` | dati ammessi fino a questo istante |
| Cattura | `capture_wall_ms` | ora reale, dichiarata |
| Scrittura | ordine nel journal | **unica prova verificabile**; `write_wall_ms` solo dichiarata |

**Le feature si catturano prima della chiamata al modello** (`capture_phase: pre_model`), dalle stesse candele che il modello riceve; un test lo verifica con l'orologio.

Nuovi campi dello snapshot:
- `inputs_digest`: sha256 delle candele usate;
- `inputs_window`: la finestra esatta, cioè prima candela e numero di candele per timeframe;
- `feature_set`: la versione delle feature, tolta dalle feature stesse.

**Prestazioni.** Prima la traccia rileggeva l'intero journal tre volte per decisione, il motore una volta.

| Dimensione del journal | Una lettura completa |
|---|---|
| 10 000 eventi | 0,14 s |
| 60 000 eventi | 1,0 s |
| 200 000 eventi | 4,5 s |

Ora motore, adattatore e traccia usano solo letture per id o filtrate in SQL: `get`, `list_run_after`, `last_seq`, `first_seq_stamped_after`, `list_run_kinds_since`. Un ciclo di 8 simboli su un journal di 60 000 eventi è passato da **28,7 s a 1,3 s**; senza traccia, da 7,7 s a 1,1 s. Un test impedisce di reintrodurre letture complete.

## 3. Validazione indipendente delle feature
`ops/brain-unico/training/snapshot_verify.py` è codice separato, senza import dal runtime e senza rete. Parte da **copie attestate** delle candele, una per timeframe con `candles_meta.json`, lette con valori decimali esatti. Verifica che:
- la finestra sia completa e contigua;
- non ci siano doppioni divergenti;
- le candele siano chiuse entro il taglio dei dati;
- il **digest coincida**;
- le feature ricalcolate con una **implementazione propria** coincidano (tolleranza 1e-9), senza feature mancanti né sconosciute;
- l'istante dei dati (asof) coincida.

Solo l'esito `verified` toglie `snapshot_unverified` nel builder (`--decision-candles DIR`). Restano comunque esclusi dal training:
- **i numeri di rischio del runtime**, perché non verificati;
- **la riga intera**, finché il journal non è attestato dalla Fase 0.

È aggiunta la sorgente `brain_unico`. 21 test end-to-end, dal ciclo reale al builder, coprono ogni manomissione: candela cambiata, mancante o duplicata, meta assente, feature alterata, tolta, aggiunta o non calcolabile, asof spostato, taglio anticipato, digest falso, finestra spostata.

## 4. `thesis_id` e anti-reingresso
- **Definizione della tesi** (`backend/v3/runner/thesis.py`): stesso simbolo e lato, ingresso entro 12 h dal precedente, nessun ingresso di lato opposto in mezzo. È la stessa di E0: un test incrociato confronta 80 ingressi casuali con `e0_measure.annotate`.
- **Identificativo:** `thesis_id` deriva dall'id della decisione del primo ingresso. I tempi sono quelli delle decisioni, non l'ora reale dell'apertura.
- **Causalità:** l'esito precedente viene solo da chiusure anteriori alla decisione.
- **Lettura:** una sola query SQL per ciclo, all'indietro di 30 giorni; se la catena arriva al bordo, è segnalata come `truncated`.
- **Registrazione:** `thesis_id` e `reentry_index` finiscono nello snapshot di ogni OPEN approvata.
- **Anti-reingresso cablato in modalità `observe`:** registra nello snapshot che cosa *bloccherebbe*, senza bloccare. La regola provvisoria è indice > 2, cioè dal terzo reingresso, come l'ipotesi H2 di E0. La regola dell'attesa dopo una perdita è spenta.
- **Blocco reale (`enforce`):** implementato e testato, **non attivo**. Le soglie sono parametri di trading: servono la misura E0 sugli storici certificati e una decisione del proprietario.

## 5. Etichette degli esiti per il laboratorio LLM
`backend/v3/llm_cost_lab/outcomes.py` applica le stesse regole a ogni modello, fissate prima e senza valori predefiniti:
- l'ingresso è il prezzo di mercato all'istante della decisione; l'entry dichiarato dal modello non conta;
- lo stop è quello del modello; se è dal lato sbagliato, la proposta non è eseguibile;
- l'obiettivo è `target_r` volte R, con orizzonte, costi e regola per la candela ambigua stabiliti in anticipo;
- l'etichettatura usa `learning/opportunity`, cioè solo candele successive alla decisione.

`score` restituisce per ogni modello:
- l'EV netto in R;
- vittorie e perdite;
- gli ingressi sfavorevoli evitati e le occasioni mancate dalle NO_TRADE, rispetto al riferimento sullo stesso campione.

L'accordo con il riferimento non è mai un criterio, e sotto 30 etichette il risultato porta un avviso.

## Mutazioni
| Componente | Rilevate |
|---|---|
| Copertura e provenienza | 16/16 |
| Validatore | 14/14 |
| Tesi | 12/13; la superstite è equivalente, perché il lato nella chiave è ridondante con l'id della decisione |
| Etichette | 10/10 |

Ho tolto dal ciclo un aggiornamento della tesi che non poteva mai avere effetto: è codice morto, emerso dalle mutazioni.

## Limiti e prossimi passi
- **Ritardo con cicli lunghi:** in sidecar molti snapshot dei simboli successivi risulteranno `recorded_*_late`, quindi non validi per il training, finché le decisioni portano l'istante d'inizio del giro. Va misurato in collaudo. Proposta per dopo: dare a ogni decisione il proprio istante di riferimento, cioè barre e prezzo al momento della chiamata. Cambia la freschezza degli input del modello: da decidere.
- **Validazione delle feature:** servono copie attestate delle candele 15m/1h/4h. Scaricarle è un'attività operativa, con autorizzazione.
- **Numeri di rischio dello snapshot:** sono verificabili ricostruendoli dal journal; per ora restano esclusi.
- **Confronto LLM:** con le etichette resta da fissare il protocollo, cioè campione, `target_r`, orizzonte e costi, prima di qualunque chiamata reale (con autorizzazione).
