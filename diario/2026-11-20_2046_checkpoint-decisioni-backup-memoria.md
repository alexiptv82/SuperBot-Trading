# Checkpoint verificabile SuperBot-Trading — 20/11/2026 20:46 Europe/Rome

## Esito sintetico

Dopo il supplemento delle 17:49 sono emerse tre novità verificate: il proprietario ha chiuso l’audit delle fonti esterne con regole vincolanti; il candidato extbackup è stato separato per componenti e parti cifrate; la memoria decisionale di Brain Unico misura ora anche le decisioni duplicate per slot. Le modifiche restano su rami di laboratorio/candidati: non risultano merge su `main`, deploy, installazione, prova reale del nuovo backup, training, ordini o cambi VPS da questo checkpoint.

## Obiettivi e decisioni utente

- Trading esclusivamente **PAPER**, con tre portafogli separati: **Falco**, **Toro**, **Brain**.
- Falco e Toro restano archivi storici integri e intoccabili, classificati `semantic_not_certified`; sono conservati nel dataset per memoria/audit ma esclusi da split, sufficienza e training.
- Brain Unico resta la priorità: memoria verificabile, uscite studiate controfattualmente, rischio esplicito, dati attestati e rollback.
- Audit esterno chiuso: nessuna importazione di operazioni esterne e nessuna seconda memoria operativa. Le fonti pubbliche restano solo riferimento metodologico.
- **Fase A** approvata soltanto dopo la preparazione della RC: analisi offline, read-only e su dati attestati; stesse condizioni per tutte le alternative, confronto fuori campione, journal intatto e nessun parametro scelto sugli stessi dati.
- Nessuna ulteriore indagine o prova Termius sulla contabilità Falco/Toro senza una nuova richiesta del proprietario.

## Configurazione e rischio: desiderato contro implementato

| Area | Desiderato/deciso | Implementato o verificato nel repository | Non attivo / non provato |
|---|---|---|---|
| Falco/Toro | conservazione integrale; nessun training su dati non certificati | righe marcate `excluded` / `semantic_not_certified`; originali preservati | riconciliazione contabile sospesa; nessuna nuova prova autorizzata |
| Brain | PAPER AI-first, memoria decisionale completa, `NO_TRADE` valido | API/UI memoria read-only con copertura, catena, aperture senza traccia, NO_TRADE, chiusure, tesi/reingressi e `duplicate_slot_decisions` | stato live e collaudo PAPER non verificati qui |
| Duplicati per slot | misurazione reale, senza falsi zeri | slot ricavato da `cycle_minutes`; se la configurazione runner non è leggibile il valore è “non verificabile”, non 0 | efficacia sul run reale non certificata |
| Rischio | sizing, limiti, stop/circuit breaker e mandato approvati | perdita giornaliera visibile read-only; misure di memoria disponibili | Issue #124 P0 aperta; profilo rischio definitivo, mandato nuova run e promozione non approvati |
| Uscite | protezione profitti e confronto verificabile | studio documentato come prossima fase | bracci controfattuali e Fase A solo dopo RC; nessuna modifica runtime |
| Backup | componenti indispensabili certificabili separatamente dagli storici | candidato con componenti e parti da 90 MiB, manifest e SHA-256 per parte | nuova prova reale, installazione, copia off-host e restore PC non eseguiti/certificati |

## Novità verificate

1. **Decisione audit e Fase A** — `3d76edbb2e6e0912aee340edd68acdc798a7532d`, solo documentazione: nessuna importazione esterna o seconda memoria; Fase A dopo la RC, offline/read-only su dati attestati.
2. **Correzioni documentali** — `f456cee857e2996094e37bddd24bccde5934f943`: il riepilogo pubblico è `public_summary.json`; i giorni distinti sono `sufficiency.distinct_days`; `feature_source` e `quality_flags` non provano da soli feature verificate; decisioni del journal e righe dataset non sono equivalenti.
3. **Backup separato per componente** — `75a714be3976a732afa88a9aed3c6dc8c248e70f`:
   - `indispensabili`: database + Brain V3 + Arena, accettabile solo con esito 0;
   - `storici`: Falco/Toro e altri storici, esito 0 oppure 3, dove 3 resta integro ma semanticamente non certificato;
   - file cifrati divisi in parti da 90 MiB con SHA-256 per parte e verifica del ricomposto;
   - retention separata; `run.sh` di produzione invariato;
   - **74 test non-root dichiarati** dal commit; prova reale da autorizzare, non eseguita.
4. **Memoria decisionale** — `48876b97340432e31b0ac47cc57cfd8783a3b24e`: API e schermata Brain Unico espongono `duplicate_slot_decisions`; commit con test dedicati per nessun duplicato, riavvio a metà slot, slot diversi e configurazione assente.
5. **Gate riferito dal diario** per `48876b97…`: V3 **5.355**, Dataset Builder **158**, Jest **153**. Fonte: `STATO.md` / commit diario `4443c641…`; non rieseguito in questo checkpoint e non presentato come GitHub Actions indipendente.

## Backup, chiavi e servizi senza dati sensibili

- Prova reale precedente: archivio cifrato di 117.472.954 byte; journal tecnicamente validi Brain 1.058, DeepSeek 1.260, Qwen 1.281, MiniMax 1.306.
- La prova precedente mantiene l’esito corretto: integrità tecnica Brain/Arena verificata, semantica Falco/Toro non certificata. Le anomalie PAPER restano +21,13 USDT Falco, +39,08 USDT Toro e 30 trade Toro presenti soltanto nello storico.
- Il nuovo candidato `75a714be…` risolve nel codice il limite di 100 MB tramite componenti/parti, ma **non prova** che un nuovo archivio sia stato creato, installato, copiato fuori VPS o ripristinato sul PC.
- Ramo storico `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato ma non installato/certificato secondo lo stato consolidato.
- Copia cifrata della chiave `age` sul PC: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. È una verifica locale; non certifica backup, presenza o restore sulla VPS.
- Stato live generale di runner, ExitService, app, backup e VPS: **non verificato** in questo checkpoint.
- Nessuna chiave privata, passphrase, token, segreto o dettaglio utile all’accesso è stato letto o pubblicato.

## Branch, PR, issue e SHA verificati

- `diario` prima di questa scrittura: `4443c6412d203da0685b26f804443e1ecc782412`.
- `integration/brain-unico-20261119`: `48876b97340432e31b0ac47cc57cfd8783a3b24e`.
- `claude/extbackup-storici-20261121`: `75a714be3976a732afa88a9aed3c6dc8c248e70f`.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`, invariato rispetto al checkpoint precedente.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Issue [#124](https://github.com/alexiptv82/SuperBot-Trading/issues/124): **open**, P0; resta NO-GO per nuovi deploy Brain Unico finché non chiusa e verificata.

## Eseguito, preparato, non approvato

- **Eseguito nel repository:** decisione audit documentata; correzioni al rapporto; separazione backup per componenti/parti; misura read-only dei duplicati di memoria; test dichiarati.
- **Preparato:** prova reale dei due componenti di backup; studio delle uscite; Fase A dopo la RC.
- **Non eseguito/non certificato:** nuova prova extbackup, installazione, trasferimento esterno, restore PC, controllo live VPS, collaudo PAPER delle nuove metriche.
- **Non approvato:** merge/deploy, cambi runtime/servizi/rischio, training, ordini, LIVE, API a pagamento, uso di fonti esterne come dati, seconda memoria.
- **Sospeso per decisione utente:** ulteriori diagnosi o prove Termius su Falco/Toro.

## Blocker e prossime attività

1. Conservare Falco/Toro e mantenerli esclusi dal training; nessuna riscrittura degli storici.
2. Preparare la RC Brain Unico con le misure di memoria appena completate.
3. Studiare le uscite e predisporre i bracci controfattuali; eseguire Fase A soltanto dopo la RC e su dati attestati.
4. Proporre il rischio definitivo; Issue #124 P0 e mandato della nuova run restano blocker.
5. Solo con consenso separato: eseguire prova reale dei componenti `indispensabili` e `storici`, quindi certificare copia off-host e restore PC.
6. Non confondere codice/test del candidato con installazione o stato live.

## Istruzioni di ripresa per un’altra AI

1. Leggere `STATO.md`, questo checkpoint e l’ultima versione di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare di nuovo le HEAD di `diario`, integrazione, candidato extbackup, PR #80, Issue #124 e ramo extbackup storico con SHA completi.
3. Usare `48876b97…` come HEAD Brain Unico documentata e `75a714be…` come candidato extbackup, non come codice distribuito.
4. Trattare `duplicate_slot_decisions` come misura read-only; valore non verificabile se manca la configurazione, mai falso zero.
5. Trattare il backup precedente come integrità tecnica Brain/Arena verificata e semantica Falco/Toro non certificata; il nuovo split è preparato ma non provato.
6. Preservare PAPER, EventJournal, storici append-only, divieto di training su dati non attestati e nessun segreto pubblico.

---

Checkpoint esclusivamente documentale; nessuna modifica operativa, merge, deploy, VPS, servizio, reboot, reset, ordine o API a pagamento.
