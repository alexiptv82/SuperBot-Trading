# SuperBot LONG — autentico V6.1.1 su Bitget live pubblico + preflight Brain (2026-11-01)

## Livello di prova raggiunto

**Test Live GitHub Actions**: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41347328579, SUCCESS. In QUESTO run non è stato impiegato uno stub: `backend/research_frozen_long_v611_engine.zlib.b64` ricostruisce il sorgente originale invariato del LONG V6.1.1 sotto un tempdir, verificato via SHA256 `36f8c62be8d205d909ae16f5652209710de56ae710fedb6b75a601b96486fe72`; prima dell'import il loader frozen `long_shadow_offline_probe.frozen_engine()` ripete la verifica. Archivio originale recuperato da `SuperBot_LONG_MTF_15m_Audit_Shadow_Ready_01.zip` fornito dall'utente. La copia compressa è SOLO un fixture di ricerca: i byte ricostruiti sono identici, non cambia la strategia.

Workflow `.github/workflows/long-shadow-original-live-e2e.yml`; modulo `backend/long_shadow_live_authentic_v611_synthetic_e2e.py`, materiale `backend/research_materialize_frozen_long_v611.py`, 5 test sui byte/immutevolezza in `backend/tests/test_long_shadow_original_frozen_fixture.py`.

**Risultato letto dai log REALI** del run 41347328579: `{status: PASS, engine: AUTHENTIC_FROZEN_V611_SHA256_PINNED, rest_closed_series: 8, books1_ack_count: 2, books1_observed_frames: 5, consumer_count: 3, evaluations: 12, decisions: {NO_TRADE: 12}, reasons: {SETUP_ABSENT: 12}, orders_created: 0, wallets_modified: false, paper_eligible: false}`. Source LIVE_PUBLIC_BITGET: REST 1m/15m/1H/4H BTC/ETH, nuova WS books1 dopo REST, wallet Hawk/Toro/Brain Free **sintetici in tempdir**. A differenza del precedente E2E col test stub, qui il congelato vero è stato caricato e valutato in diretta nel runner GitHub. Non ci sono posizioni vere, dati privati o API ordini.

**CI successiva** al commit `906804dc3650d53c6e4173831c4ea0332a9dc1d8`, GitHub Actions run `41347649054`: backend isolated-contract SUCCESS **110/110 test** nelle 12 suite ([17,4,4,10,6,12,9,19,10,4,10,5]), static READ_ONLY_STATIC_GATES_PASS. Il job React può risultare in corso all'atto di lettura; verificarne il completamento. Run live originale 41347649123 SUCCESS. Nessuna modifica alla produzione, nessun merge o deploy.

## Preflight Brain senza leggere segreti

L'app web `superbot` da `.github/workflows/brain-free-app-deploy.yml` monta le directory di **Brain Free e Brain Pilot entrambe in sola lettura** (`/opt/superbot-brain-free`, `/opt/superbot-desk-data/brain`), quindi il solo mount di app o la validità di `brain.sqlite3` **NON indica** quale Brain processi ordini né quale sia vivo sul VPS.

Nuovo `backend/long_shadow_brain_docker_metadata_preflight.py` — indagine **locale read-only** da eseguire solo in occasione di un audit VPS autorizzato: usa esclusivamente `docker ps --format` per i container e `docker inspect --format '{{json .Mounts}}'`; non legge ENV, log o account, non stampa nomi o path di container, saldi o simboli. Produce solo conteggi dei montaggi con `RW=true` per Free o Pilot, distingue app readonly, uno o più writer possibili. **In tutti i casi** `active_owner_confirmed=false`: mount scrivibile non è prova proprietario wallet, il mapping delle runtime deve essere attestato separatamente. 10 test di regressione, inclusi privacy, writer doppi, falsi indizi app readonly e nessuna scrittura Docker.

Comando DIAGNOSTICO soltanto, **NON eseguito su alcuna VPS in questa chat**:

```bash
PYTHONPATH=backend python backend/long_shadow_brain_docker_metadata_preflight.py
```

## Gate non ancora superati

- `AUTHENTIC_FROZEN_V611_PUBLIC_REAL_FEED_SYNTHETIC_WALLET_E2E=PASS`
- `FROZEN_ENGINE_BYTES_HASH_CHECK=PASS`
- `CURRENT_BRAIN_PROCESS_ON_VPS=UNVERIFIED` (non c'è connessione SSH/VPS in questa chat)
- `REAL_WALLET_SNAPSHOT_VALIDATION_ON_VPS=NOT_TESTED`, nessun wallet utente letto
- `LONG_15M_1H_4H_CONTINUITY_H24=NOT_PROVEN`, un sample live non è un servizio
- `ECONOMIC_EVIDENCE=INSUFFICIENT`, 12 NO_TRADE non dimostrano profitto né validità statistica
- `PAPER_ELIGIBLE=NO`, `ORDERS_CREATED=0`, `MERGE=NO`, `DEPLOY=NO`

PR #26 resta DRAFT e non mergiata; PR #27 (chiusura manuale singolo trade per ID) resta DRAFT e separata. Brain AI attuale completamente libero bocciato per prossimo rilascio, futura conversione a Brain rules-governed con ONE wallet dopo completamento LONG. Nessun cambiamento agli SHORT o alla protezione capitale 450 USDT.

## Aggiornamento audit Docker v2 — 1 novembre 2026

L'audit del primo preflight ha rivelato un caso non coperto: un processo writer può avere un nome differente da `brain` o `superbot`, oppure montare una cartella *contenente* il wallet anziché il percorso esatto. Il codice iniziale lo poteva ignorare e sottostimare i candidati.

Corretto in `backend/long_shadow_brain_docker_metadata_preflight.py`: **tutti i container in esecuzione** vengono ispezionati per i soli metadati dei mount Docker (nessuna variabile, nessun log, nessuna lettura wallet). Si confrontano sia `Source` sia `Destination` con le due directory note, comprese cartelle parent e figli. Nomi inattesi, montaggi ampi, web-app con mount scrivibile e più writer causano `AMBIGUOUS_OR_UNEXPECTED_WRITER_MOUNT`. L'output è esclusivamente aggregato e non contiene nomi, percorsi, capitale o credenziali. In ogni caso `active_owner_confirmed=false`, perché un mount Docker non prova che sia il vero processo trading.

Test di regressione ampliati a **16 casi** (10 precedenti + nomi inattesi, mount per `Source`, cartelle parent, web-app erroneamente RW, conteggio completo e fail-closed). La verifica GitHub CI sul commit con patch andrà controllata prima di trattare il preflight come verificato. **Mai eseguire il preflight sulla VPS senza un'azione esplicita dell'operatore.**

Per la prima verifica VPS da Termius, si può usare il singolo comando di sola lettura:

```bash
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
```

Questo elenca solo i container e il loro stato, **non** saldo, credenziali, env né log. È un primo inventario; non attesta ancora il wallet. Dopo aver letto l'elenco si può decidere quale diagnostica mount eseguire, senza cambiare i servizi.
