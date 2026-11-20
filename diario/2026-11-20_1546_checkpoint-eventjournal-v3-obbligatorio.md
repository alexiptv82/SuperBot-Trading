# Checkpoint verificabile SuperBot-Trading — 20/11/2026 15:46 Europe/Rome

## Esito sintetico

Il candidato documentale per proteggere gli storici è avanzato: `claude/extbackup-storici-20261121` ora punta a `0da29766e7bd03720a1268b458640f0ff0807218` e rende obbligatorio il controllo dell'`EventJournal V3` per Brain V3 attivo e per le tre run Arena. Il commit dichiara 51 test non-root. La procedura reale sugli storici non è stata eseguita: non risultano installazione, trasferimento esterno, esecuzione come root o certificazione del backup completo.

## Obiettivi e vincoli invariati

- Trading esclusivamente **PAPER** con tre portafogli distinti: **Falco**, **Toro** e **Brain**.
- Obiettivo: Brain Unico verificabile, memoria e storici preservati, rischio esplicito e apprendimento solo da dati attestati.
- `EventJournal` e storici append-only; chiusure manuali conservate ma non imitabili automaticamente.
- Nessun merge, deploy, riavvio, reset, ordine, training, API a pagamento o modifica operativa da questo checkpoint.

## Configurazioni e rischio: desiderato contro implementato

| Area | Desiderato/deciso | Implementato o preparato | Non provato/non attivo |
|---|---|---|---|
| Falco/Toro/Brain | tre portafogli PAPER isolati e confrontabili | flussi PAPER e Brain Unico documentati | stato live, capitale e servizi non verificati |
| Rischio | sizing, limiti, stop, mandato e circuit breaker approvati; `NO_TRADE` valido | anti-reingresso `observe`; perdita giornaliera visibile read-only | `enforce`, profilo rischio v2, soglie definitive e mandato nuova run non approvati; Issue #124 aperta |
| Dati | freschezza, provenienza e integrità attestabili | test multi-timeframe e sonda feed; validatore reale 24/24 | archivio candele ancora `manifest_unanchored`; nessun training |
| Backup | tutti gli storici cifrati e ripristinabili senza segreti pubblici | prova positiva su run vuota; candidato extbackup con controlli V3 preparato | storici reali non ancora sottoposti a backup e restore completi; nessuna certificazione off-host |

## Novità verificata e limite

- Commit `0da29766e7bd03720a1268b458640f0ff0807218` sul ramo `claude/extbackup-storici-20261121`.
- Brain V3 attivo e le tre run Arena devono presentare un `journal.db` con tabella `v3_events` e catena valida; l'esito viene registrato nell'indice e riverificato dopo il ripristino. Mancanza o discordanza produce NO-GO.
- L'indice del journal diventa obbligatorio nel ripristino; archivi non V3, come Brain storico/libero/adattivo, non vengono forzati al formato V3.
- Il messaggio di commit riporta **51 test**: 9 nuovi negativi e prova dello script con una run Arena senza journal; la fonte è il commit, non una GitHub Action indipendente.
- La conversazione recente accessibile conferma che il comando definitivo è stato preparato, ma non riporta un esito reale: `ESITO PROVA: OK` resta soltanto l'esito atteso, non ottenuto.

## Stato consolidato dei backup

- Backup cifrato già eseguito dal proprietario: riuscito, ma sulla run Brain preparata, in pausa e mai avviata; 1 evento e 6 file. Prova lo strumento, **non protegge gli storici reali**.
- Storici individuati read-only: Brain V3 attivo, tre Arena, Brain libero/storico/adattivo, area AI e Falco/Toro. Nessun insieme risulta ancora coperto da backup e restore end-to-end verificati.
- Brain libero risulta circa 469 MB, oltre il limite GitHub di 100 MB per singolo file; nessun invio monolitico a GitHub può essere dato per scontato.
- Ramo storico richiesto dall'utente `work/extbackup-bot-stopped-20261109` invariato a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato, non installato o certificato secondo lo stato consolidato; nessun controllo live VPS.

## Branch, PR, issue e SHA verificati

- `diario` prima di questo checkpoint: `913d98c512849cd54d7561eb9b81dc2892ca5f39`.
- `integration/brain-unico-20261119`: invariato a `de59f6775915cb46a2ae63025dbea0466abc04bb`.
- Candidato storici: `claude/extbackup-storici-20261121` a `0da29766e7bd03720a1268b458640f0ff0807218`.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Issue [#124](https://github.com/alexiptv82/SuperBot-Trading/issues/124): resta aperta/P0 secondo il diario; nessuna nuova chiusura verificata.
- Extbackup storico: `work/extbackup-bot-stopped-20261109` a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.

## Test con fonte

- Candidato `0da29766…`: **51 test** dichiarati dal commit; non rieseguiti in questo checkpoint e non presentati come CI indipendente.
- Versione precedente `ad3ae567…`: 42 test non-root; superata dalla nuova HEAD.
- Integrazione Brain resta alla precedente evidenza documentale: suite **5.352**, Builder **157**, Jest **152**, 0 falliti a `de59f677…`; non rieseguiti qui.
- I commit rilevanti riportano `[skip ci]`.

## Chiavi e servizi senza dati sensibili

- Copia cifrata della chiave `age` sul PC: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. È una prova locale e non certifica il backup o restore sulla VPS.
- Non sono stati letti o pubblicati chiavi private, passphrase, token, segreti, percorsi operativi completi o dettagli di accesso.
- Stato live di runner, exit service, app, extbackup e VPS: **non verificato**.

## Eseguito, preparato, non approvato

- **Eseguito nel repository:** correzione del candidato extbackup e test non-root attestati dal commit.
- **Eseguito dal proprietario in precedenza:** backup cifrato della run vuota con 1 evento e 6 file.
- **Preparato ma non eseguito:** prova completa sugli storici reali, inclusi controlli V3 obbligatori, ripristino e verifica dell'indice.
- **Non approvato/non eseguito:** esecuzione come root della prova storici, trasferimento esterno, installazione/modifica extbackup, merge/deploy, cambi servizi/permessi/rischio, ordini, LIVE, training e API a pagamento.

## Anomalie, blocker e prossime attività

- Le voci automatiche più recenti di `STATO.md` sono intestate 21/11/2026, mentre i commit GitHub sono del **20/11/2026**. Lo storico non viene riscritto; questo checkpoint usa la data verificata Europe/Rome.
- Blocker: Issue #124 P0; archivio candele non ancorato; profilo rischio e mandato nuova run non approvati; backup reale degli storici non certificato.
- Prossimo passo soltanto con consenso separato: eseguire la prova sugli storici reali e verificare inventario, spazio, cifratura, indice V3 e restore, senza presumere trasferimenti o installazione.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e l'ultima versione di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare le HEAD complete di `diario`, integrazione, candidato storici, PR #80, Issue #124 ed extbackup storico.
3. Non presentare il backup con 1 evento come protezione degli storici reali e non presentare i 51 test come prova reale sulla VPS.
4. Non eseguire la prova storici, cambiare permessi o trasferire archivi senza consenso esplicito.
5. Preservare PAPER, separazione Falco/Toro/Brain, EventJournal e divieto di training su dati non attestati.

---

Checkpoint esclusivamente documentale; nessun segreto o dettaglio operativo d'accesso aggiunto.
