# Checkpoint verificabile — RC84 gate read-only e bundle unità, nessun cutover

**Data:** 12/11/2026 11:44 Europe/Rome  
**Ambito:** sola documentazione; PAPER ONLY; storici ed EventJournal da preservare.

## Esito consolidato

Dopo il checkpoint delle 10:49 sono emersi riscontri nuovi dalle conversazioni recenti accessibili e da schermate Termius salvate nella Libreria. Non è disponibile una trascrizione integrale di eventuali chat eliminate e non è stato eseguito un nuovo controllo autonomo della VPS: i fatti operativi sotto derivano esclusivamente dagli output visibili, confrontati con GitHub.

### Fatto e verificato

- Diagnosi iniziale alle 10:57: il processo individuato come possibile writer era il demone `docker`; nessun file dei tre wallet risultava aperto o scrivibile da quel processo, output `RC84_DIAGNOSI_SOLO_LETTURA=PASS`.
- Alle 11:00 il primo preflight ha correttamente rifiutato l'attivazione per il falso positivo `possible_competing_paper_wallet_process_count_1`. Erano visibili container legacy ancora attivi: `superbot`, `superbot-rc84-paper-close-bridge`, preview RC84 e preview RC70. Questo non prova che i nuovi worker fossero attivi.
- Diagnosi Docker alle 11:03: il container `superbot` montava Falco/Toro/Brain in sola lettura; il close bridge autorizzato montava i tre wallet in lettura/scrittura; output `RC84_DIAGNOSI_DOCKER_READONLY=PASS`.
- [PR #88 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/88), ramo `work/rc84-paper-cutover-readonly-gate-20261112`, HEAD verificato `337353f225baba535e777d5e49fd2b760dfcfe3f`: alle 11:07 il checker pinned ha prodotto `RC84_CUTOVER_PREFLIGHT_READ_ONLY=PASS` e `RC84_CUTOVER_NO_SERVICES_OR_DATA_MODIFIED=PASS`. Ha verificato backup+sorgenti, quattro template esatti, piano di path swap, close bridge come writer autorizzato e nessun altro container Docker con wallet RW. Ha anche rilevato legacy exit Falco e Toro **ACTIVE**, legacy Brain exit **INACTIVE**. L'attivazione risultava esplicitamente non autorizzata.
- [PR #89 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/89), ramo `work/rc84-paper-unit-bundle-paused-20261112`, HEAD `d8a1a4067bd88406d9e8b34563bf84ee0f39efed`: alle 11:24 `--check` e `--prepare` hanno prodotto `RC84_BUNDLE_PREPARED_AND_VERIFIED=PASS`, quattro unità candidate più quattro rollback, nessuna pending close/reset, nessuna modifica systemd o wallet, nessun deploy/restart. Bundle preparato in directory separata collegata alla sorgente candidata RC84 `ab7e0b7...`.
- [PR #90 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/90), ramo `work/rc84-paper-unit-cutover-paused-20261112`: alle 11:32 lo script dalla revisione `182486cb3d5e3d7e658198e56d4207edb9de8cd2` ha eseguito **solo** `--check`, con `RC84_RELEASE_BACKUP_AND_GATE=PASS`, hash del bundle PASS, quattro worker inattivi PASS, `RC84_RELEASE_READ_ONLY_CHECK=PASS` e `RC84_RELEASE_NOT_APPLIED=True`.
- GitHub mostra ora PR #90 a HEAD successivo `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b` (3 commit, aggiornata alle 11:37 Europe/Rome). Nei riscontri accessibili non compare una nuova esecuzione VPS riferita a questo HEAD: il PASS delle 11:32 **non ricertifica automaticamente** la revisione corrente.

### Stato dei tre portafogli PAPER

- Obiettivo utente invariato: Falco 1.000 USDT PAPER con identità scalp LONG/SHORT; Toro 1.000 USDT PAPER con identità medio termine LONG/SHORT; Brain 2.000 USDT PAPER guidato da DeepSeek, con gestione uscite single-owner e rischio distinto.
- Ultimo snapshot certificato invariato: copia locale sulla stessa VPS, manifest SHA-256 `a18aff67032605045dd3ef3888f5d225fdd8930b49d89d780aa676aca8f6c8fa`, 25 file verificati, tre pause conservate, Falco 7 posizioni e Toro 3 al momento dello snapshot; conteggio Brain non misurato.
- Nessuna prova nuova di reset, nuovi ordini, rimozione pause o perdita degli storici/EventJournal.
- I quattro **worker candidati systemd** risultavano inattivi nel check delle 11:32. Parallelamente, gli output delle 11:00–11:07 mostrano componenti legacy/close bridge attivi: non descrivere l'ambiente come completamente spento.
- Con uscite legacy Falco/Toro attive e close bridge autorizzato, lo stato delle posizioni può cambiare dopo lo snapshot; senza una nuova lettura non inventare conteggi correnti. Brain legacy exit risultava inattivo nel gate delle 11:07.

## Preparato, non rilasciato

- Sorgente candidata RC84 `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`: staged, non installata.
- Bundle candidate+rollback PR #89: preparato e verificato in directory separata, non installato in systemd.
- Procedura PR #90 `--apply-paused`: predisposta per un cutover controllato con pause mantenute e rollback delle unità; **non eseguita e non autorizzata da questo checkpoint**.
- Backup esterno ramo `work/extbackup-bot-stopped-20261109`: preparato, non installato.
- Verifica PC della copia cifrata della chiave age: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica presenza, esecuzione o restore del backup sulla VPS.

## Rilasciato / installato

Nessun nuovo rilascio verificato: nessun merge, deploy, installazione unità, daemon-reload, avvio dei quattro worker candidati, reset, ordine o LIVE.

## Test e fonti

- Screenshot Termius 10:57: `RC84_DIAGNOSI_SOLO_LETTURA=PASS`.
- Screenshot Termius 11:03: `RC84_DIAGNOSI_DOCKER_READONLY=PASS`.
- Screenshot Termius 11:07: gate PR #88 read-only PASS e nessuna modifica.
- Screenshot Termius 11:24: bundle PR #89 preparato/verificato PASS, no systemd/wallet/deploy/restart.
- Screenshot Termius 11:32: revisione PR #90 `182486cb...`, check read-only PASS e `NOT_APPLIED=True`.
- Riscontro GitHub corrente: PR #88/#89/#90 tutte Draft e non mergiate; HEAD come sopra. I run Actions storici #43095712678 e #43096514061 non costituiscono prova di questa preparazione e restano irrilevanti per autorizzare l'apply.

## Problemi e blocker

1. Nessuna certificazione VPS disponibile per l'HEAD corrente `0a2fa7e...` della PR #90.
2. L'apply richiede consenso operativo separato; questo checkpoint documentale non lo concede.
3. Topologia mista: quattro worker candidati inattivi, ma close bridge/container e legacy exit Falco/Toro attivi; serve evitare doppio owner durante un eventuale handover.
4. Brain legacy exit risultava inattivo; il nuovo Brain exit Type=notify deve diventare healthy prima del runner, con rollback verificabile.
5. Snapshot locale non è backup off-host; extbackup e restore VPS non sono installati/certificati.
6. Conteggi posizioni correnti non noti dopo lo snapshot; non dedurli.

## Prossimo passo sicuro

Prima di qualunque apply, rieseguire in sola lettura il checker **sull'HEAD esatto corrente** della PR #90, verificare hash/pin, quattro worker inattivi, tre pause, writer/owner unici e bundle intatto. Solo dopo revisione dell'output e consenso esplicito separato si potrà valutare `--apply-paused`; il comando di apply non fa parte di questo checkpoint. Dopo un eventuale cutover autorizzato servirebbero prove post-release PAPER, heartbeats paused/draining, Brain exit healthy, nessuna crescita inattesa delle posizioni e rollback pronto.

## Istruzioni di ripresa

1. Leggere `STATO.md` ramo `diario` e questo checkpoint.
2. Verificare PR #88, #89 e #90 ai rispettivi HEAD correnti; non trasferire risultati da uno SHA a un altro.
3. Trattare staged/prepared come **non installato**.
4. Mantenere PAPER, tre pause, storici ed EventJournal; niente reset o LIVE.
5. Non esporre segreti o dettagli di accesso VPS.
