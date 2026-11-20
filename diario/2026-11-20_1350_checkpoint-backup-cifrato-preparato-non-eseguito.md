# Checkpoint verificabile SuperBot-Trading — 20/11/2026 13:50 Europe/Rome

## Esito sintetico

Dal checkpoint delle 12:47 il ramo laboratorio è avanzato da `03607bec…` a `de59f6775915cb46a2ae63025dbea0466abc04bb`. Sono state committate e testate su dati sintetici una funzione di cifratura `age` e una procedura amministrativa circoscritta per il backup cifrato della run Brain. **Il backup reale non è stato eseguito:** l'accesso non-root alla cartella della run è stato bloccato dai permessi e non è stato usato `sudo`. Non risultano trasferimenti esterni, cambi di permessi, deploy o modifiche ai servizi.

## Obiettivo e perimetro

- Trading esclusivamente **PAPER**; portafogli distinti **Falco**, **Toro** e **Brain**.
- Obiettivo: confronto controllato, gestione rischio esplicita e apprendimento soltanto da eventi/candele attestati.
- Storici ed `EventJournal` append-only; chiusure manuali dell'operatore conservate ma non imitabili.
- Questo checkpoint modifica soltanto documentazione. Nessun merge, deploy, VPS, servizio, riavvio, reset, ordine, API a pagamento o training.

## Configurazioni e rischio: desiderato contro implementato

| Area | Desiderato/deciso | Implementato nel repository | Non provato/non attivo |
|---|---|---|---|
| Portafogli | Falco/Toro/Brain PAPER separati | flussi PAPER e Brain Unico documentati | stato live, capitale e servizi non controllati |
| Rischio | sizing, limiti, stop/circuit breaker e mandato approvati; `NO_TRADE` sempre possibile | anti-reingresso ancora `observe`; stato perdita giornaliera esposto read-only @ `32ea96e4` | `enforce`, profilo rischio v2, soglie definitive e mandato nuova run non approvati; Issue #124 P0 aperta |
| Dati | candele fresche e provenienza attestata | fix feed e test 1m/15m/1h/4h; 15m attestato anche dalla sonda reale | archivio candele ancora `manifest_unanchored`; nessun training |
| Backup | backup coerente, cifrato e ripristinabile fuori VPS | strumenti e procedura testati sinteticamente nel ramo laboratorio | nessuna esecuzione sulla run reale, nessuna copia esterna, nessun restore con la chiave del proprietario |

## Novità verificate

1. **Cifratura e freschezza** — commit `f53df73c00e159e6510276c0710f227077e55948`.
   - Funzione `age` aggiunta al backup; prova completa andata/ritorno con chiave **temporanea di test**.
   - Nessun trasferimento esterno.
   - Test CandleStore per ultima candela chiusa su 1m/15m/1h/4h; la verifica reale disponibile resta quella 15m registrata dalla sonda precedente.
   - Il profilo rischio definitivo resta da approvare: percentuali storiche non diventano automaticamente soglie Brain Unico.
2. **Procedura amministrativa preparata** — commit `de59f6775915cb46a2ae63025dbea0466abc04bb`.
   - Script autonomo e procedura documentata; 6 test da non-root su run sintetica.
   - Sorgente aperta in sola lettura, integrità SQLite, catena del journal, manifest, restore e round-trip cifrato verificati nei test.
   - Nessuna esecuzione come root e nessuna modifica di permessi.
3. **Correzione importante** — la formulazione precedente “nessun chiaro su disco” era troppo ampia. La fase di backup crea copie temporanee in chiaro in un'area privata; soltanto la successiva cifratura è in streaming. I test verificano la pulizia anche in errore, ma la cancellazione è ordinaria del filesystem, non sovrascrittura sicura.
4. **Protezione generale incompleta** — il ramo extbackup descrive Falco/Toro e altri dati storici, ma non è installato/certificato; Brain V3 e Arena non risultano inclusi nell'installazione reale. La nuova procedura riguarda una sola run Brain e non equivale a un backup generale.

## Branch, PR, issue e SHA verificati

- `integration/brain-unico-20261119`: `de59f6775915cb46a2ae63025dbea0466abc04bb`.
- `diario` prima di questo checkpoint: `916732df662c00fbb697f22d48d31ed13804cf8b`.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Issue [#124](https://github.com/alexiptv82/SuperBot-Trading/issues/124): **open**, P0 latch perdita giornaliera; resta NO-GO.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`, preparato ma **non installato né certificato**.

## Test e fonte

- Fonte `STATO.md` @ blob `17f9f820a60f07851ab2d3f50730ff03ba78c64d`: HEAD `de59f677…`, suite **5.352**, Dataset Builder **157**, Jest **152**, 0 falliti.
- Fonte commit `f53df73c…`: round-trip `age` con chiave di test e test freschezza CandleStore 1m/15m/1h/4h.
- Fonte commit `de59f677…`: 6 test non-root su integrità, catena EventJournal, restore, cifratura, chiave errata/manomissione, rifiuti e pulizia in errore.
- I risultati sono attestati dal repository/diario; non sono stati rieseguiti qui e i commit riportano `[skip ci]`. Non sono presentati come GitHub Actions indipendenti.

## Backup, chiavi e servizi

- Verifica PC della copia cifrata della chiave `age`: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. Prova locale soltanto; non certifica backup o restore VPS.
- La nuova prova crittografica usa una chiave effimera di test; non dimostra ancora la decifrabilità con la chiave privata del proprietario.
- Il tentativo di identificare la run reale è rimasto read-only e bloccato dai permessi non-root; nessun contenuto della run è stato letto o copiato.
- Nessuna chiave privata, passphrase, token, comando operativo o dettaglio di accesso viene riportato in questo checkpoint pubblico.
- Stato live di runner, exit service, app, extbackup e VPS: **non verificato**.

## Eseguito, preparato, non approvato

- **Eseguito nel repository:** codice e test di cifratura, test freschezza multi-timeframe, script amministrativo, procedura e piano RC aggiornati.
- **Eseguito sinteticamente:** backup/restore/cifratura e round-trip con chiave temporanea; nessun dato operativo reale.
- **Preparato ma non eseguito:** unica esecuzione amministrativa della run Brain e successiva verifica con la chiave del proprietario.
- **Non approvato/non eseguito:** backup reale come root, trasferimento esterno, modifica extbackup, inclusione Arena, merge/deploy, cambi servizi/permessi/rischio, ordini, LIVE, training e API a pagamento.

## Anomalia documentale

La voce più recente di `STATO.md` è intestata **21/11/2026**, ma il commit GitHub `916732df…` risulta del **20/11/2026 13:37 Europe/Rome**. Lo storico non viene riscritto: questa discrepanza è registrata qui e la data verificabile del presente checkpoint resta 20/11/2026.

## Blocker e prossime attività

1. Issue #124 P0 deve essere chiusa formalmente.
2. Archivio `candles-20261120T064955Z-95a00e9b` ancora da ancorare; nessun training finché `manifest_unanchored`.
3. Profilo rischio Brain Unico e mandato della nuova run da approvare.
4. Backup reale, copia esterna e restore con chiave proprietario richiedono consenso separato; fino ad attestazione completa restano NO-GO.
5. Verificare sidecar di uscita e rollback soltanto nel pre-collaudo autorizzato.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e la versione più recente di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare nuovamente HEAD integrazione/diario, PR #80, Issue #124 ed extbackup con SHA completi.
3. Non confondere test sintetici, sonda reale e stato live: riportare sempre la fonte.
4. Non eseguire la procedura amministrativa, cambiare permessi o trasferire archivi senza consenso esplicito.
5. Preservare PAPER, separazione Falco/Toro/Brain, EventJournal, storici e divieto di training su dati non attestati.

## Fonti principali

- GitHub API/diff dei commit `f53df73c…` e `de59f677…`.
- `STATO.md` ramo `diario`, commit `916732df…`, prima di questa scrittura.
- Libreria `ULTIMO-STATO-SUPERBOT.md` v135: conteneva la HEAD `03607bec…` ma non `f53df73c…` o `de59f677…`.
- Conversazioni recenti: nessun risultato ulteriore restituito dalla ricerca; nessuna pretesa di trascrizioni complete o chat eliminate.

---

Checkpoint solo documentale; nessun segreto o dettaglio operativo di accesso è stato aggiunto.
