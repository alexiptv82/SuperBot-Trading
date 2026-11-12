# Checkpoint verificabile — RC84 cutover PAPER applicato in pausa

**Data:** 12/11/2026 12:42 Europe/Rome  
**Ambito di questo checkpoint:** sola documentazione. L'operazione VPS descritta è stata eseguita dall'utente in una conversazione recente; questa esecuzione non ha modificato codice operativo, VPS, servizi, wallet, ordini o GitHub Actions.

## Novità verificata

Due schermate Termius recenti, ore 12:37 e 12:41 Europe/Rome, dimostrano che il cutover controllato preparato nella [PR #90 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/90) è stato effettivamente eseguito sull'HEAD corrente:

- ramo: `work/rc84-paper-unit-cutover-paused-20261112`;
- HEAD GitHub: `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b`;
- script scaricato: `deploy/scripts/rc84-paper-cutover-apply-paused-20261112.py`;
- Git blob verificato prima dell'esecuzione: `dcabc6683e517f09ead3e0bca1a91a719eaf26d0`;
- sintassi Python validata con `ast.parse`;
- eseguiti in sequenza `--check` e `--apply-paused`.

L'output è tornato regolarmente al prompt e riporta:

- `RC84_RELEASE_BACKUP_AND_GATE=PASS`;
- `RC84_RELEASE_FOUR_UNIT_BUNDLE_HASHES=PASS`;
- `RC84_RELEASE_FOUR_WORKERS_INACTIVE=PASS` prima dello switch;
- `RC84_RELEASE_FOUR_UNITS_SWITCHED=PASS`;
- `RC84_RELEASE_HEARTBEATS_FALCO_TORO_BRAIN=PASS`;
- `RC84_RELEASE_BRAIN_EXIT_HEALTHY=PASS`;
- `RC84_RELEASE_NO_NEW_CLASSIC_POSITIONS=PASS`;
- `RC84_RELEASE_PAPER_WORKERS_STARTED_PAUSED=PASS`;
- `RC84_RELEASE_NO_RESET_NO_LIVE=PASS`;
- `RC84_RELEASE_PAUSE_FLAGS_RETAINED=3`;
- `RC84_RELEASE_MANUAL_RESUME_NOT_AUTHORIZED=True`.

La successiva diagnostica alle 12:41 ha prodotto `RC84_POST_RELEASE_DIAGNOSTIC_COMPLETED`. Nella porzione visibile:

- Brain runner punta alla sorgente candidata `/opt/superbot-v3-rc84-repair-ab7e0b7`, con `ActiveState=active`, `SubState=running` e nessun daemon-reload pendente;
- Falco: pausa presente, heartbeat recente, stato `draining`;
- Toro: pausa presente, heartbeat recente, stato `draining`;
- Brain: pausa presente, heartbeat recente, stato `paused`;
- Brain exit: heartbeat recente, stato `healthy`.

## Stato consolidato dei tre portafogli PAPER

| Portafoglio | Obiettivo utente | Stato verificato dopo il cutover |
|---|---|---|
| **Falco** | 1.000 USDT PAPER, scalp LONG/SHORT, distinto da Toro | Worker RC84 avviato ma con pausa presente; heartbeat recente e stato `draining`. Nessuna nuova posizione classica durante il cutover. Il conteggio corrente non è mostrato: 7 resta soltanto il dato dello snapshot precedente. |
| **Toro** | 1.000 USDT PAPER, medio termine LONG/SHORT, fallback d'ingresso separato | Worker RC84 avviato ma con pausa presente; heartbeat recente e stato `draining`. Nessuna nuova posizione classica durante il cutover. Il conteggio corrente non è mostrato: 3 resta soltanto il dato dello snapshot precedente. |
| **Brain** | 2.000 USDT PAPER, DeepSeek AI-first, rischio distinto e uscita single-owner | Runner RC84 attivo sotto pausa; heartbeat `paused`. Nuovo exit worker con heartbeat `healthy`. Nessuna prova di ripresa manuale o chiamata DeepSeek a pagamento. Conteggio posizioni non misurato. |

Le configurazioni desiderate restano quelle già consolidate: Falco scalp, Toro medio, Brain AI-first; leva Brain 20–50x e size 350–400 USDT sono obiettivi/policy candidata già documentati, non valori dimostrati da un trade reale in questo cutover. NO_TRADE resta valido. Trading esclusivamente PAPER.

## Eseguito / preparato / non approvato

### Eseguito e verificato

- Gate e hash del backup/bundle verificati.
- Quattro unità systemd sostituite con le candidate del bundle.
- Worker Falco, Toro, Brain runner e Brain exit avviati.
- Tre pause preservate.
- Falco/Toro in draining, Brain runner paused, Brain exit healthy.
- Nessun reset e nessun LIVE.
- Nessuna nuova posizione classica osservata durante la procedura.
- Diagnostica post-release completata.

### Preparato o ancora separato

- Bundle rollback byte-exact resta parte del pacchetto PR #89/PR #90; non è stato necessario usarlo nell'esito mostrato.
- Backup esterno sul ramo `work/extbackup-bot-stopped-20261109` resta preparato ma non installato né collaudato con restore.
- La verifica PC della copia cifrata age resta `ESITO: VERIFICA OK` con chiave pubblica coincidente; non certifica backup o restore sulla VPS.
- PR #80 RC84 resta riferimento storico Draft; la catena operativa attuale deriva dalle PR #85–#90.

### Non approvato / non provato

- Nessuna rimozione dei `pause.flag` e nessuna ripresa manuale.
- Nessun merge delle PR Draft #85–#90.
- Nessun reset, ordine LIVE o API a pagamento.
- Nessuna prova di stabilità prolungata, chiamata DeepSeek reale, notifiche Telegram end-to-end o browser autenticato dopo questo cutover.
- Nessuna certificazione off-host del backup.
- Nessun conteggio corrente completo delle posizioni; `NO_NEW_CLASSIC_POSITIONS=PASS` dimostra assenza di crescita durante il passaggio, non prova il numero attuale.

## Rami, PR e SHA

- PR #85 Draft, sorgente candidata: `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`, ora usata dalle nuove unità ma non mergiata.
- PR #88 Draft, gate read-only: `337353f225baba535e777d5e49fd2b760dfcfe3f`.
- PR #89 Draft, bundle candidate+rollback: `d8a1a4067bd88406d9e8b34563bf84ee0f39efed`.
- PR #90 Draft, cutover: `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b`, blob script `dcabc6683e517f09ead3e0bca1a91a719eaf26d0`.
- Le PR risultano ancora Draft/non mergiate al controllo GitHub. La descrizione della PR #90 è ormai storicamente superata quando dice “non ancora eseguito”; prevalgono le prove Termius successive.

## Backup, chiavi e storici

Lo snapshot certificato precedente resta una copia locale sulla stessa VPS: 25 file, manifest SHA-256 `a18aff67032605045dd3ef3888f5d225fdd8930b49d89d780aa676aca8f6c8fa`, tre pause, Falco 7/Toro 3 al momento della copia e conteggio Brain non misurato. Non è un backup off-host. Nessuna prova mostra perdita o reset di wallet, storici, learning o EventJournal durante il cutover; la procedura dichiara `NO_RESET_NO_LIVE=PASS`.

## Blocker e rischi residui

1. **Ripresa manuale non autorizzata:** mantenere i tre pause flag.
2. **PR Draft in esecuzione:** la VPS ora punta a sorgente/unità non mergiate; conservare SHA e rollback esatti.
3. **Owner delle uscite:** il Brain exit nuovo è healthy e il legacy Brain exit era inattivo; per Falco/Toro i legacy exit risultavano active nel gate precedente. Verificare in sola lettura assenza di doppie chiusure/owner prima di qualsiasi resume.
4. **Stabilità non ancora prolungata:** i heartbeat sono recenti ma fotografano pochi secondi dopo l'avvio.
5. **Backup off-host assente:** extbackup/restore VPS ancora non certificati.
6. **Conteggi correnti non noti:** non dedurre 7/3 come valori attuali e non attribuire eventuali chiusure senza EventJournal.

## Prossimo passo sicuro

Senza rimuovere le pause e senza chiamare provider a pagamento, eseguire una verifica read-only dopo un intervallo ragionevole: stato delle quattro unità, heartbeat non stale, Brain exit healthy, assenza di crash/restart loop, nessun nuovo ingresso, nessuna doppia chiusura Falco/Toro e integrità EventJournal/storici. Solo dopo prove stabili e una nuova autorizzazione esplicita si potrà valutare la ripresa manuale PAPER. Nessun comando di resume è incluso o autorizzato da questo checkpoint.

## Istruzioni di ripresa

1. Leggere `STATO.md` e questo file.
2. Considerare il cutover **applicato**, ma i portafogli ancora **in pausa**.
3. Verificare sempre SHA `0a2fa7e...`, sorgente `ab7e0b7...` e blob `dcabc668...`.
4. Non confondere Draft/non mergiato con “non installato”: in questo caso la sorgente Draft è installata sulla VPS.
5. Preservare PAPER, pause, snapshot, rollback, storici ed EventJournal.
6. Non esporre segreti o assumere trascrizioni integrali di chat eliminate.
