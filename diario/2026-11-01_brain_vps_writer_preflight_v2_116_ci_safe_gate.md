# 2026-11-01 — Brain VPS runtime preflight v2, 116 CI pass — HOLD SHADOW DEPLOY

**Mandato utente:** `ok procedi` dopo test live con motore LONG V6.1.1 autentico. Obiettivo ora identificare la fonte Brain effettivamente attiva sul VPS Singapore e preparare release-gate shadow. L'utente non autorizza merge, deploy, trading, modifiche ai wallet, agli SHORT o alla protezione 450 USDT.

## Codice e audit preparati — nessuna connessione VPS

- Su PR #26 Draft `work/long-shadow-app-observation-20261101`, diagnostic `backend/long_shadow_brain_docker_metadata_preflight.py` aggiornato a schema `v2`.
- Trovata lacuna P1 nel primo diagnostico: scansione solo dei container con nomi `brain`/`superbot`, falsa negazione per processi con nomi diversi. Ora si analizzano **tutti i container Docker in esecuzione**, con massimo 100; solo `docker ps --format` e `docker inspect --format '{{json .Mounts}}'` (no exec/env/log/SSH/API privata). Confronto sia Source sia Destination dei mount, compresi parent/child delle due directory Brain (Free e Pilot). Qualsiasi writer estraneo, app web RW, montaggio largo o più writer => `AMBIGUOUS_OR_UNEXPECTED_WRITER_MOUNT`. Anche un candidato esatto produce `ONE_EXACT_WRITABLE_MOUNT_CANDIDATE_NOT_PROVEN_OWNER`, **mai** `active_owner_confirmed=true`. Potevano esistere servizi host senza Docker: non vengono certificati.
- Diagnostica restituisce solo conteggi aggregati e stato, nessun nome/path/simbolo/saldo/posizione o segreto. Nessuna esecuzione sulla VPS effettuata.
- Test `backend/tests/test_long_shadow_brain_docker_metadata_preflight.py` aggiornati da 10 a **16**. Verificano writer stranieri, bind montati in un altro percorso ma con Source reale, parent-mounted, app web erroneamente RW, dati privati non emessi, gestione errori e nessuna chiamata Docker che scrive.

## Test GitHub CI verificati

- Commit codice `e3f9114be9a13a337ac9000b2b64d65cef570ede`: workflow `Long Shadow Read-Only Contract` run **41348194083** SUCCESS, backend **116/116 PASS** su 12 suite (`[17,4,4,10,6,12,9,19,10,4,16,5]`), static `READ_ONLY_STATIC_GATES_PASS`, frontend React test e build SUCCESS.
- Su stesso commit: REST reale Bitget smoke **41348194033** SUCCESS; pipeline pubblica E2E con wallet sintetici **41348194047** SUCCESS; pipeline REAL V6.1.1 frozen pubblico live con wallet sintetici **41348194103** SUCCESS. Rollover 1m **41348194078** era ancora `in_progress` al momento di annotazione; controllare se necessario e non dare esito falso.

## Sorgente Brain ancora non confermata

- Verificato dal codice deploy in main `.github/workflows/brain-free-app-deploy.yml`: app web `superbot` monta **sia** `/opt/superbot-brain-free` **sia** `/opt/superbot-desk-data/brain` come sola lettura. Questo prova solo che la web app può leggerli, NON quale processo Brain gestisca trading e quale wallet sia autorevole.
- **Nessun tool SSH/VPS** disponibile nella presente chat: non è possibile verificare realmente i container o file della VPS da GitHub. L'operatore può fornire in Termius un inventario innocuo (senza segreti) eseguendo il comando seguente e condividendo schermata:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

- Questo è il solo comando iniziale; non tocca nulla, non legge segreti/posizioni e NON attesta ownership. Dopo l'inventario esaminare metadati mount RO/RW con diagnosi v2 e solo successivamente verificare il processo owner. Evitare comandi generici `docker inspect` senza filtri, `printenv`, credenziali, log/DB, reboot.

## Gate NON superati

`BRAIN_REAL_VPS_WRITER=UNVERIFIED`; `REAL_WALLETS_NOT_ACCESSED`; `LONG_MTF_H24=NOT_PROVEN`; `ECONOMIC_EDGE=INSUFFICIENT`; `PAPER_ELIGIBLE=NO`; `SHADOW_DEPLOY_NOT_AUTHORIZED`; `MAIN_MERGE=NO`; `ORDERS=0`. PR #26 Draft in sviluppo, PR #27 Draft per chiusura manuale un solo trade per ID separata, non operativa. Brain libero bocciato per prossimo rilascio; rules-controlled redesign solo dopo LONG. Nessun lavoro in produzione.