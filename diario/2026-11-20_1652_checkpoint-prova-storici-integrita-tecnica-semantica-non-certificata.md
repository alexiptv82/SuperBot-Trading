# Checkpoint verificabile SuperBot-Trading — 20/11/2026 16:52 Europe/Rome

## Esito sintetico

È stata eseguita una prova reale sugli storici. Il backup cifrato è stato prodotto e i journal V3 obbligatori risultano tecnicamente verificati, ma il ripristino ha rilevato quattro anomalie semantiche nei dati PAPER di Falco/Toro. L'esito corretto resta **NO-GO / integrità tecnica OK ma semantica non certificata**: non esiste ancora un backup completo certificato. Il candidato di lavoro è avanzato a `f60b90d64521cd8834f6f99d85d7fe04f8187d99`, con diagnostica read-only preparata e 67 test dichiarati; nessuna nuova prova completa è stata eseguita dopo questa correzione.

## Obiettivi e decisioni invariati

- Trading esclusivamente **PAPER**; portafogli distinti **Falco**, **Toro** e **Brain**.
- Brain Unico verificabile, memoria e storici preservati, rischio esplicito e apprendimento solo da dati attestati.
- `EventJournal` e storici append-only; chiusure manuali conservate ma non imitate automaticamente.
- `NO_TRADE` valido; nessun riempimento forzato degli slot.
- Nessun merge, deploy, riavvio, reset, ordine, training, API a pagamento o modifica operativa da questo checkpoint.

## Configurazioni e rischio: desiderato contro implementato

| Area | Desiderato/deciso | Implementato o preparato | Non provato/non attivo |
|---|---|---|---|
| Falco/Toro/Brain | tre portafogli PAPER isolati e confrontabili | flussi PAPER e Brain Unico documentati; Falco/Toro rilevati fermi nella prova | stato live generale, capitale corrente e servizi non verificati da questo checkpoint |
| Rischio | sizing, limiti, stop, mandato e circuit breaker approvati | anti-reingresso `observe`; perdita giornaliera read-only | `enforce`, profilo rischio v2, soglie definitive e mandato nuova run non approvati; Issue #124 aperta |
| Dati | provenienza, freschezza e integrità attestabili | journal V3 di Brain/Arena verificati nella prova; diagnostica classici read-only preparata | archivio candele ancora `manifest_unanchored`; origine dei 30 trade Toro extra non spiegata; nessun training |
| Backup | storici cifrati e ripristinabili senza segreti pubblici | archivio cifrato reale prodotto; integrità tecnica Brain/Arena verificata | semantica Falco/Toro non certificata; nessuna installazione o copia off-host certificata |

## Prove reali e risultati verificati

1. **Prima prova estesa:** inventario di circa 535 MiB, spazio richiesto circa 4.237 MiB e disponibile circa 21.305 MiB. NO-GO sul confine di ciclo Falco/Toro perché i bot erano fermi e veniva usata la modalità normale; nessun ripristino eseguito in quel tentativo.
2. **Correzione modalità bot fermi:** commit `4a4db056e25e2b2d5389c65d0e08efcbec35f893`, 54 test dichiarati. Se entrambi i classici sono fermi usa la modalità dedicata; stati misti/non verificabili restano NO-GO. Nessun controllo di integrità indebolito.
3. **Prova reale successiva:** archivio cifrato di **117.472.954 byte** prodotto. Journal verificati: Brain V3 1.058 eventi; DeepSeek 1.260; Qwen 1.281; MiniMax 1.306. Le catene risultano valide secondo il diario più recente.
4. **Ripristino non certificato:** quattro problemi su Falco/Toro. Differenze contabili di +21,13 e +39,08 USDT PAPER; Toro presenta 25 trade nello stato e 55 nello storico, quindi 30 righe soltanto nello storico. L'origine di queste righe non è ancora nota.
5. **Correzioni successive:** `c692ce68e9d65929e0875d2ceb9b2e7dbd005119` ha migliorato visibilità errori e persistenza dei soli registri testuali, con 61 test; è superato da `f60b90d64521cd8834f6f99d85d7fe04f8187d99`, che ricostruisce la contabilità secondo il motore, separa difetti tecnici da anomalie semantiche e dichiara 67 test.

## Interpretazione corretta del risultato

- Backup e journal V3: **integrità tecnica verificata nella prova**.
- Ripristino complessivo: **non certificato** per la semantica Falco/Toro.
- L'ipotesi che le differenze dipendano dalla gestione di cassa, salvadanaio, posizioni aperte e limiti di perdita del motore è compatibile con il segno degli scarti ma non ancora confermata sui dati reali.
- I 30 trade Toro presenti solo nello storico restano un blocker distinto.
- Non ripetere la prova completa prima della diagnostica read-only richiesta; non alterare gli storici e non trasformare l'esito 3 in OK.

## Branch, PR, issue e SHA verificati

- `diario` prima di questo checkpoint: `1435bdf7fa3a2546c9c3a049bd17a1314774ccb2`.
- `claude/extbackup-storici-20261121`: `f60b90d64521cd8834f6f99d85d7fe04f8187d99`.
- `integration/brain-unico-20261119`: invariato a `de59f6775915cb46a2ae63025dbea0466abc04bb`.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Issue [#124](https://github.com/alexiptv82/SuperBot-Trading/issues/124): **open**, P0.
- Ramo storico `work/extbackup-bot-stopped-20261109`: invariato a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`; preparato e non installato/certificato secondo lo stato consolidato.

## Test e fonte

- `4a4db056…`: 54 test dichiarati dal commit.
- `c692ce68…`: 61 test dichiarati dal commit.
- `f60b90d6…`: 67 test dichiarati dal commit; è la HEAD corrente del candidato.
- Integrazione Brain: precedente evidenza documentale suite **5.352**, Builder **157**, Jest **152**, 0 falliti a `de59f677…`.
- I test non sono stati rieseguiti in questo checkpoint; i commit riportano `[skip ci]` e non sono presentati come GitHub Actions indipendenti.

## Backup, chiavi e servizi senza dati sensibili

- Copia cifrata della chiave `age` sul PC: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. Prova locale soltanto; non certifica la presenza o il ripristino del backup sulla VPS.
- Il nuovo archivio dimostra il percorso cifrato della prova, non una copia esterna permanente né un backup installato.
- Nessuna chiave privata, passphrase, token, segreto, comando amministrativo o dettaglio d'accesso è riportato.
- Falco e Toro risultavano fermi nella ricognizione collegata alla prova; lo stato live generale di runner, exit service, app, extbackup e VPS non è stato verificato da questo checkpoint.

## Eseguito, preparato, non approvato

- **Eseguito dal proprietario:** inventario, backup cifrato reale, verifica dei journal V3 e tentativo di ripristino; risultato non certificato per quattro anomalie Falco/Toro.
- **Eseguito nel repository:** correzioni `4a4db056`, `c692ce68` e `f60b90d6`, con test dichiarati.
- **Preparato ma non eseguito:** diagnostica read-only sui classici e classificazione dell'origine dei 30 trade Toro extra; nessuna nuova prova completa dopo `f60b90d6`.
- **Non approvato/non eseguito:** modifica degli storici, indebolimento dei controlli, installazione extbackup, trasferimento esterno, merge/deploy, cambi servizi/permessi/rischio, ordini, LIVE, training e API a pagamento.

## Blocker e prossime attività

1. Eseguire soltanto la diagnostica read-only già preparata per ricostruire contabilità e provenienza dei 30 trade Toro extra.
2. Correggere codice o classificazione solo dopo evidenza diagnostica; non correggere o riscrivere i dati storici.
3. Ripetere la prova completa soltanto dopo diagnosi e autorizzazione; l'esito accettabile deve distinguere integrità tecnica e certificazione semantica.
4. Restano inoltre Issue #124 P0, archivio candele non ancorato e profilo rischio/mandato nuova run non approvati.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e l'ultima versione di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare le HEAD di `diario`, candidato extbackup, integrazione, PR #80, Issue #124 e ramo extbackup storico.
3. Trattare il risultato corrente come **integrità tecnica OK, semantica non certificata**, mai come backup completo riuscito.
4. Non ripetere Termius/prova completa prima della diagnostica read-only e non alterare storici, EventJournal o servizi.
5. Preservare PAPER, separazione Falco/Toro/Brain e divieto di training su dati non attestati.

---

Checkpoint esclusivamente documentale; nessun segreto o dettaglio operativo d'accesso aggiunto.
