# Brain Unico — Training Dataset Builder (progetto e implementazione offline)

Stato: **sviluppo offline, collaudato solo su dati sintetici**. Nessun dato reale è stato letto, nessun addestramento è stato eseguito, nessun modello è stato prodotto. Riferimenti: Issue #113 (decisione del 19/11/2026, 10:20: «il nuovo Brain impara da dati verificabili, non da riassunti LLM»).

## 1. Obiettivo

Trasformare gli storici di **Falco, Toro, Brain storico, DeepSeek, Qwen e MiniMax** in esempi per un modello quantitativo, **senza perdere**: le perdite, i `NO_TRADE`, i rifiuti, le chiusure manuali, le posizioni ancora aperte, la fonte e il run. Lo scoreboard LLM e `lessons.md` non sono addestramento; questo è il primo passo che lo rende possibile.

Il builder legge **solo copie ferme** (Fase 0), non scrive negli input, non usa la rete e non produce mai testo libero: solo numeri e codici brevi.

## 2. Che cosa esiste oggi, fonte per fonte

Questa matrice è il risultato più importante dell'analisi: **le fonti non sono equivalenti** e i metodi di apprendimento devono saperlo.

| Dato | Falco / Toro (classici) | Brain storico | Brain V3 e Arena (journal V3) |
|---|---|---|---|
| Decisioni eseguite (apertura, SL/TP, leva) | sì (`open`) | sì (`open`) | sì (`paper_open`, solo stop) |
| Esito reale (PnL netto, motivo, durata) | sì (`close`, anche parziali) | sì (`trade_closed` + `partial_trade`) | sì (`paper_close`) |
| **Feature al momento della decisione** | **sì, registrate** (`features`) | forse (`ai_input`: formato da verificare) | **no** (il `brain_decision` non le salva) |
| **MFE / MAE** | **sì, registrati** (`mfe_r`, `mae_r`) | non noto | **no** |
| **Funding pagato** | **sì** | non noto | **no** |
| `NO_TRADE` / hold | **no** (solo conteggio chiamate) | forse (`ai_decision`) | **sì** (`brain_decision` NO_TRADE) |
| Aperture rifiutate (con motivo) | sì (`candidate`) | sì (`execution_rejected`) | solo come decisione OPEN non approvata (senza lato né prezzo) |
| Chiusure manuali con motivazione | non tracciate come tali | `operator_*` | annotazioni dell'Arena (file a parte: **non ancora letto dal builder**) |
| Collegamento decisione → posizione | no | no | sì (`decision_event_id`, con stato `linked/unlinked/dangling`) |

Conseguenza: per **V3/Arena le feature e MFE/MAE vanno ricostruite** da candele chiuse e sono marcate `reconstructed_from_candles`, mai spacciate per registrate. I classici hanno invece i valori *realmente visti* dal sistema al momento della decisione (`logged_at_decision`). Un modello deve poter distinguere le due origini: la colonna `feature_source` serve a questo.

## 3. Modello dati (`schema.py`, versione 1)

Una riga = una decisione. Campi principali:

- **Identità e provenienza**: `example_id` (hash deterministico), `source_system` (`falco`, `toro`, `brain_storico`, `arena_deepseek`, `arena_qwen`, `arena_minimax`), `source_run`, `source_kind`, `provenance` (input, versione builder, set di feature, `link_status`, `duplicate_of`, `inputs_verified`, `schema_unverified`).
- **Decisione**: `record_kind` (`executed`, `candidate_rejected`, `no_trade`), `action` (`LONG`, `SHORT`, `NO_TRADE`, `OPEN_REJECTED`), `decision_ts_ms`, `decision_day`, `symbol`.
- **Feature**: `features` + `feature_source` (`logged_at_decision` | `reconstructed_from_candles` | `none`) + `feature_asof_ms`.
- **Proposta**: entry, stop, target, leva, confidenza (se nota), `decider`, strategia/regime (se noti), codice del motivo di rifiuto.
- **Esito**: `status` (`closed` | `open_censored` | `not_executed`), PnL netto, `net_r`, costi, funding (+ `funding_known`), motivo di uscita, **`is_manual`**, durata, parziali, MFE/MAE (+ `mfe_mae_source`).
- **Etichette**: rendimenti forward a 1h/4h/24h e barriera stop/target/timeout per **ciascun lato** quando non c'è una direzione (NO_TRADE e rifiuti), con `label_complete`.

Regole verificate dai test: `is_synthetic` deve essere sempre `false`; nessun NaN; coerenza lato/azione, eseguito/esito, feature/origine; nessun testo libero (lista chiusa di chiavi vietate, stringhe ≤ 24 caratteri sicure).

## 4. Causalità e anti-leakage

1. Le feature leggono solo candele con `open + 15 min ≤ decisione` (**chiuse**). Un test altera tutto ciò che è successivo e verifica che le feature non cambino; un altro altera il passato e verifica che cambino.
2. L'ingresso delle etichette è l'**apertura della prima candela con open ≥ decisione**: la candela che contiene la decisione è esclusa.
3. **Nessuna interpolazione**: se manca anche una sola candela, l'etichetta è `complete=false` e non contiene numeri; le feature sono `None` (non inventate).
4. Stop e target nella stessa candela: vince lo **stop** (scelta prudente), con `ambiguous=true`.
5. Split **solo cronologici**: embargo e *purging* in base alla fine dell'informazione futura (`max(orizzonte, chiusura reale)`); `assert_no_leakage` lo verifica; 25 dataset casuali di test.

## 5. Deduplicazione e provenienza

- `trade_history.jsonl` e `learning_log.jsonl` contengono le stesse chiusure: la riga dello storico è saltata se la chiusura è già nel registro (`history_duplicates_skipped`), senza sommarla due volte; le chiusure parziali dello stesso `id` sono aggregate (il `net_r` è additivo).
- Lo stesso trade in due input (per esempio Falco in `desk-data` e nel journal V3) è **marcato** `duplicate_of`, **non cancellato**; i duplicati restano fuori da split e sufficienza.
- Gli ID del Brain storico ripartono ad ogni `experiment_reframed`: l'epoca fa parte della chiave.
- Ogni input è identificato per `input_id`; il manifest riporta lo SHA256 dei file letti, **mai i percorsi**.

## 6. Sufficienza (decisione dell'utente, 19/11/2026)

Primo modello **shadow solo offline**: ≥ 300 esempi etichettati e verificati e ≥ 20 giorni. Per **considerare** la promozione: ≥ 1000 esempi, ≥ 45 giorni, più OOS cronologico con embargo, confronto con baseline, calibrazione, EV netto, drawdown, sufficienza delle classi e approvazione esplicita (queste ultime solo elencate: il builder non le valuta). *Etichettato e verificato* = input verificato (audit di catena o riconciliazione), feature presenti, etichetta completa, non duplicato, non sintetico, **non chiusura manuale**. Sono soglie minime, **non** garanzie statistiche né prova di profitto.

## 7. Cosa NON fa

Non addestra, non seleziona modelli, non scarica candele (si preparano a parte da una fonte pubblica e si passano in una directory), non legge le annotazioni manuali dell'Arena (da aggiungere con il lettore dedicato), non verifica la catena degli eventi (lo fa l'audit di Fase 0), non riscrive né "pulisce" gli storici. Lo schema del Brain storico è letto in modo **tollerante e non verificato**: ogni chiave non attesa viene riportata nel manifest privato (`keys_seen_unverified_schemas`) e le righe sono marcate `schema_unverified`.

## 8. Requisiti per il futuro Brain Unico (log in avanti, schema v2)

Per non dover più ricostruire, il Brain Unico deve **scrivere al momento della decisione**, nel journal append-only: hash e riferimento dello snapshot delle feature (point-in-time), versioni di prompt, modello e politica, `thesis_id`, lato e prezzi **anche per i rifiuti e i NO_TRADE**, codice del motivo (non testo), motivo di uscita, funding pagato, slippage, MFE/MAE alla chiusura e, per le chiusure manuali, un codice di motivazione. Questo è il difetto strutturale di V3 emerso dall'analisi: senza questi campi il modello resta dipendente da una ricostruzione.

## 9. Piano

1. **Fatto**: schema, candele, feature, etichette, lettori, split, sufficienza, builder, 54 test sintetici. Verifica per mutazione: reintroducendo in una copia di scratch ciascuno di 30 difetti (look-ahead, interpolazione, ingresso sulla candela contenente, perdite o NO_TRADE filtrati, duplicati cancellati invece di marcati, chiusure manuali non marcate, testo libero, NaN, sintetici accettati, leakage degli split, soglie abbassate, permessi o repo dell'output, sidecar SQLite, ordine non deterministico, epoche del Brain storico) almeno un test fallisce: **30 su 30 rilevati**.
2. Verificare lo schema reale del Brain storico sulla **prima copia** disponibile (nessuna ipotesi prima).
3. Preparare la cache di candele chiuse da fonte pubblica (strumento separato, rete solo lì).
4. Lettore delle annotazioni manuali dell'Arena e collegamento ai `paper_close` `manual`.
5. Prima esecuzione reale **solo su copie verificate** (dopo lo snapshot di Fase 0, con consenso).
6. Baseline e modello shadow (es. LightGBM) **solo se `sufficiency.status != insufficient`**; registry, confronto con baseline, rollback e approvazione prima di ogni promozione.

## 10. Uso e verifica

```
python3 ops/brain-unico/training/builder.py --spec spec.json --out /percorso/nuovo --candles /percorso/candele
python3 ops/brain-unico/training/test_training.py      # 54 test sintetici
```

`spec.json`: `{"inputs": [{"id": "...", "source_system": "falco|toro|brain_storico|arena_deepseek|arena_qwen|arena_minimax", "kind": "classic|v3|brain_free", "path": "<COPIA>", "verified": false}]}`. L'output è una directory nuova (0700) fuori da qualunque repository: `examples.jsonl` (0600), `manifest.json` (0600, privato), `public_summary.json` (solo numeri). **Non mettere mai gli esempi o il manifest nel repository.**
