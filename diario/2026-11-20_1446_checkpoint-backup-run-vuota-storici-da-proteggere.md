# Checkpoint verificabile SuperBot-Trading — 20/11/2026 14:46 Europe/Rome

## Esito sintetico

Il diario GitHub attesta che il proprietario ha eseguito con successo la procedura cifrata preparata a `de59f677…`, ma il backup riguardava una run Brain **preparata, in pausa e mai avviata**: 1 evento e 6 file, quindi nessuno storico reale di trading è stato protetto. Gli storici reali sono stati individuati solo tramite metadati/processi e restano senza un backup verificato. Per colmare la lacuna è stato preparato il ramo isolato `claude/extbackup-storici-20261121` @ `ad3ae56734f740ec87b1466c6f89e1bdcd61c3cb`, con 42 test non-root; la prova sugli storici reali non è stata eseguita.

## Obiettivi e vincoli invariati

- Trading esclusivamente **PAPER**; portafogli separati **Falco**, **Toro** e **Brain**.
- Obiettivo: Brain Unico verificabile, memoria/storici preservati, rischio esplicito e apprendimento solo da dati attestati.
- `EventJournal` e storici append-only; chiusure manuali conservate ma non imitabili.
- Nessun merge, deploy, riavvio, reset, ordine, training, API a pagamento o modifica operativa da questo checkpoint.

## Configurazioni e rischio: desiderato contro implementato

| Area | Desiderato/deciso | Implementato/preparato | Non provato/non attivo |
|---|---|---|---|
| Falco/Toro/Brain | tre portafogli PAPER isolati e confrontabili | flussi PAPER e Brain Unico documentati | stato live, capitale e servizi non verificati |
| Rischio | sizing, limiti, stop, mandato e circuit breaker approvati; `NO_TRADE` valido | anti-reingresso `observe`; perdita giornaliera visibile read-only | `enforce`, profilo rischio v2, soglie definitive e mandato nuova run non approvati; Issue #124 aperta |
| Dati | freschezza, provenienza e integrità attestabili | test multi-timeframe e sonda feed; validatore reale 24/24 | archivio candele ancora `manifest_unanchored`; nessun training |
| Backup | tutti gli storici cifrati e ripristinabili, senza segreti pubblici | procedura singola verificata su run vuota; candidato extbackup storici preparato | storici reali non ancora sottoposti a prova completa; nessun trasferimento/certificazione off-host |

## Novità verificate e loro limiti

1. **Backup cifrato eseguito dal proprietario, ma sulla run sbagliata per lo scopo storico.**
   - Fonte: `STATO.md` sul ramo `diario`, commit precedente `bf24b4e…`.
   - Procedura `de59f677…` con impronta attestata OK; archivio cifrato prodotto con 1 evento e 6 file.
   - Il codice di preparazione spiega il singolo evento: `run_prepared`, configurazione, mandato, budget, pausa e marcatore. La run non era mai stata avviata.
   - Conclusione corretta: prova positiva dello strumento su una run reale ma vuota; **nessuna certificazione degli storici di trading**. Questo checkpoint non ha letto l'output live né il contenuto dell'archivio.
2. **Storici reali individuati, non copiati.**
   - Sono documentati: Brain V3 attivo, tre run Arena, Brain libero, Brain storico, Brain adattivo, area AI e Falco/Toro.
   - L'individuazione è stata read-only tramite processi/struttura; per le aree protette non è stato letto il contenuto.
   - Brain libero risulta circa 469 MB: supera il limite GitHub di 100 MB per singolo file, quindi un futuro backup non può assumere un invio diretto monolitico.
   - Nessuno di questi insiemi risulta coperto da un backup e restore verificati end-to-end.
3. **Candidato extbackup storici.**
   - Prima versione: `16571ae35ec8cdf04a227824d5fe6e2b228be959`, 34 test.
   - HEAD corretta: `ad3ae56734f740ec87b1466c6f89e1bdcd61c3cb`, 42 test non-root.
   - Copia ricorsiva filtrata, SQLite in sola lettura, integrità, archivi obbligatori con NO-GO preventivo, controllo spazio, inventario e confronto della catena EventJournal V3 anche dopo restore.
   - **Preparato soltanto:** nessuna esecuzione come root, nessun trasferimento, nessuna installazione o modifica del backup esistente.

## Branch, PR, issue e SHA verificati

- `diario` prima del presente checkpoint: `bf24b4e6652b5958966870523380684247c0b04e`.
- `integration/brain-unico-20261119`: invariato @ `de59f6775915cb46a2ae63025dbea0466abc04bb`.
- Candidato storici: `claude/extbackup-storici-20261121` @ `ad3ae56734f740ec87b1466c6f89e1bdcd61c3cb`.
- Backup esterno storico richiesto dall'utente: `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`; resta preparato e non certificato/installato secondo lo stato consolidato, senza controllo live in questa esecuzione.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Issue [#124](https://github.com/alexiptv82/SuperBot-Trading/issues/124): **open**, P0; resta NO-GO.

## Test e fonte

- Candidato extbackup `ad3ae567…`: **42 test non-root** riferiti dal messaggio di commit, inclusi catena hash, troncamento/manomissione, journal mancante, originale riscritto, archivio obbligatorio mancante e prova completa sintetica.
- Versione precedente `16571ae3…`: 34 test; superata dalla HEAD corretta.
- Integrazione Brain resta alla precedente evidenza documentale: suite **5.352**, Builder **157**, Jest **152**, 0 falliti @ `de59f677…`.
- Tutti i commit rilevanti riportano `[skip ci]`; i test non sono stati rieseguiti qui e non sono presentati come GitHub Actions indipendenti.

## Backup, chiavi e servizi senza dati sensibili

- Copia cifrata della chiave `age` sul PC: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. Prova locale; non certifica il backup o restore VPS.
- Il backup della run vuota dimostra che il percorso crittografico può produrre un archivio, non che la chiave privata del PC abbia già restaurato gli storici reali.
- Nessuna chiave privata, passphrase, token, percorso operativo completo, comando amministrativo o dettaglio di accesso è riportato qui.
- Stato live di runner, exit service, app, extbackup e VPS: **non verificato da questa esecuzione**.

## Eseguito, preparato, non approvato

- **Eseguito dal proprietario e attestato nel diario:** backup cifrato della run preparata/vuota; 1 evento, 6 file, esito OK.
- **Eseguito nel repository:** sviluppo del candidato extbackup storici e 42 test non-root.
- **Preparato ma non eseguito:** inventario/prova completa sugli storici reali, restore e cancellazione dell'ambiente di prova.
- **Non approvato/non eseguito:** prova storici come root, trasferimento esterno, installazione/modifica extbackup, merge/deploy, cambi servizi/permessi/rischio, ordini, LIVE, training e API a pagamento.

## Anomalie e limiti documentali

- Le nuove voci automatiche di `STATO.md` sono intestate 21/11/2026, ma i relativi commit GitHub sono del **20/11/2026**. Lo storico non viene riscritto; il presente checkpoint usa la data verificata Europe/Rome.
- L'esito del backup singolo proviene dal diario/conversazione accessibile e non da un controllo live indipendente di questa AI.
- I contenuti di alcune aree protette restano da inventariare; non si assume che esistano dati validi finché la prova non li elenca.

## Blocker e prossime attività

1. Issue #124 P0 da chiudere formalmente.
2. Archivio candele da ancorare; nessun training finché `manifest_unanchored`.
3. Profilo rischio Brain Unico e mandato nuova run da approvare.
4. Solo con consenso separato: eseguire la prova extbackup sugli storici reali, verificare inventario, spazio, cifratura e restore; nessun trasferimento nella prova.
5. Progettare la destinazione del file Brain libero senza presumere compatibilità col limite GitHub per file.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e l'ultima versione di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare le HEAD complete di `diario`, integrazione, candidato storici, PR #80, Issue #124 e ramo extbackup storico.
3. Non presentare il backup con 1 evento come protezione degli storici reali.
4. Non eseguire la prova storici, cambiare permessi o trasferire archivi senza consenso esplicito.
5. Preservare PAPER, separazione Falco/Toro/Brain, EventJournal e divieto di training su dati non attestati.

## Fonti principali

- GitHub `STATO.md` @ blob `90c82fb0987112ad0cfa5974fdf7535494f21981` prima di questa scrittura.
- Commit candidato extbackup `16571ae3…` e `ad3ae567…`.
- Libreria `ULTIMO-STATO-SUPERBOT.md` v136, che non conteneva questi SHA né l'esito della run con 1 evento.
- Conversazione recente accessibile: conferma read-only della ricognizione; nessuna pretesa di trascrizione completa o stato live generale.

---

Checkpoint esclusivamente documentale; nessun segreto o dettaglio operativo d'accesso aggiunto.
