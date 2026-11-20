# Checkpoint verificabile SuperBot-Trading — 20/11/2026 23:45 Europe/Rome

## Esito sintetico

Dal checkpoint delle 22:51 sono emerse novità verificate: il collaudo Brain PAPER è stato diviso in due fasi; il proprietario ha richiesto un tetto esplicito di quattro posizioni; la correzione è stata preparata e testata su un ramo isolato, ma non è ancora approvata né integrata. È inoltre emersa una sottostima del rischio aperto ricostruito dal journal perché i costi stimati non sono inclusi: la correzione contabile è soltanto proposta. Nessuna modifica operativa, run, servizio o VPS è stata eseguita.

## Correzione del checkpoint precedente

Il file append-only delle 22:51 e la sua sezione Library contengono accidentalmente un carattere `+` all'inizio di ogni riga. Il contenuto fattuale è integro, ma la resa Markdown è degradata. Per rispettare l'append-only non viene riscritto: questo checkpoint sostituisce la sua funzione di ripresa con formattazione corretta e preserva integralmente la sezione storica difettosa.

## Obiettivi e decisioni consolidate

- Solo trading **PAPER**; storici ed EventJournal preservati.
- Tre portafogli: **Falco**, **Toro**, **Brain**.
- Falco e Toro restano archivi integri, `semantic_not_certified`, esclusi da split, sufficienza e training; nessuna nuova indagine senza richiesta.
- Brain Unico resta la priorità, con nuova run separata e nessun riuso/cancellazione dei journal storici.
- Profilo B per 2.000 USDT: 1%/circa 20 USDT stimati per operazione, rischio aperto 4%, avviso giornaliero 3%, stop nuove aperture 4%, floor 1.600 USDT, leva 1–30×, margine 20% per posizione e 50% totale.
- Il mandato resta `approved:false`; nessuna configurazione è attiva.

## Collaudo PAPER in due fasi

| Fase | Decisione verificata | Stato |
|---|---|---|
| Fase 1 | Verifica tecnica rapida di 72 ore, 8 simboli, profilo B; non è una valutazione delle prestazioni | Documentata in `66989d8add77f33914b42d65a3baee100216e72e`; non avviata |
| Fase 2 | Prime 25 crypto più XAUUSDT/XAGUSDT, solo dopo Fase 1 positiva; nuova config e nuovo mandato; budget ricavato dal costo AI misurato | Solo roadmap, non approvata per attivazione |
| Posizioni | Massimo 4 esplicito richiesto dal proprietario | Correzione pronta su ramo isolato, non integrata |
| Mandato | Deve restare non approvato fino a pre-collaudo e protezione storici | `approved:false` verificato |

## Massimo quattro posizioni: desiderato vs implementato

- Prima della correzione, “quattro” era solo implicito: 4% di rischio aperto / 1% per operazione. Operazioni ridotte dai limiti di margine potevano rischiare meno dell'1% e consentire più di quattro aperture.
- Ramo isolato `claude/tetto-posizioni-20261121` @ `6eac67aa896d7115b7dd03fd5cb8fec703a1edc3`:
  - aggiunge `max_open_positions` nel controllo serializzato `recheck_paper_open`, sotto lock e sullo stato fresco;
  - rifiuta la quinta apertura;
  - vale per il percorso sidecar previsto per la RC; il percorso legacy non passa da questa conferma;
  - non modifica gli altri parametri del profilo B.
- Stato: **preparato e testato, ma da approvare prima dell'integrazione**. L'HEAD di integrazione `1debd53d…` contiene soltanto documentazione, non il fix.

## Lacuna del rischio aperto

- La ricostruzione dal journal somma distanza ingresso-stop × quantità senza includere i costi stimati.
- Il RiskManager include invece i costi stimati: i due valori non sono in parità.
- Verifica documentata: senza il tetto, con gli otto simboli il rischio stimato complessivo avrebbe potuto raggiungere circa **5,3–6,1%**, oltre il budget del 4%.
- Con il tetto di quattro posizioni, ogni posizione resta ≤1% stimato e il totale resta ≤4%; tuttavia vicino al floor la sottostima residua è indicata in circa 5–7 USDT per posizione.
- Correzione proposta: includere i costi stimati nel rischio aperto e aggiungere test di parità con `quote_paper_risk`. **Non applicata e non approvata.**

## Test e fonti

- Fonte commit `6eac67aa`: 7 test mirati per 0/3 posizioni ammesse, quinta rifiutata, chiusura/riapertura, ricostruzione dopo riavvio, percorso serializzato e concorrenza.
- Lo stesso commit dichiara che 5 dei 7 test falliscono senza il controllo e che la suite V3 completa sul ramo ha **5.400 test passati**.
- Due test preesistenti di `open_serial` sono stati adattati per continuare a verificare il veto del budget con non più di tre posizioni.
- Fonte `STATO.md`/commit `1debd53d`: piano RC aggiornato e gate riferito verde.
- Questi risultati sono dichiarati nel repository; il presente checkpoint non ha rilanciato le suite e non ha usato GitHub Actions.

## Branch, PR e SHA verificati

- `integration/brain-unico-20261119`: `1debd53d0a18e0cb3a8b9aad8879e32405ecee4d` — documentazione del piano, fix non incluso.
- `claude/tetto-posizioni-20261121`: `6eac67aa896d7115b7dd03fd5cb8fec703a1edc3` — fix isolato, da approvare.
- `diario` prima di questo checkpoint: `d732267e200ab00d3a8394a14fb1b5993203fac0`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- RC84 PR #80: **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`; test della PR non dichiarabili indipendentemente verdi.
- Issue #124: **open/P0**, ancora NO-GO per nuovi deploy Brain. Le soglie 35%/50% e floor 450 nell'issue appartengono alle run storiche; la nuova run B usa 3%/4% e 1.600, come chiarito nel piano RC.
- Backup candidato `claude/extbackup-storici-20261121`: `75a714be3976a732afa88a9aed3c6dc8c248e70f`.
- Ramo storico richiesto `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.

## Backup, chiavi e servizi

- Backup esterno: componenti separati, parti cifrate da 90 MiB e 74 test dichiarati; **non installato**, nessun primo invio off-host e nessun restore completo sul PC certificato.
- Copia cifrata della chiave age sul PC: PowerShell **`ESITO: VERIFICA OK`** e confronto della chiave pubblica coincidente. È prova locale; **non certifica** il backup o il ripristino sulla VPS.
- Nessuna chiave privata, passphrase, token o segreto è stata letta o salvata.
- Stato live VPS/servizi non controllato in questa esecuzione; non assumere che config, mandato, fix o backup siano installati.

## Eseguito, preparato, non approvato

**Eseguito/verificato**
- Lettura di GitHub, `STATO.md`, commit/branch, PR #80, Issue #124 e Library versione 145.
- Verifica delle decisioni recenti accessibili e riscontro sui commit.
- Identificazione del difetto di formattazione del checkpoint delle 22:51.

**Preparato ma non applicato**
- Configurazione profilo B e mandato `approved:false`.
- Piano Fase 1/Fase 2.
- Tetto esplicito di quattro posizioni su ramo isolato.
- Backup esterno per componenti.

**Non approvato/non eseguito**
- Merge del tetto nell'integrazione.
- Correzione contabile del rischio aperto.
- Approvazione mandato, creazione run, pre-collaudo, deploy, modifica servizi/VPS, training, API a pagamento o ordini.
- Installazione, invio off-host e restore certificato del backup.

## Blocker e prossime attività

1. Approvare o respingere il ramo del tetto dopo review; non dichiararlo implementato finché non entra nella RC.
2. Correggere e testare la parità del rischio aperto includendo i costi stimati.
3. Chiudere e verificare Issue #124 prima di qualsiasi deploy/avvio Brain.
4. Eseguire pre-collaudo del servizio uscite e rollback sul commit RC che include il tetto.
5. Verificare config completa e SHA-256; approvare mandato solo con consenso separato.
6. Completare backup con primo invio e restore PC prima del consenso al deploy.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e la sezione più recente di `ULTIMO-STATO-SUPERBOT.md`.
2. Ignorare i caratteri `+` iniziali del checkpoint storico delle 22:51: sono un artefatto di formattazione, non parte dei dati.
3. Verificare nuovamente gli HEAD remoti prima di agire.
4. Distinguere sempre: decisione, branch isolato, test dichiarato, integrazione, approvazione, deploy e stato live.
5. Mantenere PAPER-only e preservare Falco/Toro, storici ed EventJournal.

## Fonti consultate

- GitHub `alexiptv82/SuperBot-Trading`: ramo `diario`, `STATO.md`, commit `66989d8a`, `6eac67aa`, `1debd53d`, PR #80, Issue #124 e branch/SHA indicati.
- ChatGPT Library `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, versione 145 prima della scrittura.
- Conversazioni recenti effettivamente accessibili: decisione Fase 1 PAPER 72h, richiesta del tetto esplicito su ramo isolato e vincolo di non applicare/deployare senza consenso. Nessuna trascrizione di chat perse e nessuna inferenza sullo stato live VPS.

