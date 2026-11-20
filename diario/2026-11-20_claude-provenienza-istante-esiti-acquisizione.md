# 20/11/2026 (2) — Claude: provenienza delle candele, istante per simbolo, esiti LLM, procedura di acquisizione

**Ramo:** `integration/brain-unico-20261119` @ `3f1c5b9f`, prima `5c2edfca`. Solo laboratorio: nessun deploy, servizio, restart, parametro attivo, spesa, download o chiamata a provider.

| Passo | Commit | Suite V3 offline |
|---|---|---|
| Base | `5c2edfca` | 5235 |
| Integrità e provenienza delle candele | `9acd96d7` | 5238 |
| Istante per simbolo (laboratorio) | `1aadf4ec` | 5250 |
| Etichette LLM | `0453433e` | **1 fallito** (vedi Incidente) |
| Correzione | `24b18d08` | 5256 |
| Procedura di acquisizione | `3f1c5b9f` | **5264**, 0 falliti |

Test del Dataset Builder: 153 passati, tra cui 18 nuovi di provenienza. Annullamento: ogni passo è un commit singolo, si annulla con `git revert`.

## 1. Attestazione delle candele: quattro requisiti, non equivalenti
Come segnalato dal proprietario, `candles_meta.json` **dichiara** la fonte ma non la prova. Ora il builder distingue quattro requisiti:

| Requisito | Dove | Verdetto |
|---|---|---|
| Coerenza matematica delle feature | `snapshot_verify` | `feature_consistency` = `verified` / motivo |
| Integrità dei file archiviati | `candle_provenance` | `candle_archive_integrity` = `intact` / motivo |
| Provenienza verificabile delle candele | `candle_provenance` | `candle_provenance` = `attested` / `declared_only` / motivo |
| Attestazione del journal e delle decisioni | `attestation.py` (Fase 0) | `input_not_attested` in eligibility |

**Provenienza `attested`** richiede tutte queste condizioni:
- integrità intatta;
- fonte = endpoint pubblico atteso, lo stesso del runtime;
- ogni file **riderivato dalle risposte grezze conservate** e coincidente, con URL coerenti con simbolo e granularità e solo candele chiuse all'acquisizione;
- SHA-256 del manifest uguale a un'**ancora esterna registrata dall'operatore** (`--candle-anchors`).

Uno snapshot perde `snapshot_unverified` solo con i primi tre requisiti; la riga entra nel training solo con anche il quarto.

**Restrizione anche per le etichette di mercato.** Il solo meta **non basta più**: senza provenienza attestata le righe restano `market_data_unattested`. I test del builder ora costruiscono archivi attestati, come farà la procedura reale.

**Falsificazioni provate.**
- Dati modificati con hash del manifest ricalcolati: l'integrità risulta `intact`, ma la provenienza è `file_not_derived_from_source`.
- Dati e risposte grezze modificati in modo coerente: `anchor_mismatch`.
- Manifest non ancorato: `manifest_unanchored`.
- Fonte o URL diversi: rifiutati.

## 2. Istante decisionale per simbolo (laboratorio)
`run_brain_cycle(instant="per_symbol", slot_start_ms, slot_end_ms)` usa per ogni simbolo il proprio istante: candele, prezzo, decisione, snapshot e tesi. Il predefinito resta `cycle` e `wiring.py` non cambia.

**Confronto sullo stesso scenario** (8 simboli, modello da 45 s, uscita del sidecar a metà ciclo):

| | `cycle` (attuale) | `per_symbol` |
|---|---|---|
| Snapshot validi | **2/8** (gli altri: decisione scritta in ritardo) | **8/8** |
| Età del dato alla chiamata al modello | cresce fino a ≥ 700 s nel test | 0 |
| Nuova candela da 15 m chiusa durante il ciclo | non vista | vista dai simboli successivi |
| Id delle decisioni | uno per simbolo, stesso istante | uno per simbolo, istante proprio |
| Dataset Builder | — | ammette e verifica le feature |
| `thesis_id` | — | catene corrette tra cicli |

**Deduplicazione per slot.** Con un riavvio dentro lo stesso slot non si ridecide (`already_decided_in_slot`). Un istante fuori dallo slot o all'indietro dà `instant_out_of_slot`, senza decisione.

**Constatazione sul codice attuale**, documentata da un test e non corretta perché è il percorso operativo: in modalità `cycle` un riavvio nello stesso slot ridecide tutti i simboli, con 16 decisioni invece di 8, più costo API e campioni duplicati.

**Proposta:** attivare `per_symbol` e la deduplicazione per slot nel cablaggio dopo il collaudo, con decisione del proprietario.

## 3. Anti-reingresso
Resta in `observe`. Per `enforce` servono dati attendibili, i risultati E0 e l'approvazione del proprietario.

## 4. Etichette LLM
- **Controfattuali e osservati separati.** Ogni etichetta dei candidati è `simulated_counterfactual`. I trade PAPER reali del riferimento (`observed`) stanno in una sezione **separata e non confrontabile alla pari**. Se ne riporta solo la distanza media tra simulazione e osservato sullo stesso campione, cioè quanto la simulazione rappresenta la politica d'uscita reale.
- **NO_TRADE giudicate solo in relazione al riferimento.** Gli esiti possibili sono:
  - evitato;
  - mancato;
  - riferimento piatto;
  - entrambi astenuti, che **non** è prova di correttezza;
  - non giudicabile.
- **Incertezza per ogni modello:** deviazione standard, errore standard, intervallo al 95 % approssimato, giorni UTC distinti e campione `insufficient` sotto 30.
- **Confronto appaiato:** con il riferimento, solo sui campioni dove hanno aperto entrambi.
- **Limiti dichiarati in ogni rapporto:**
  - esiti controfattuali;
  - uscita a barriere, non la politica reale;
  - nessun gap né slippage;
  - ordine dentro la candela ignoto;
  - NO_TRADE relative;
  - campioni non indipendenti.

## 5. Procedura di acquisizione delle candele (preparata, NON eseguita)
È in `docs/v3/BRAIN-UNICO-ACQUISIZIONE-CANDELE-20261120.md` e `ops/brain-unico/candles/acquire_candles.py`:
- **Fonte:** endpoint pubblico Bitget `history-candles`, tramite la **stessa funzione del runtime**, con verifica che la derivazione coincida.
- **Simboli:** gli 8 del runner.
- **Periodo:** dalla prima decisione − 37 giorni fino all'ultima decisione + 24 ore.
- **Dimensione:** circa 12 MB e 272 richieste per 47 giorni.
- **Destinazione:** una directory nuova nella home di laboratorio, fuori dal repository.
- **Contenuto:** manifest con hash di ogni file e risposte grezze.
- **Ancora:** registrata dall'operatore.
- **Rete:** nessuna senza `--confirm-network`.

**Serve l'autorizzazione del proprietario** per eseguirla.

## Incidente: regressione pubblicata (commit `0453433e`)
Il commit delle etichette LLM è stato pubblicato con **1 test fallito**: un commento in `outcomes.py` nominava un componente operativo, violando il test di isolamento del laboratorio. La causa è un errore di procedura: il comando pubblicava se `grep` riusciva, non se la suite era verde. Il commit `24b18d08` ha corretto il commento circa 5 minuti dopo, senza riscrivere la storia, con suite 5256 e 0 falliti.

**Rimedio:** da allora la pubblicazione è condizionata a `rc=0` della suite, nessuna riga `FAILED` e test del builder verdi.

## Verifica delle mutazioni ripetuta
Lo script di mutazione poteva riusare il bytecode in cache (`__pycache__`) quando file mutato e ripristinato avevano lo stesso secondo di modifica, e così ha segnalato una falsa "sopravvissuta". Tutte le campagne del 20/11 sono state **rieseguite** con cache disattivata e cancellata, e **confermano** i risultati:

| Campagna | Rilevate |
|---|---|
| Copertura | 16/16 |
| Validatore | 14/14 |
| Tesi | 12/13 (1 equivalente) |
| Provenienza | 15/15 |
| Istante | 10/10 |
| Etichette | 10/10 |

## Prossimi passi
- Dopo l'autorizzazione: acquisizione delle candele, ancora dell'operatore, prima validazione reale degli snapshot.
- Decisione del proprietario su `per_symbol` e sulla deduplicazione per slot.
- Protocollo preregistrato del confronto LLM: campione, `target_r`, orizzonte, costi.
- Dashboard del Brain Unico: copertura valida, verdetti dei quattro requisiti, tesi e reingressi osservati.
