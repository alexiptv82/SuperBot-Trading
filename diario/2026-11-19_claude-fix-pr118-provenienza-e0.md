# 19/11/2026 — Claude: fix residui PR #118 + misura E0 (PR #119)

## PR #118 — `claude/brain-unico-training-dataset-20261119` @ `0833c0d6b53949c8f92349bb64271e725e95cdf5` (da `e983d36`)
1. **Simbolo nel legame** (`builder.link_input`): simbolo noto e uguale da entrambe le parti; un input di altro simbolo non si collega MAI, nemmeno con lo stesso `cycle_id` (`symbol_conflict`); input senza simbolo mai collegato (`ambiguous_feature_link`, escluso); ciclo noto diverso escluso (`cycle_conflict`).
2. **Provenienza** (`attestation.py`, `phase0_attestation_v2`): costruita SOLO da una run sigillata `full` con `SNAPSHOT_GO`; ricalcola e lega summary/snapshot_log/manifest/audit (digest manifest e teste di catena ricalcolati, conteggi, run_id = nome directory); `check` ricostruisce dalla run (JSON modificato -> `attestation_stale_or_tampered`). Senza **ancora esterna** `--anchors {run_id: sha256 summary.json}` (mai dalla spec) -> `hash_matched_untrusted`, motivo `provenance_not_anchored`, escluso. v1 rifiutata. Una run finta coerente in ogni campo resta `hash_matched_untrusted` (test dedicato).
- 103 test sintetici PASS (88 + 15), stabili; mutazioni: 25/25 nuove, 8/8 tradotte dal giro precedente, 25/25 precedenti. BUILDER_VERSION 0.3.0. Doc §12.
- Nota pratica: i file `private/` della run sono root 0600 -> la prima esecuzione reale richiede un passaggio di copia autorizzato a parte.

## PR #119 — `claude/brain-unico-profit-guardian-20261119` @ `d6ed73da7a229e051bcd96d7fb3db9abf5f07bb8` (da `cec2b87`)
- `ops/brain-unico/guardian/e0_measure.py` + `test_e0_measure.py`: H1 (trade dopo >= +4R realizzati di sessione vs [-1R,+1R)) e H2 (reingressi 3+ vs primo), effetto fisso di flusso, bootstrap a blocchi di sessione, Holm, minimo 30 trade/10 sessioni, verdetti worse/better/no_evidence/inconclusive; solo fonti attestate; output solo numeri 0600 fuori git. 18 test, 23/23 mutazioni.
- `docs/v3/BRAIN-UNICO-E0-MISURA-STORICI-20261119.md`: percorso con consensi, definizioni pre-registrate, limiti (solo PnL realizzato, tesi proxy, regime), regole di decisione.
- Proposta Guardian §H: decisioni provvisorie utente (R_base 1–1,5% in PAPER, leve fino a 50x dimensionate dal rischio, +400/+500 solo riferimento, eccezioni OFF, osservazione leggera in LOCKED); `screened_signal` vs `full_decision` (shadow LLM budget 0 di default); floor con posizioni simultanee/ordini pendenti/correlazione/gap/liquidazione; rimosse le formule "garantisce/per costruzione".

## Non fatto
Nessun dato reale, root, snapshot, stop, merge, deploy, Action o API. Il Guardian operativo NON e' iniziato. Preso atto della decisione utente (voce 14:45): il prossimo PAPER del Brain unico sara' un collaudo finale integrato con tracciabilita' requisito -> implementazione -> test -> evidenza.
