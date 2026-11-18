# Checkpoint verificabile — SuperBot-Trading

**Data:** 18/11/2026, 13:53 Europe/Rome  
**Ambito:** sola documentazione; PAPER; nessun merge, deploy, GitHub Actions, modifica VPS, riavvio, reset, ordine, wallet o chiamata API a pagamento.

## Sintesi di ripresa

Dal checkpoint del 14/11 sono emerse novità sostanziali e verificabili. Il progetto ha spostato il lavoro futuro dai tre portafogli storici Falco/Toro/Brain a una **AI Arena PAPER** dentro l'architettura Brain, con tre corsie indipendenti **DeepSeek, Qwen e MiniMax**. Falco e Toro sono stati ritirati/archiviati come portafogli operativi futuri; la strategia SHORT di Falco e tutti gli storici/EventJournal devono restare conservati e recuperabili. Il Brain storico non va confuso con le tre nuove corsie e non va interrotto dai lavori Arena.

La gara autorizzata è un primo screening PAPER di **72 ore contigue**, 27 mercati comuni, stessa baseline DeepSeek e stessa policy di rischio/esecuzione per tutte le AI. Budget desiderato: 2 USD/giorno e 6 USD cumulativi per provider, 18 USD totali. Non è ancora iniziata: T0 assente, mandati non approvati e runner decisionali Arena inattivi. Il limite interno DeepSeek riduce il rischio ma non costituisce un tetto matematico lato fornitore; il saldo account è condiviso con il Brain storico e non deve essere ridotto automaticamente.

## Portafogli e decisioni utente

- **Falco storico:** PAPER, specializzazione SHORT da preservare integralmente; ritirato/archiviato, non cancellato. Nessuna autorizzazione a modificare la logica SHORT o gli storici.
- **Toro storico:** PAPER, ritirato/archiviato. Le precedenti proposte LONG e Fable restano ricerca/staging non promossa; la direzione corrente non è riattivare Toro ma confrontare tre AI sulla medesima baseline.
- **Brain storico:** PAPER secondo le ultime prove disponibili; resta separato e, secondo gli screenshot riportati nei commenti GitHub del 18/11, runner ed exit risultavano attivi. Questo checkpoint non ha accesso SSH e non certifica lo stato live corrente.
- **AI Arena futura:** tre portafogli PAPER indipendenti DeepSeek/Qwen/MiniMax, 2.000 USDT nominali ciascuno nelle run preparate, 27 mercati, memoria indipendente durante la gara. L'app unica SuperBot deve mostrare tre card, posizioni, PnL e storico, lasciando Falco/Toro separati e recuperabili.
- **Chiusura manuale e apprendimento:** il codice prepara una chiusura PAPER per AI con motivo umano append-only e idempotenza; l'esito deve entrare nell'evidenza di apprendimento senza perdere trade. La memoria condivisa/finale che impara dai tre portafogli e dalle chiusure umane non è ancora dimostrata operativa. La gara non deve contaminare reciprocamente le memorie delle tre corsie.
- **Precondizioni utente recenti:** non avviare la gara prima di risolvere i problemi di gestione emersi dal report sui trainer; al termine delle 72 ore valutare dati, costi e qualità prima di qualsiasi estensione. L'esperimento LLM locale e la ricerca Time Machine sono post-T0 e non devono ritardare né alterare la gara.

## GitHub verificato

- Ramo `diario` prima di questo checkpoint: `937b9ec39d7d4e717dc010c716e1d64fd1cda8ed`, fermo al 14/11.
- PR draft [#102](https://github.com/alexiptv82/SuperBot-Trading/pull/102), `work/arena-paper-runners-manual-close-20261117` a `48dc07494345fe9d973b900b67cd094cec56e7e5`: runner PAPER, chiusura manuale per AI, journal e motivazioni append-only; non deploy.
- PR draft [#106](https://github.com/alexiptv82/SuperBot-Trading/pull/106), `work/arena-vps-stage-paused-only-20261117` a `95c554b65521efaef1eedb8f35326e6d18cc34f9`: stage conservativo; nessun T0 o avvio.
- PR draft [#107](https://github.com/alexiptv82/SuperBot-Trading/pull/107), `work/arena-prepare-paused-runs-20261118` a `731b836c5e74f3709187370ef4e59ed4d71ef583`: preparazione delle tre run in pausa, T0 separato, budget gate e backup a caldo.
- PR draft [#108](https://github.com/alexiptv82/SuperBot-Trading/pull/108), ricerca Brain/Profit Guardian a `c03919d52020bcd9cb14e305a75995f46fd2cab2`: replay e proposta di freni rischio; **non applicata**. L'utente ha deciso di mantenere per la gara la baseline DeepSeek e la stessa policy per tutte le AI.
- PR draft [#109](https://github.com/alexiptv82/SuperBot-Trading/pull/109), prezzi Qwen/MiniMax a `06562c4a0281560ab231ee9d86d26ffd2a9847ea`; base della successiva PR #110.
- PR draft [#110](https://github.com/alexiptv82/SuperBot-Trading/pull/110), `work/arena-72h-18usd-budget-20261118`, HEAD verificato `3dd6aa588339c6136d52e9ff027c91e5e3f80377`: hard stop nuove inferenze/aperture a T0+72h, prenotazione budget fail-closed, correzione feed candele chiuse, sostituzione auditabile delle run preparate, recovery persistente dopo SIGKILL/disconnessione e sonda read-only web→bridge. Nessun deploy/T0.
- Issue [#111](https://github.com/alexiptv82/SuperBot-Trading/issues/111): Sequence Analyzer e Brain Time Machine esclusivamente ricerca SHADOW post-Arena; nessuna modifica alla gara.
- Riferimenti storici invariati: PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) RC84 HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`; backup esterno preparato su `work/extbackup-bot-stopped-20261109` HEAD `3dc2116…`, non installato.

## Test e riscontri, con fonte

- Commento PR #110 del 18/11, HEAD `3dd6aa…`: **1.028 test locali superati** per Arena/runner/uscite/budget/feed/preparazione/cutover; `test_prepare_script.py` 14 PASS; 2 fallimenti `test_v3_cutover_gate` dichiarati identici al ramo base. Nessuna GitHub Action. Il checkpoint verifica la presenza del commento e del commit, non rilancia i test.
- Sul precedente HEAD `6c779e…` erano riportati frontend **23 suite / 175 test PASS** e smoke mock senza crediti su feed Bitget reale: 27/27 decisioni per ciascuna AI, 0 errori e 0 aperture. Una revisione ChatGPT ha letto i file ma non ha rilanciato le suite; il difetto rollback successivamente trovato è stato corretto e testato nel nuovo HEAD.
- La correzione feed completa lo storico con sole candele già chiuse da `candles`; senza il fix il test reale aveva mostrato `data_unavailable` su 27/27 simboli. Non prova redditività.
- PR #108: 12 test ricerca e replay su ingressi di controllo; risultati non giustificano l'applicazione automatica di trailing/BE o riduzione size alla gara. Manca l'export degli ingressi reali del Brain.

## Stato VPS/backup/app — prove puntuali, non stato live continuo

- Commenti GitHub derivati da screenshot Termius dell'utente: alle 09:36 Europe/Rome tre run risultavano `PREPARED_PAUSED_NO_T0`, un solo evento `run_prepared` ciascuna, journal integri, zero posizioni, mandati non approvati, T0 assente, tre exit-worker sani; backup a caldo locale verificato in `/opt/superbot-v3-backups/arena-20261118T083627Z`. È backup sulla stessa VPS, non copia esterna cifrata.
- Alle 12:25 un `--inspect` read-only ha confermato Qwen nello stato preparato; il ritaglio non mostrava tutti i campi DeepSeek/MiniMax e non va esteso oltre ciò che è visibile.
- Alle 13:42 la sonda reale del container web ha dato **`CHANNEL_NOT_OK`**: bridge host attivo e socket host presente, ma socket Arena non montato nel container e flag Arena assenti. Quindi GET Arena/chiusura manuale Samsung end-to-end **non sono certificati**. Nessuna ricreazione del container è approvata; prima serve inventario read-only e rollback completo della configurazione web/login.
- Le tre run VPS esistenti hanno config/hash precedenti a #110. Non modificare i file in place. Il wrapper corretto `--replace-prepared`/`--recover-replace` è solo codice testato localmente; non risulta eseguito sulla VPS.
- Verifica PC della copia cifrata della chiave age: output PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica coincidente. Prova la copia cifrata sul PC, **non** certifica il backup su VPS e non autorizza a leggere/esporre segreti.
- Backup esterno storico: preparato sul ramo dedicato, non installato. Nessuna prova di copia esterna Arena nuova.

## Fatto / preparato / rilasciato

- **Fatto e verificato documentalmente:** decisione gara 72h/27 mercati/PAPER; ritiro conservativo Falco/Toro; PR/branch/SHA sopra; test riportati nei commenti GitHub; backup locale e probe `CHANNEL_NOT_OK` come evidenza screenshot; age PC `ESITO: VERIFICA OK`.
- **Preparato, non rilasciato:** runner/uscite/backup/manual close Arena, sostituzione run con recovery, budget guard, dashboard 3 giorni, bridge probe, ricerca Brain e Time Machine.
- **Rilasciato/attivo:** nessuna nuova release da questo checkpoint. T0 non assegnato, decisori Arena inattivi, nessuna inferenza/spesa Arena o ordine LIVE attestato.
- **Non approvato:** merge/deploy, ricreazione container web, sostituzione run VPS, T0, modifica saldo DeepSeek condiviso, nuova strategia/risk policy, estensione oltre 72h, memoria finale automatica, backup esterno.

## Blocker e prossimo passo

1. Inventario **sola lettura** del container/web manager e rollback completo, senza stampare env/segreti; progettare mount minimo del socket Arena e journal RO senza rompere login Samsung o bridge storico.
2. Verificare il canale web→bridge e GET autenticato su ambiente sintetico; fino ad allora manual close Samsung non operativo e fallback documentale resta pausa via Termius.
3. Prima di qualunque sostituzione run, nuova revisione del pin `3dd6aa…`; se approvata in futuro, eseguire solo con unità transient/tmux, backup intatto e recovery idempotente. Questo checkpoint non la autorizza.
4. Verificare limiti/credito provider senza esporre segreti e senza ridurre il saldo condiviso DeepSeek; trattare 18 USD come massimo desiderato, non garanzia assoluta lato fornitore.
5. Risolvere i rilievi di gestione/trainer richiesti dall'utente; poi preflight finale su 27 mercati, uscite, journal, backup, T0 comune e budget. Solo con nuova autorizzazione separata avviare la gara PAPER.
6. Dopo 72 ore: fermare nuove inferenze/aperture automaticamente, lasciare le uscite attive fino a flat, valutare PnL netto, drawdown, uptime, NO_TRADE, coverage, costi, correlazione e sequenze di riapertura. Nessuna estensione automatica.

## Istruzioni di ripresa

Leggere nell'ordine `diario/STATO.md`, questo checkpoint, PR #110 e i suoi commenti più recenti, quindi Issue #111. Confrontare sempre HEAD corrente con `3dd6aa…`; non promuovere commenti/screenshot a stato live senza nuovo controllo. Preservare PAPER, Falco SHORT, archivi Falco/Toro, tutti i journal/memorie, backup e hash. Non leggere o pubblicare chiavi, token, passphrase o dettagli d'accesso VPS.

## Limiti delle fonti

Conversazioni recenti accessibili solo come estratti/riassunti indicizzati, non trascrizioni integrali e non recupero di chat eliminate. GitHub e Library sono stati letti direttamente. Le prove VPS sono screenshot/risultati riportati dall'utente nei commenti GitHub; nessun accesso SSH live in questa esecuzione.
