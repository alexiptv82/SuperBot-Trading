+# Checkpoint verificabile SuperBot-Trading — 20/11/2026 22:51 Europe/Rome
+
+## Esito sintetico
+
+Dal checkpoint delle 21:44 è emersa una novità verificata: sul ramo `integration/brain-unico-20261119` è stata preparata, ma non attivata, la configurazione del profilo PAPER B insieme a un modello di mandato non approvato. Il ramo è poi avanzato con una correzione documentale importante: il mandato operativo corrente non è firmato e non prova l'identità dell'approvatore; il verificatore Ed25519 già presente è separato e non collegato al runner. Nessuna run, configurazione attiva, servizio, journal o VPS è stata modificata in questo checkpoint.
+
+## Obiettivi e perimetro
+
+- Solo trading **PAPER**; nessun ordine LIVE.
+- Conservare integralmente storici ed EventJournal; niente reset o cancellazioni.
+- Tre portafogli: **Falco**, **Toro**, **Brain**.
+- Brain Unico resta la priorità: rischio esplicito, memoria verificabile, dati attestati, uscite autonome, collaudo misurabile e rollback.
+- Questo checkpoint è solo documentazione. Nessun merge, deploy, GitHub Actions, accesso/modifica VPS, reboot, restart, reset, ordine o API a pagamento.
+
+## Portafogli PAPER
+
+| Portafoglio | Stato consolidato | Vincoli |
+|---|---|---|
+| Falco | Archivio storico integro; `semantic_not_certified` | Escluso da split, sufficienza e training; nessuna nuova indagine senza richiesta |
+| Toro | Archivio storico integro; `semantic_not_certified` | Escluso da split, sufficienza e training; anomalie storiche preservate, non corrette distruttivamente |
+| Brain | Primo PAPER da 2.000 USDT da preparare su run nuova | Profilo B scelto, ma config e mandato restano non applicati; Issue #124 è P0/NO-GO |
+
+## Profilo B: desiderato, preparato, implementato
+
+| Aspetto | Decisione/desiderio | Stato verificato |
+|---|---|---|
+| Rischio per trade | 1% / circa 20 USDT | Presente nel nuovo file di configurazione; è una stima allo stop, non un massimo garantito |
+| Posizioni/rischio aperto | max 4 posizioni; 4% rischio aperto | Rischio aperto 4% configurato; il limite “4 posizioni” resta requisito da verificare nel runtime/gate |
+| Giornata | avviso 3%; stop nuove aperture 4% | Configurato; non chiude posizioni già aperte e non garantisce perdita giornaliera massima |
+| Equity floor | 1.600 USDT | Configurato come blocco nuove aperture; non garantisce che l'equity non scenda sotto |
+| Leva | 1–30× | Configurata; il motore può ridurla per sicurezza, non alzarla |
+| Margini | max 20% per posizione; 50% totale | Configurato |
+| Approvazione proprietario | Approvazione esplicita; preferenza per prova crittografica owner-only con chiave privata fuori Brain/repo/VPS e validità massima 24h | **Non implementata nel runner**: il template operativo è un file non firmato con `approved:false`; chi può scrivere la cartella run potrebbe approvarlo. Il verificatore Ed25519 separato esiste, ma non è cablato al runner |
+| Integrità configurazione | Tutti i parametri del profilo devono essere vincolati/verificati | Il `policy_hash` copre i limiti di rischio/leva, ma non limite giornaliero, simboli, modello, ciclo o budget; la documentazione richiede quindi controllo manuale SHA-256 dell'intera config prima di qualunque attivazione |
+
+## Novità verificate
+
+- `integration/brain-unico-20261119` @ `45b95ff828203703a2104f59667961b3698522b0`:
+  - aggiunti `runner_config_brain_unico_paper_b.json` e `mandate_brain_unico_paper_b.TEMPLATE.json`;
+  - template legato alla run `brain-unico-paper-rc1`, `approved:false`, `policy_hash ba5c074ec2ecfe34`;
+  - configurazioni esistenti lasciate invariate;
+  - documento di revisione e 5 test mirati aggiunti;
+  - nessun parametro applicato, nessun deploy o servizio toccato.
+- Il ramo di integrazione è poi avanzato a `f50baf89be1e1c8a2e4128f1bd054ec58b8fdde2`:
+  - sola correzione documentale;
+  - chiarito che il mandato operativo non è firmato e prova coerenza, non identità;
+  - chiarito che l'Ed25519 con durata massima 24h è un sistema separato, non usato dal runner;
+  - aggiunto il requisito di verificare l'impronta completa della configurazione prima dell'attivazione.
+- Il ramo `diario` aveva già indicizzato `45b95ff8` nel commit `7138d85dced7a544874198b9ed6b5a50aba4a48b`, ma non la successiva precisazione `f50baf8`: questa lacuna è il motivo del presente checkpoint.
+
+## Test ed evidenze
+
+- Fonte `45b95ff8`: commit dichiara **5 test** nuovi per valori esatti del profilo, differenze rispetto alla config 2.000 precedente, template non approvato/policy hash, accettazione-rifiuto del mandato e perdita stimata di 20 USDT.
+- Fonte `STATO.md` del ramo `diario`: gate riferito per `45b95ff8` = **V3 5.393, Dataset Builder 158, Jest 153**.
+- `f50baf8` modifica soltanto la documentazione; non dichiara una nuova esecuzione completa dei test.
+- Questo checkpoint non ha rilanciato le suite né usato GitHub Actions: i conteggi sopra sono evidenze dichiarate nel repository, non una nuova certificazione indipendente.
+
+## RC84, branch e SHA verificati
+
+- `diario` prima di questo checkpoint: `7138d85dced7a544874198b9ed6b5a50aba4a48b`.
+- `integration/brain-unico-20261119`: `f50baf89be1e1c8a2e4128f1bd054ec58b8fdde2`.
+- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
+- RC84 PR #80: **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`; nessun merge.
+- Issue #124: **open/P0**; resta NO-GO per nuovi deploy Brain finché il latch della perdita giornaliera non è chiuso e verificato.
+- Candidato backup esterno: `claude/extbackup-storici-20261121` @ `75a714be3976a732afa88a9aed3c6dc8c248e70f`.
+- Ramo storico richiesto: `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
+
+## Backup, chiavi e servizi
+
+- Backup esterno: preparato per componenti separati, parti cifrate da 90 MiB e 74 test dichiarati; **non installato**, nessun primo invio off-host e nessun restore completo sul PC certificato.
+- Copia cifrata della chiave age sul PC: verifica PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica coincidente. È prova locale della copia cifrata; **non certifica** la copia, l'installazione o il ripristino del backup sulla VPS.
+- Nessuna chiave privata, passphrase, token o segreto è stata letta o registrata.
+- Stato live dei servizi/VPS non controllato in questa esecuzione: non inferire che configurazioni preparate, backup o mandati siano presenti o attivi sulla VPS.
+
+## Eseguito, preparato, non approvato
+
+**Eseguito/verificato**
+- Lettura di GitHub, `STATO.md`, checkpoint recenti, PR #80, Issue #124 e SHA dei rami.
+- Lettura della copia Library versione 144.
+- Verifica dei nuovi file e delle differenze dei commit `45b95ff8` e `f50baf8`.
+
+**Preparato ma non applicato**
+- Configurazione profilo B per una nuova run Brain PAPER.
+- Template di mandato `approved:false`.
+- Procedura documentale per il controllo dell'impronta completa.
+- Backup esterno per componenti.
+
+**Non approvato/non eseguito**
+- Nessuna approvazione del mandato, creazione della run, attivazione config, deploy, merge, prova VPS, training, chiamata AI a pagamento o ordine.
+- Nessun cablaggio del verificatore Ed25519 nel runner.
+- Nessuna installazione o prova off-host del backup.
+
+## Blocker e prossime attività
+
+1. Risolvere e verificare Issue #124 prima di qualsiasi nuovo deploy/avvio Brain.
+2. Decidere esplicitamente se il primo PAPER può usare il mandato operativo non firmato oppure richiede cablaggio Ed25519; non confondere i due meccanismi.
+3. Verificare che il requisito “max 4 posizioni” sia realmente imposto, non soltanto dedotto dal 4% di rischio aperto.
+4. Riesaminare la config completa e il suo SHA-256; poi approvare il mandato solo con consenso separato.
+5. Completare prova finale RC, backup esterno con primo invio e restore PC, pre-collaudo e consenso al deploy; nessuna di queste attività è autorizzata da questo checkpoint.
+
+## Istruzioni di ripresa
+
+1. Leggere per primi `STATO.md` sul ramo `diario`, questo checkpoint e la sezione più recente di `ULTIMO-STATO-SUPERBOT.md`.
+2. Verificare nuovamente gli HEAD remoti: non assumere che gli SHA qui riportati siano ancora correnti.
+3. Trattare `f50baf8` come ultimo stato documentale verificato dell'integrazione in questo checkpoint.
+4. Distinguere sempre **decisione**, **file preparato**, **implementazione cablata**, **approvazione**, **deploy** e **stato live verificato**.
+5. Mantenere PAPER-only; preservare Falco/Toro, storici ed EventJournal; non esporre segreti.
+
+## Fonti consultate
+
+- GitHub `alexiptv82/SuperBot-Trading`: ramo `diario`, `STATO.md`, commit e file dei rami indicati, PR #80 e Issue #124.
+- ChatGPT Library `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, versione 144 prima della scrittura.
+- Conversazioni recenti: accessibilità limitata; nessuna trascrizione integrale di chat perse. Le sole informazioni utili recuperate confermavano la scelta del profilo B e lo stato non applicato; le novità tecniche sono state accettate solo dopo verifica su GitHub.
+
