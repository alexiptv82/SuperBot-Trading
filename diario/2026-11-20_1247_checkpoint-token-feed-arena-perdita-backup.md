# Checkpoint verificabile SuperBot-Trading — 20/11/2026 12:47 Europe/Rome

## Esito sintetico

Dal checkpoint delle 11:46 sono emerse novità verificabili e materialmente rilevanti. Il ramo laboratorio `integration/brain-unico-20261119` è ora a `03607bec2ab884c173bce290720e283bb69d9da7`. Sono stati committati: la politica permanente di efficienza token in `CLAUDE.md`; lo storico Arena in sola lettura; l'esposizione dello stato di perdita giornaliera nella schermata Brain; uno strumento di backup a caldo con verifica di ripristino. Queste modifiche sono **nel ramo laboratorio e non risultano distribuite o attivate sui servizi**. Nessun controllo live della VPS è stato eseguito in questo checkpoint.

## Obiettivo e perimetro invariati

- Trading esclusivamente **PAPER**; nessun ordine reale, LIVE o API a pagamento.
- Tre portafogli distinti: **Falco**, **Toro**, **Brain**. Obiettivo: confronto controllato e tracciabile, senza contaminazione di capitale, rischio, memoria o risultati.
- Storici ed `EventJournal` append-only da preservare; chiusure manuali dell'operatore conservate ma non imitabili dal training.
- Nessun merge su `main`, deploy, riavvio, reset, modifica servizi/VPS o cambio di parametri è autorizzato da questo checkpoint.

## Configurazione e rischio: desiderato contro implementato

| Area | Desiderato/deciso | Implementato e verificato nel repository | Non provato o non attivo |
|---|---|---|---|
| Portafogli | Falco/Toro/Brain PAPER separati | Struttura e flussi PAPER documentati nei checkpoint precedenti | Stato live dei tre servizi e capitale corrente non controllati |
| Rischio | sizing, limiti, stop/circuit breaker e mandato espliciti; `NO_TRADE` sempre possibile | `thesis_id` e anti-reingresso in `observe`; visualizzazione perdita giornaliera read-only aggiunta @ `32ea96e4` | anti-reingresso `enforce`, soglie/profilo rischio v2 e mandato di nuova run non approvati; Issue #124 P0 aperta |
| Dati/apprendimento | usare solo eventi e candele verificabili | archivio e validatore reale già presenti; 24/24 campioni verificati e 24/24 manomissioni rilevate @ `733182f6` | archivio ancora `manifest_unanchored`; nessun training autorizzato |
| UI/storico | Brain Unico come vista principale; Arena consultabile senza comandi | storico Arena `/arena` opt-in e sola lettura @ `e6c3f3d7`; chiusura Arena non importata | nessun deploy/app live verificato |

## Novità verificate dal checkpoint precedente

1. **Politica token applicata** — commit `ccbcf547c7f7686652c9cb2b7c767dde36678d0d`: `CLAUDE.md` modificato con 14 righe aggiunte e 0 rimosse. La policy riduce letture/chiamate ridondanti, ma conserva il gate completo prima di ogni pubblicazione; sicurezza e correttezza prevalgono. Solo documentazione, nessuna configurazione operativa.
2. **Feed reale e storico Arena** — commit `e6c3f3d7ea76c9e665cd88c04d10d9b9c5c97531`: percorso Arena read-only, pagina `/arena`, nessun comando/chiusura Arena. Il messaggio di commit e `STATO.md` registrano una sonda autorizzata di 2 tentativi con ultima candela chiusa presente e pagine contigue. Il rapporto indicato fuori repository non è stato letto in questo checkpoint: si verifica l'attestazione documentale, non il contenuto grezzo della sonda.
3. **Perdita giornaliera nella UI** — commit `32ea96e4ac03a259c91ebca1025bffd417a29335`: stato filtrato `{level, pct}` esposto dal battito e visualizzato in sola lettura; nessuna soglia cambiata. Non chiude Issue #124.
4. **Backup Brain Unico preparato** — commit `03607bec2ab884c173bce290720e283bb69d9da7`: nuovo `backend/v3/runner/run_backup.py`, backup SQLite in sola lettura, `integrity_check`, verifica catena EventJournal, manifest SHA-256 e restore in cartella nuova; 7 test nel commit. Il piano RC dichiara lo strumento pronto, ma esecuzione sui dati reali, cifratura e copia fuori VPS richiedono consenso e **non risultano eseguite**.

## Branch, PR, issue e SHA verificati

- `diario` prima di questo checkpoint: `a207b82644a691cec72b9bde68539307076da6ab`; `STATO.md` include le novità Claude, ma la Libreria v134 si fermava alla proposta delle 11:46.
- `integration/brain-unico-20261119`: `03607bec2ab884c173bce290720e283bb69d9da7`.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0` (verifica API; nessun merge).
- Issue [#124](https://github.com/alexiptv82/SuperBot-Trading/issues/124): **open**, P0 latch perdita giornaliera; resta NO-GO.
- Backup esterno: `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`, preparato ma **non installato né certificato**.

## Test e fonte

- Fonte `STATO.md` del ramo `diario` @ `a207b826…`: gate riferito sulla HEAD laboratorio con **5.341** test suite, **157** Dataset Builder, **152** Jest, 0 falliti.
- Fonte commit `e6c3f3d7…`: 21 test del percorso Arena e Jest 151/151; sonda feed 2 tentativi registrata nel messaggio di commit.
- Fonte commit `03607bec…`: 7 test dedicati al backup/restore, inclusi manomissione, troncamento, destinazione esistente/interna e file non elencati.
- Questi risultati sono evidenza di repository/diario; non sono stati rieseguiti qui e i commit usano `[skip ci]`, quindi non vengono presentati come GitHub Actions indipendenti.

## Backup, chiavi e servizi senza segreti

- Copia cifrata della chiave `age` sul PC: output PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. È una prova locale della copia PC; **non certifica** backup, presenza o restore sulla VPS.
- Il nuovo backup a caldo Brain e il vecchio ramo extbackup sono filoni distinti: entrambi richiedono ancora prova/installazione autorizzata nel contesto reale prima di rimuovere il NO-GO.
- Nessuna chiave privata, passphrase, token, indirizzo o dettaglio di accesso è stato letto o salvato.
- Stato live di runner, exit service, app, backup esterno e VPS: **non verificato in questa esecuzione**.

## Eseguito, preparato, non approvato

- **Eseguito nel repository:** policy token; codice/UI Arena read-only; indicatore perdita giornaliera; strumento e test backup a caldo; aggiornamento piano RC.
- **Preparato ma non distribuito:** l'intera HEAD laboratorio `03607bec…`, piano RC PAPER, backup a caldo sui dati reali, extbackup `3dc2116a…`.
- **Non approvato/non eseguito:** merge `main`, deploy, installazione, riavvio/reset, modifiche VPS/servizi, ordini, LIVE, training, provider/API a pagamento, anti-reingresso `enforce`, soglie numeriche rischio, cifratura/copia esterna del nuovo backup.

## Blocker e prossime attività

1. Issue #124 P0 deve essere chiusa formalmente; la sola visualizzazione della perdita non basta.
2. Ancorare l'archivio candele `candles-20261120T064955Z-95a00e9b` (SHA-256 già registrato `4c982882e53324ce944279b3e016cc8b71f4b96e64e76e7a03afa0021aecf407`); fino ad allora `manifest_unanchored` e nessun training.
3. Solo con consenso separato: eseguire backup/restore sui dati reali, cifrare e copiare fuori VPS; attestare il risultato senza pubblicare segreti.
4. Prima di qualsiasi release: mandato rischio approvato, gate completo verde sul commit candidato, sidecar di uscita sano e rollback provato.
5. Non confondere RC84 #80 con Brain Unico: entrambi restano draft/laboratorio e non distribuiti.

## Istruzioni di ripresa per un'altra AI

1. Leggere prima `STATO.md`, questo checkpoint e la versione più recente di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare nuovamente le HEAD di `diario`, `integration/brain-unico-20261119`, PR #80, Issue #124 ed extbackup; non fidarsi di SHA abbreviati.
3. Trattare test, sonda feed e stato servizi secondo la fonte: non convertire attestazioni del diario in controllo live.
4. Preservare PAPER, separazione Falco/Toro/Brain, EventJournal e storici; nessun training su dati non attestati.
5. Non installare, distribuire, riavviare, eseguire backup reali o modificare rischio senza consenso esplicito ulteriore.

## Fonti principali

- GitHub branch/commit API e diff dei commit `ccbcf547…`, `e6c3f3d7…`, `32ea96e4…`, `03607bec…`.
- `STATO.md` ramo `diario` @ blob `e27959df77640de63627c760968d037bf6fa0a80` prima di questa scrittura.
- Libreria `ULTIMO-STATO-SUPERBOT.md` v134, che non conteneva `ccbcf547` e riportava ancora la policy come proposta.
- Conversazioni recenti: usate solo le porzioni effettivamente accessibili; nessuna pretesa di trascrizioni complete o chat eliminate.

---

Questo checkpoint documenta soltanto. Non modifica codice operativo, servizi, VPS, ordini o configurazioni di trading.
