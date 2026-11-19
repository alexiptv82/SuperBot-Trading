# Checkpoint Claude Code — 19/11/2026: correzioni dalle revisioni delle PR #117 e #118

Autore: Claude Code (laboratorio, utente non-root). Riferimento: Issue #113; revisioni ChatGPT [PR #117](https://github.com/alexiptv82/SuperBot-Trading/pull/117#issuecomment-7007604011) e [PR #118](https://github.com/alexiptv82/SuperBot-Trading/pull/118#issuecomment-7007605069). **Nessun dato reale letto, nessun comando privilegiato, nessuno stop, snapshot reale, merge o deploy.** I test sono sintetici e non replicati da ChatGPT.

## SHA finali (push fast-forward, nessun force, PR restano draft)

| PR | Branch | SHA | Base |
|---|---|---|---|
| #117 | `claude/brain-unico-fase0-conclusion-20261119` | `6dcdedc36c3aafb4a2bed2a8f7b8edcc74b80482` | branch della PR #116 |
| #118 | `claude/brain-unico-training-dataset-20261119` | `e983d36f7be8d9965ed37283d3d4ca86b658fdab` (fix `8d24609f…`, poi allineamento roadmap) | `main` |

**Nuovo hash del bundle sigillato** (`ops/brain-unico/sealed/phase0_sealed.py` al commit `6dcdedc…`): `4dcaff8b5cb583df20e7386dca2a8c78bdf472260595bf461d4913df4266a7b3`. Sostituisce `358f4793…` e `afcab6f7…`: **nessuno dei bundle precedenti va usato; nessun bundle è stato eseguito.** L'hash va ricalcolato sui byte del commit (`git show <commit>:ops/brain-unico/sealed/phase0_sealed.py | sha256sum`).

## PR #118 — integrità del Training Dataset Builder (schema v2)

- **P0-1** feature del Brain storico: legame causale (stessa epoca, input precedente, stesso `cycle_id` o stesso simbolo); altrimenti nessuna feature e conteggio `ambiguous_feature_link`.
- **P0-2** il flag `verified` della spec è **ignorato**: serve un'attestazione `phase0_attestation_v1` (snapshot completo + audit non FAIL) con SHA-256 uguali a quelli dei file letti; fail-closed.
- **P0-3** `eligible_for_training` / `ineligible_reasons` calcolati una volta e usati da split e sufficienza; il dataset completo resta intatto.
- **P0-4** barriera sul prefisso contiguo fino al primo tocco; `label_complete` (barriera) separato da `horizons_complete`.
- **P0-5** MFE/MAE ricostruiti solo da candele intere, dichiarati `approximate_candles`, non etichette certificate.
- **P1** PnL mancante ≠ 0 (`closed_unknown_pnl`); `label_origin` e flag per i controfattuali; annotazioni manuali per codice; `candles_meta.json` obbligatorio e hash dei file di mercato nel manifest.
- Test: **88** sintetici (54 + 34); **33 su 33** mutazioni rilevate (oltre alle 30 su 30 della versione precedente).

## PR #117 — finalizzazione dell'Arena e audit del rischio

- `status` **eliminato**: `status-services` legge solo systemd (nessun DB, nessun file di dati), esito `SERVICES_OK` o `INCOMPLETE` (exit 1). Le posizioni aperte vengono solo da uno snapshot coerente (`full`).
- `stop-openings` **richiede `--checkpoint-run`**: un `full` recente, `SNAPSHOT_GO`, che copra tutti i provider selezionati, con snapshot/manifest completi, audit non FAIL, catene verificate, audit dei limiti presente e servizi invariati, in una directory fidata. Su NO-GO nulla viene fermato né distrutto; nessuna scorciatoia nel bundle.
- Nessuna promessa sulle uscite entro 24 h: età delle posizioni misurata da **adesso**, `open_overdue`, flag `open_positions_overdue_for_exit`; nessun timeout automatico né chiusura forzata.
- `risk_audit`: `no_breach_proven` e `fully_checked` (sempre falso) con `not_checkable`; dati mancanti in `data_gaps` (mai zero); ripartizione per giorno UTC; politica dichiarata **non verificata** contro la run. Un −40 % aggregato non prova il rispetto del freno giornaliero e resta strategicamente inadatto a un profilo LIVE.
- `--auth-ref` è solo tracciamento, non autorizzazione.
- Test: **76** (bundle) + **90** (Fase 0) + **24** (audit di rischio) + **29** (inventory); **28 su 28** mutazioni rilevate.

## Non fatto / richiede consenso separato

Esecuzione del bundle come root (`status-services`, `full`, `stop-openings`), qualunque stop di runner, snapshot reale, lettura di journal/DB, prima esecuzione reale del builder (servono copie attestate, `candles_meta.json` e lo schema reale del Brain storico), addestramento. Nessun modello è stato addestrato.
