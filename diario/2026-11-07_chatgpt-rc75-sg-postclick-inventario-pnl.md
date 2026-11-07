# SuperBot-Trading V3 — RC75, audit VPS post-chiusure manuali PAPER

**Data audit:** 2026-11-07T17:03:15Z (18:03 CET) · **Metodo:** workflow GitHub Actions con SSH, `python3 -B`, letture di stato e storico, `systemctl` e `docker inspect` esclusivamente in lettura · **NESSUN ORDINE / DEPLOY / RESTART / RESET / MERGE**.

## Evidenze riproducibili

- [Run RC75 #42394206286](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42394206286): SUCCESS, primo inventario post-click.
- [Run RC75 #42394351334](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42394351334): SUCCESS, riconciliazione chiusure `2026-11-07` in fuso `Europe/Rome` e somma `net` dai record `trade_history.jsonl`.
- Codice audit in `work/v3-rc75-sg-postclick-audit-20261107`, commit `f72340b712f5de67a541d2dea9cf8bbd9373fd6d`, `.github/workflows/v3-rc75-sg-postclick-readonly.yml`. Branch **separato**, nessun merge né modifica VPS.

## Inventario reale della VPS al momento dell'audit

| Portafoglio | Posizioni aperte | Simboli | Chiusure manuali del 7/11 | `net` totale USDT | `fees` totale USDT |
|---|---:|---|---:|---:|---:|
| Falco | **1** | **ARB** | **5** | **+628,9169** | 13,8944 |
| Toro | **1** | **ARB** | **1** | **+154,0444** | 4,8175 |
| **Totale classici** | **2** | ARB su due portafogli indipendenti | **6** | **+782,9613** | 18,7119 |

Falco chiuse manuali del giorno (tutte `closed_by=utente`, `manual_learning=profit_protection_example`):
- NEAR `net=+226,6468`, fees 2,7424
- ATOM `net=+121,6592`, fees 2,5655
- LINK `net=+92,8411`, fees 2,7027
- TIA `net=+114,8315`, fees 2,9293
- SUI `net=+72,9383`, fees 2,9545

Toro chiusa manuale del giorno: LINK `net=+154,0444`, fees 4,8175, `closed_by=utente`, `manual_learning=profit_protection_example`.

Le cifre `net` sono P&L **realizzato nel simulatore PAPER**, al netto delle `fees` dichiarate nel journal; NON includono P&L non realizzato delle due ARB ancora aperte. Non sono denaro reale, né rappresentano equity corrente o risultato atteso futuro. Il confronto con il vecchio inventario (6 Falco + 2 Toro) è coerente con 6 uscite e nessuna nuova apertura, mentre i motori legacy restano fermi.

## Protezioni e blocchi verificati

- Web container `superbot`: running. Flag `TRADING_MODE=paper`, `DESK_MODE=paper`, `V3_CUTOVER_READONLY=1`, `V3_ALLOW_CLASSIC_SINGLE_CLOSE=1`. Flag `V3_ALLOW_BRAIN_SINGLE_CLOSE` **non presente** nella lista di flag pubblicabili, quindi **non dichiarare Brain close attivo**.
- Falco e Toro: servizi `superbot-v3-falco-exit.service` e `superbot-v3-toro-exit.service` ACTIVE, heartbeat `ready=true` fresco (1,9 e 1,8 s), `pause.flag` presente, container legacy `exited`, nessun `close_position.flag` pendente.
- Brain: run preparata con directory e `journal.db` presenti, `pause.flag` presente; nessun heartbeat sidecar exit, nessun `close_request.json` o `close_result.json`. [PR #74](https://github.com/alexiptv82/SuperBot-Trading/pull/74) **solo offline**, NON deployata.
- Backup locale RC69: **2 directory di snapshot** trovate dal glob; ultima indicata `rc69-paper-legacy-20261107T110255Z-142218`. Queste sono precedenti alle chiusure. **Non è ancora stato creato uno snapshot post-close** né provato il suo restore.
- Backup esterno `superbot-extbackup.service`: ultimo `Result=exit-code`; **non certificato/riparato**. `systemctl is-active` e `is-enabled` per servizi non zero sono stati stampati come `UNAVAILABLE` dal wrapper del workflow, non interpretare questo valore come assenza di unità.

## Successivo passo prima della nuova run PAPER 1000/1000/2000

1. Preservare **le due ARB aperte** finché l'utente decide se/come chiuderle da `Classici → Falco/Toro → Chiudi ora`; non usare il pulsante per conto suo.
2. Acquisire **nuovo snapshot locale post-close**, verificare SHA e restore in directory isolata senza sovrascrivere RC69, con autorizzazione specifica per la scrittura dei backup; valutare e ripristinare off-host prima del reset.
3. Verificare sidecar Brain singolo owner/lease/run_id/IPC rigorosi in ambiente sintetico, senza aprire trade o attivare Brain. Eventuale deploy/flag Brain richiede GO specifico; non riavviare i motori.
4. Dopo ulteriore audit e consenso esplicito, archiviare run storiche e creare le **nuove** run separate PAPER: Falco 1.000, Toro 1.000, Brain 2.000, conservando journal e learning. Falco/Toro restano con Claude e SHORT originali, solo miglioramenti LONG/trend.
