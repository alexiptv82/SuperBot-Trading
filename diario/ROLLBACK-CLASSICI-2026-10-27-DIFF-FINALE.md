# AGGIORNAMENTO — rilasciato e verificato 27/10/2026, 20:02 Roma


## ROLLBACK CLASSICI + SALVADANAIO LIVE PAPER — 27/10, 20:02 Roma (19:02 UTC)
- OK deploy esplicito utente eseguito. Classici Hawk/Bull su3abf1f808b09bf9066d96a1d16f945d65601ba02, heartbeat3abf1f8, healthy/restart0/PAPER, istanza singola. Metodo5818 selettivo come diff approvato, anti-biasLONG/SHORT e bugfixmotore mantenuti, P1/regime/Guardianavanzato esclusi. CapitalV1off, policySalvadanaioonlyREADY.
- App su56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace, HTTP200, codiceserver/frontend/manifesto coerenti. Bundle frontend contiene Salvadanaio e reader reale installato restituisce available/ready per Hawk/Bull. App non ha DockerHEALTHCHECK: verificato HTTP, non inventare healthy.
- Deployclassici40564697020 SUCCESS18:58UTC; backupbots-20261027-185733-deploy + immagine superbot-desk:rollback-20261027-185733. Deployapp40565004065 SUCCESS19:01UTC; backupSQLite superbot-deploy-20261027-190057.db con restorePASS, superbot:prev e build.prev preservati.
- Postflight indipendente40565394446/job122405174661 SUCCESS19:02:12UTC: sorgenti sette moduli classici hashidentici al codice approvato, nuovi heartbeat/cicli riusciti; archivi protetti prefixhashidentici al preflight (append consentito), run_no/run_started_ms invariati, budgettotale non diminuito. Tutte le posizioni precedenti conservate:2Hawk/3Bull. Nessun reset o ricostruzione account; nessuna modifica manuale a memoria/storico/flag.
- Nuovo backupbots-20261027-190211-classici_vault_postflight: include salvadanaio-journal.jsonl (2righe ciascuno), hash/JSON/ripristinoPASS; vecchi journalV1 intatti (11Hawk/8Bull). Tradehistory279Hawk/152Bull, lessons45/54righe; learningcresce normalmente. errors.md assente prima non creato dal deploy. Nessun importo reale esposto.
- Tutti i container non coinvolti, inclusi Brain129547ed e legacy1f2edeb6, hanno stessoID/StartedAt del preflight: nessun riavvio o cambiamento. HI-TV mai contattato. Nessun ordine live.
- Salvadanaio: primaattivazione senza accreditare profitto passato fittizio. Eccedenza netta realizzata sopra1000 al rollover00:00UTC, residuo dopo perdite, nessun reintegro né prelievo dal vault. Pending distinto, nessuna chiusura forzata. Primo rollover live ancora da osservare: testofflinePASS non equivale a evento già avvenuto.
- Opsdi rilascio: guardiasorgente89misurata; backup riconosce journalSalvadanaio come critico/obbligatorio al postoV1quando policyvault-only.91testbackup/deployguard +1testselezionejournal/corruzionePASS; nessuna modifica aggiuntiva a strategia. Primo preflightfallito perverifiererrorsopzionale giàdocumentato, nessun restartcorrettivo.
- HEADrule-pool ora183fdb7b1bf25140d2d236c98e50262b5cd3411b (ultimi commit solo trigger/verifier), main56dc; differiscono dal codice botdistribuito3abf intenzionalmente. Trigger verifier disarmato phase=none approved=no [skipci], vecchi backup/immagini conservati. Riserva rilascio ChatGPT conclusa. Prossimo: osservare prima giornata/rollover senza modificare parametri; nuovi deploy richiedono nuovoOK.


---
## Documento di revisione conservato (precedente al deploy)

# Rollback selettivo classici — diff da approvare prima del deploy

Stato: codice preparato, nessun deploy. Solo PAPER. Autorizzazione operatore del 27 ottobre 2026.

## Basi e perimetro

- Metodo richiesto: `5818aee1e587f103d222510e761b30e02776ff15`.
- Questo ramo parte da `rule-pool` `d1701f22f2a615ac3ef05f96b9d1d3b297abf0bc`.
- Ultimo runtime classico verificato nella precedente indagine: `89b0dca3e259c548ed82754c2301c7b024d18ff5`. Non è stata effettuata una nuova ispezione del VPS in questa implementazione.
- Le run positive hanno attraversato più revisioni: la baseline richiesta non equivale a una ricostruzione di tutti i loro ingressi e non promette di ripeterne i risultati.
- Backup codice già presenti: `backup/classici-2026-10-27` e `backup/rule-pool-2026-10-27`. Non sostituiscono backup dei dati e immagini prima del futuro rilascio.

## Cambiamenti effettivi

| Area | Risultato preparato |
| --- | --- |
| Soglie esecutive | Tier A/B 60, C 70; scoring senza P1/bonus successivi |
| Slot e sizing | Hawk 10 slot, massimo 100 per trade; Bull 3 slot, massimo 350 per trade; formule fisse della baseline |
| Stop giornaliero | 12%; esclusa gestione Capital V1 a percentuali e stop 20% |
| Segnali | Pesi storici, niente regime BTC successivo, veto Bull aggregato o fallback P2 |
| Dati | Niente feed daily nativo aggiunto dopo la baseline; disponibilità minima 200 barre daily conservata per correttezza. Trend 4h su vere barre 4h, parità neutrale, RSI piatto neutrale |
| Macro e stagionalità | Logica originale ripristinata, incluso filtro macro attivo quando il calendario è disponibile e penalità +5 nella finestra 12h; non la successiva modalità osservazione |
| SL | Resta 1.2 ATR come nella baseline scelta; nessuna modifica opportunistica a 1.5 ATR |
| Motore e LONG | Conservati cursore barre, gestione barre chiuse e stop nella barra di ingresso, DCA senza allargare stop, stato posizioni moderno, score del proprio lato e metriche nette nel prompt |
| Chiusure | Conservate gestione protettiva e chiusure semplici/anticipate/parziali; Profit Guardian avanzato non importato né attivato |
| Brain adattivi | Nessuna modifica ai loro rami, container o dati; questi file riguardano i classici |
| Archivi operativi | Nessuna modifica a trade_history.jsonl, lessons.md, errors.md, learning_log.jsonl |

`engine.py` mantiene il motore corrente: unica variazione è il default stop giornaliero da 10% a 12%. Il prompt usa il metodo storico con le correzioni matematiche/LONG/DCA e i campi diagnostici corretti. Questo è un rollback selettivo, non un checkout integrale del vecchio motore.

## Salvadanaio

- Attivo automaticamente solo in PAPER. Il ramo rifiuta avvio in modalità live.
- Confine giorno UTC. Trasferisce solo eccedenza realizzata netta sopra 1000 operativi, senza generare denaro e senza prelevare dal saldo protetto.
- Decisione esplicita dell'operatore: dopo perdita si mantiene il residuo; nessun rabbocco. Un conto che passa da 900 a 950 resta a 950, senza accantonare 50.
- Fee già detratte dalla contabilità. Il Salvadanaio non sottrae fee una seconda volta.
- Non forza chiusure a mezzanotte; profitti non realizzati o capitale vincolato restano eventualmente in attesa, esclusi dal saldo protetto. Il trasferimento avviene solo quando finanziabile.
- Preserva posizioni, memoria e saldo già esistente. Prima attivazione senza ricostruire accantonamenti storici inesistenti.
- Registro accrediti per giorno UTC con giorno origine, timestamp e saldo dopo accredito. Nessuna funzione di reinvestimento o trasferimento manuale aggiunta.
- Stato e vault nello stesso snapshot atomico con journal `salvadanaio-journal.jsonl`, outbox append-only e recupero dopo crash. Vecchio `capital-v1-journal.jsonl` lasciato intatto, non usato come snapshot finanziario corrente.
- Gap di giorni, barre di confine mancanti o stato incoerente richiedono riconciliazione: niente ricostruzioni inventate. Gestione protettiva separata dal permesso di aumentare rischio.
- Primo avvio senza file inizializza il conto una volta; stato esistente vuoto/corrotto non viene ricreato automaticamente.

## Dashboard separata

Ramo `work/classici-salvadanaio-dashboard-20261027` basato su main `4cf41d23bb94f7a868b25dd1c89b3e4e8993d9a8`:

- Carta “Salvadanaio” separata per Hawk/Bull: saldo, accredito odierno UTC, storico ultimi 60 giorni di accredito, somme in attesa distinte, avvisi offline/non disponibile.
- P&L totale include il saldo protetto, equity/cash operativi restano distinti.
- Lettura del solo stato PAPER, nessun endpoint di scrittura o comando di trasferimento; reset bloccato quando il vault è presente.
- Per vedere e usare la funzione completa serviranno in futuro rilascio bot e app, entrambi da autorizzare. Non fondere main e rule-pool per ottenere questo diff.

## Verifiche

- 317 controlli bot e sicurezza rilascio: 138 base/macro/orari/journal, 49 rollback/correzioni, 86 adattatori simulati/rule pool, 44 guardie deploy.
- 43 test lettore app; 3 prove React SSR sul componente; bundling sintattico dell'intero grafo frontend con dipendenze esterne.
- Test CI del nuovo contratto aggiornati: gli assert delle successive policy dismesse non rappresentano il metodo approvato. Conservati test delle correzioni motore.
- GitHub Actions: build CRA completa, test React, 43 test reader, build immagine bot e import sanity superati. Anche suite bot/sicurezza superata (317 controlli). Nessun test invia ordini reali.
- CI verificata: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40558479403 e https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40558483663 .
- Workflow sui due rami di lavoro: solo test/build, nessun deploy automatico. Nessuna modifica ai trigger del deploy operativo.

## Condizione prima del rilascio

Attendere conferma separata dell'operatore sul diff finale. Prima del futuro deploy: ispezione runtime corrente, backup dati/immagini verificabile, gestione delle posizioni esistenti senza reset, coordinamento app/classici. Nessun deploy Brain adattivo o tocco ai dati classici è autorizzato da questo commit.


## Rollback classici: implementazione pronta, CI verde, NON DEPLOYATO
- Baseline approvata 5818aee; mantenute tutte le correzioni motore/LONG. Engine corrente conservato: solo default stop giornaliero torna al 12%. Guardian avanzato escluso dall'esecuzione.
- Ripristinati C70/A-B60, Bull3slot/Hawk10, sizing storico, macro originale attiva e stagionalità originale; rimossi dal percorso classico regime/P1/P2/veti e sizing percentuale successivi. SL resta1.2ATR come5818, feed daily successivo escluso ma correttezza dati mantenuta.
- Salvadanaio automatico solo PAPER: surplus netto sopra1000 al confine UTC, saldo separato e storico giornaliero visibili, pending distinto. Dopo perdita conserva residuo: nessun rabbocco/consumo vault, nessun reset o chiusura forzata. Prima attivazione senza inventare storico, posizioni/memoria conservate. Stato vuoto esistente rifiutato; prima installazione gestita. Journal separato salvadanaio-journal.jsonl con snapshot atomici e recupero crash; vecchio journal V1 non riscritto.
- Ramo bot work/classici-5818-vault-20261027: codice 08a8e6c644540b367adb6e052c5a6925a36a1e19; HEAD 27d2bf03fa2fba22f5021ec99f3c6720807d8583 (ultimo commit solo documentazione). Base d1701f2.
- Ramo app work/classici-salvadanaio-dashboard-20261027: codice e236d399e9c78ff9222bd817e59529a91f743e8f; HEAD 56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace (ultimo commit solo documentazione). Base main4cf41d2. Dashboard in sola lettura, saldo/accrediti/pending/ultimo aggiornamento; P&L include vault, operativo distinto. Storie main/rule-pool mantenute separate.
- Test GitHub: 187 base/rollback/correzioni/journal +71 adapter fake +15rulepool +44guardie deploy =317; immagine bot e import sanity verdi. App:43reader,3React, build CRA completa verde. Run CI: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40558479403 e https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40558483663 . Ultimi commit documentazione [skip ci], prodotto identico a quello testato.
- Diff bot: https://github.com/alexiptv82/SuperBot-Trading/compare/d1701f22f2a615ac3ef05f96b9d1d3b297abf0bc...27d2bf03fa2fba22f5021ec99f3c6720807d8583 ; diff app: https://github.com/alexiptv82/SuperBot-Trading/compare/4cf41d23bb94f7a868b25dd1c89b3e4e8993d9a8...56dc4bb62f64024d1ea7e5bc84602fbf52ea4ace . Dettaglio: diario/ROLLBACK-CLASSICI-2026-10-27-DIFF-FINALE.md.
- main4cf41d2/rule-poold1701f2 invariati verificati. Backup codice precedenti conservati; nessun deploy, trigger operativo, accesso/scrittura VPS, ordine o modifica agli archivi operativi. DESK_MODE resta PAPER. Nessun intervento ai Brain adattivi; nessun force push.
- Prenotazioni implementazione concluse: pronto per revisione operatore. Attesa conferma SEPARATA per futuro rilascio bot+app; backup dati/immagini e ispezione runtime attuale da fare prima del deploy. Nessun test garantisce risultati economici della baseline storica.
