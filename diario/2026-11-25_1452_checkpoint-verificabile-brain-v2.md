# Checkpoint verificabile SuperBot-Trading — 25/11/2026 14:52 Europe/Rome

## Esito sintetico

Rispetto al checkpoint persistente del 20/11 sono emerse novità sostanziali e verificabili. Il tetto di quattro posizioni e la contabilità del rischio aperto comprensiva dei costi sono stati integrati il 22/11; Issue #124 è stata corretta con test multiprocesso, integrata e chiusa. Nei giorni 23–25 sono stati installati e poi riorganizzati diversi componenti PAPER: Falco Evoluto è stato archiviato/disattivato nella nuova sessione, Brain Unico V2 è stato avviato su una nuova run da 2.000 USDT e la dashboard è stata aggiornata con esito osservato positivo. Il backup cifrato esterno è stato inviato e verificato da clone nuovo, ma il ripristino dei nuovi archivi sul PC e la copia Android restano incompleti. La Library era ancora alla versione 146 del 20/11: questa è una lacuna importante e motiva il doppio salvataggio.

Questo checkpoint è esclusivamente documentale. Non esegue codice operativo, merge, deploy, GitHub Actions, accessi o modifiche VPS, riavvii, reset, ordini o API a pagamento.

## Obiettivi e decisioni consolidate

- Trading esclusivamente PAPER; nessun LIVE.
- Storici ed EventJournal append-only da preservare; nessun reset o riscrittura.
- Tre patrimoni storici distinti: Falco, Toro, Brain.
- Falco/Toro classici restano conservati, semantic_not_certified, esclusi dal training automatico; nessuna nuova indagine sulla loro contabilità senza richiesta.
- Brain Unico/V2 resta la linea operativa prioritaria; NO_TRADE e slot vuoti sono validi.
- Nessun merge, deploy, reset o cambio rischio senza consenso specifico.
- Decisione recente accessibile ma esterna a questo repository: fondere in futuro Evolution ed Evolution X Lab in un Brain evoluto e mantenere un secondo bot autonomo PAPER da 2.000 USDT. È una roadmap su repository separato; al momento della verifica non risultavano file scritti né modifiche VPS per quella linea.

## Portafogli PAPER: desiderato vs stato verificato

| Portafoglio | Desiderato/decisione | Implementato o osservato | Limiti della prova |
|---|---|---|---|
| Falco | conservare l'asset storico SHORT e gli storici; nessuna distruzione | Falco/Toro classici conservati ed esclusi dal training; Falco Evoluto è stato installato PAPER il 23/11, poi archiviato/disattivato durante la nuova sessione Brain V2 | nessuna verifica SSH live in questo checkpoint |
| Toro | archivio storico da preservare; non parte della nuova linea operativa | dati storici conservati, semantic_not_certified; non compare tra i bot attuali della dashboard V2 | nessuna nuova certificazione semantica |
| Brain | nuova sessione PAPER da 2.000 USDT, DeepSeek principale e Claude revisore, memoria storica collegata | run brain-scalp-paper-p1, 27 strumenti, dieci slot, vecchia run archiviata con 539 eventi e tre sessioni collegate in sola lettura; dashboard V2 verificata il 25/11 | stato corrente dopo la prova delle 06:35 non ricontrollato direttamente |

## Rischio e configurazione: evoluzione verificata

1. Profilo B precedente (20–22/11): tetto esplicito di quattro posizioni e rischio aperto comprensivo dei costi integrati in integration/brain-unico-20261119 tramite c11e6d7d… e piano 302e94d2…; non più soltanto una proposta.
2. Issue #124: correzione della concorrenza multiprocesso 0f71d0be…, integrazione 5f110379…; Issue chiusa il 22/11. Il latch resta distinto dalle uscite: blocca nuove aperture, non il servizio delle chiusure.
3. Brain V2 successivo: il rilascio 6a96e599… documenta una configurazione diversa e più aggressiva, installata sulla nuova sessione: ciclo 30 minuti, leva dinamica 15–50×, margine massimo 400 USDT per trade, margine totale 55%, rischio per trade 4,3%, rischio aperto 12%, stop giornaliero 25%, universo 27 strumenti e dieci slot. DeepSeek ha confidenza minima 0,56; Claude mantiene il veto; fallback senza Claude a rischio dimezzato disattivato; LONG richiedono trend 1h+4h; costi/slippage proposti non oltre 30% di 1R.
4. Governance: la configurazione V2 risulta documentata come candidata/installata e nessun ulteriore cambio strategico è approvato dopo l'avvio. I valori del vecchio profilo B non vanno confusi con quelli della run V2 attuale; prima di qualunque ulteriore modifica va verificata la decisione proprietario che autorizza il profilo effettivamente in uso.

## Stato operativo e dashboard, con fonte e limiti

- Il 24/11 la nuova sessione Brain V2 è stata avviata; la vecchia run è stata archiviata. Non rilanciare --nuova-sessione.
- La prima installazione ha lasciato la web precedente; il primo pacchetto solo web d1bc0628… è stato rifiutato dalla sonda e ha eseguito rollback automatico senza fermare Brain.
- Diagnostica read-only del 25/11: divergenza fra tre chiusure nel riepilogo e un solo esito validato; due paper_reduce erano scartati per differenza di arrotondamento (produttore ROUND_DOWN, validatore HALF_EVEN).
- Correzione isolata work/brain-v2-web-counts-20261125 @ 6e305ed027e6aca132b0b3c1f27f42933ef902cd: paper_reduce verificato con ROUND_DOWN e paper_close con HALF_EVEN; record alterato continua a essere rifiutato.
- Installazione osservata della sola web il 25/11 alle 06:35: APP_PAPER_INSTALLATA_E_VERIFICATA, WEB_EXIT_CODE=0, dashboard confermata dall'utente come funzionante; runner, uscite e bridge non riavviati.
- Questa prova certifica l'aggiornamento web osservato, non lo stato live alle 14:52. Il runner installato potrebbe ancora scartare le due riduzioni parziali nel dataset/memoria: verifica ancora necessaria.

## Live Evolution e apprendimento

- claude/live-evolution-20261124 @ d1bc0628…; rilascio Brain 6a96e599….
- Le versioni di strategia sono registrate nel journal e fotografate sulle nuove posizioni; le posizioni vecchie mantengono le regole originarie. La prova simulata V2→V3 con posizione aperta è passata.
- La CLI superbot-strategia risulta installata col rilascio, ma la prova operativa completa V2→V3 sulla VPS resta da programmare senza chiusure forzate.
- Signal Lab è soltanto proposto come ramo/shadow advisory senza ordini: non implementato.
- La correzione degli esiti parziali è verificata per la web; l'uso corretto nel dataset/memoria del runner non è ancora certificato.

## Backup, chiavi e restore senza dati sensibili

- claude/extbackup-storici-20261121 @ 1588c95af8411b48616d73203d5d10211d38e246.
- Il 22/11 il proprietario ha eseguito il backup definitivo: componenti indispensabili e storici cifrati, inviati al repository privato dei backup e verificati da clone nuovo. Gli indispensabili risultano tecnicamente certificati; gli storici risultano integri, ma Falco/Toro restano non certificati semanticamente.
- Il ripristino dei nuovi archivi sul PC Windows non è ancora completato. La procedura Android/Termux e una copia aggiuntiva degli indispensabili sono preparate ma non eseguite.
- Ramo storico richiesto work/extbackup-bot-stopped-20261109 @ 3dc2116a08058f57fc14b695431f6e3fa1a1ca45: resta un artefatto storico preparato e non installato/certificato; è stato superato dalla linea extbackup del 21–22/11, ma va preservato.
- Copia cifrata della chiave age sul PC: PowerShell ESITO: VERIFICA OK e chiave pubblica derivata coincidente. È prova locale; non certifica presenza, backup o restore sulla VPS.
- Nessuna chiave privata, passphrase, token o segreto è stato letto o pubblicato.

## Branch, PR, issue e SHA verificati

- diario prima di questa scrittura: 14d183002b7e1efa8b8d68522786783df1e4a0eb.
- integration/brain-unico-20261119: f50f7ae40c78e7994f33d0dabf40f91d57d7873f.
- claude/tetto-posizioni-20261121: 887fc9616b5eedc2b4441357618fd5469ab5977d.
- claude/extbackup-storici-20261121: 1588c95af8411b48616d73203d5d10211d38e246.
- claude/live-evolution-20261124: d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd.
- work/brain-v2-web-counts-20261125: 6e305ed027e6aca132b0b3c1f27f42933ef902cd.
- claude/brain-unico-2000-20261124: c5d05f3f3a31e8b0cfe51949fa06fa4ec04c398b.
- claude/ingresso-unico-20261124: 612f6b4b868bb0828a23792f0f46e5946c7ddf6d.
- main: a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e.
- RC84 PR #80: open/draft, head 0e29a73a36f668643da4088178bacb8616a45ac0, ultimo aggiornamento 09/11; i test descritti nella PR restano dichiarati come non eseguiti indipendentemente.
- Issue #124: closed/completed il 22/11/2026; non va più descritta come P0 aperta.

## Test con fonte

- Tetto/rischio: ramo 887fc961…; integrazione approvata c11e6d7d… e piano 302e94d2….
- #124: correzione multiprocesso 0f71d0be…, quattro test dedicati (tre rossi sulla versione precedente) e suite V3 5.414 dichiarata; integrazione 5f110379….
- Brain V2 6a96e599…: gate DRY_RUN dichiarato verde — V3 5.588, Dataset Builder 158, Jest 212; ripartenza 13/13 e simulatore 2/2.
- App PAPER/integration f50f7ae4…: gate dichiarato V3 5.500 (1 saltato), Builder 158, Jest 210; controlli Android dichiarati 126/126.
- Correzione conteggi 6e305ed0…: test di regressione sul produttore reale e record alterato rifiutato; nessuna suite completa nuova è attribuita qui oltre alle evidenze del checkpoint del 25/11.
- I conteggi sono evidenze dichiarate nei commit/diario; questo checkpoint non ha rilanciato suite né GitHub Actions.

## Eseguito, preparato, non approvato

**Eseguito/verificato**

- Integrazione del tetto di quattro posizioni e rischio aperto con costi.
- Correzione, integrazione e chiusura di Issue #124.
- Backup esterno cifrato inviato e verificato da clone nuovo; restore PC ancora escluso.
- Installazioni PAPER del 23–25 documentate; nuova sessione Brain V2 avviata; dashboard aggiornata con esito osservato positivo.
- Vecchia run Brain archiviata; Falco Evoluto archiviato/disattivato nella nuova sessione.

**Preparato o parzialmente dimostrato**

- Live Evolution: implementato/installato, test simulato passato; test operativo completo ancora mancante.
- Correzione arrotondamento esiti parziali: pubblicata su ramo isolato e applicata alla sola web; runner/memoria da verificare.
- Copia Android/Termux e restore: preparati, non eseguiti.
- Signal Lab: proposta shadow, non implementata.
- Evolution X: accesso al repository separato verificato, nessun file scritto o deploy.

**Non approvato/non eseguito da questo checkpoint**

- Nuovi merge/deploy/cambi strategia, reset, riavvii, ordini, LIVE, API a pagamento.
- Nuova modifica del profilo rischio V2.
- Ripristino dei nuovi backup sul PC e certificazione Android.
- Nuova certificazione semantica di Falco/Toro.

## Blocker e prossime attività

1. Verificare in sola lettura se il runner/memoria installati acquisiscono correttamente i due paper_reduce; non fermare Brain per la sola UI.
2. Controllare lo stato operativo corrente senza mutazioni: heartbeat, posizioni, uscite, P&L, Telegram, costi AI, salvadanaio e contatori.
3. Non rilanciare --nuova-sessione; non usare il vecchio pacchetto web d1bc0628.
4. Eseguire più avanti un test controllato Live Evolution V2→V3 con posizione aperta e senza chiusura forzata.
5. Completare restore PC degli archivi definitivi e, con consenso separato, la prova Android/Termux.
6. Raccogliere un campione PAPER fuori dal 24/11 prima di cambiare filtri, veto o rischio.
7. Tenere separata la roadmap Evolution X dal repository e dalla run Brain V2 finché non esiste un piano approvato e verificabile.

## Istruzioni di ripresa per un'altra AI

1. Leggere STATO.md, questo checkpoint e la sezione più recente di ULTIMO-STATO-SUPERBOT.md.
2. Verificare nuovamente tutte le HEAD e lo stato di PR #80/Issue #124 prima di agire.
3. Usare 6a96e599… come riferimento del rilascio Brain V2, 6e305ed0… per la correzione conteggi e 14d18300… come ultimo checkpoint operativo prima di questa scrittura.
4. Riprendere dal controllo degli esiti parziali nel runner/memoria; non rifare dashboard, diagnosi BTC o nuova sessione.
5. Distinguere sempre evidenza GitHub, output Termius/screenshot riferito, installazione osservata e stato live corrente.
6. Preservare PAPER, storici ed EventJournal; nessun segreto pubblico, nessun reset e nessuna chiusura forzata.

## Fonti consultate

- GitHub alexiptv82/SuperBot-Trading: STATO.md, checkpoint del 25/11, branch/SHA indicati, PR #80 e Issue #124.
- ChatGPT Library /SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md, versione 146 prima della scrittura.
- Conversazioni recenti effettivamente accessibili dal 21 al 25/11; nessuna pretesa di trascrizioni perse e nessuna inferenza sullo stato live VPS oltre le prove documentate.

Checkpoint esclusivamente documentale; storici ed EventJournal preservati.

