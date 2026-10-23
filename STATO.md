## Aggiornamento 22/10/2026 — ChatGPT: analisi step 4 preparata, in attesa di revisione

- Ramo `work/director-chatgpt` HEAD `ed3c65c`: aggiunti `deploy/scripts/regime_trade_analysis.py`, workflow `desk-regime-trades.yml` e 7 test sintetici. Il ramo non contiene un trigger attivo.
- Regole di calcolo: chiave `(bot, run_no, id)`; una sola apertura; trade incluso solo con una chiusura finale; `net_r` additivo sommato su tutte le chiusure, parziali incluse; lato e BTC `roc24h` presi dall'evento di apertura. Down <−1%, up >+1%, flat negli altri casi. Report aggregato stratificato anche per run e versione.
- Il report non stampa simboli, ID, prezzi o PnL in dollari. Il workflow previsto è usa-e-getta, rete disabilitata nel container, volume dati `:ro`, snapshot SHA-256 e controllo che ID/immagine/start-time dei container Hawk/Bull non cambino durante la misura.
- Verifiche locali: `py_compile`, YAML parse e 7 test manuali passati con Python 3.12.14. `pytest` e Python 3.11 non sono disponibili in questo ambiente. Nessuna esecuzione sul server e nessun merge del workflow.
- **Gate prima del merge:** revisione di Claude, poiché il workflow accede al VPS; poi attivazione esplicita del trigger di sola lettura e controllo che i due bot non siano stati riavviati.

## Aggiornamento 22/10/2026 — ChatGPT: step 3 attivato, incompatibilità dello schema rilevata

- Merge manifest in `rule-pool`: `0cc1f035`; trigger aggiornato al commit `8b0fcaa`. Nessun deploy dei bot.
- Workflow `desk-manifest` run `39719909269` completato. Hash dei registri verificati: Hawk `87b7e871…ef443c7` (2.483 righe), Bull `d273b2e4…d1ac261` (3.107 righe); JSON invalidi 0.
- Il parser si aspetta record di trade (`symbol`, `side`, `entry_ts`, `exit_ts`, `net`, `gross`, `fees`), ma `learning_log.jsonl` è un registro di eventi (`ev=open/close/candidate`, dati annidati in `features`, `net_r` sulle chiusure). Risultato: righe valide 0; il workflow ha comunque stampato “MANIFESTO OK” perché considera fatale solo il file mancante. Gli hash attestano i byte letti, non la validità semantica.
- Step 4 (R per regime e lato) non ancora calcolato. Serve parser event-aware che unisca `open`/`close` per `(bot, run_no, id)`, sommi `net_r` delle chiusure e classifichi il regime usando solo dati d’ingresso. La classificazione disponibile nel log è BTC `roc24h` (<−1% down, >+1% up, altrimenti flat), quindi va etichettata come proxy BTC; la mediana cross-section dei 26 simboli non è direttamente registrata come singola feature.
- Workflow di sola lettura: Hawk e Bull risultavano in esecuzione senza riavvii osservati. Nessuna strategia, database o stato dei bot modificati.
- Rami: `rule-pool` `8b0fcaa`; `work/director-claude` `40157c3`; `work/director-chatgpt` `9255093`; questo aggiornamento documenta il limite emerso.

# STATO SuperBot — aggiornato 2026-10-22 sera (Claude)

## Ultima azione
**Commit `40157c3`** su `work/director-claude`:
- Step 3 ricerca: `learning_log_manifest.py` + workflow `desk-manifest.yml` + 11 test
- Nessun dato grezzo nel repo pubblico; solo sha256 + conteggi

## Deploy attivo (rule-pool HEAD: 7a5e795 / merge PR #1 stagionalità)
- `4eaaf67` — daily_stop 12% → 10% (Hawk + Bull) ← **nuovo**, riavvio gestito da desk-deploy.yml
- `880c4a4` — fix barre 1d (pause/retry 429, serie ieri come riserva)
- `eab355d` — 4 fix integrità replay (snapshot, tolleranza 0.05$, MFE upper bound, exit code reale)
- DESK_MODE: paper (invariato)
- Nessun bot riavviato manualmente da Claude/ChatGPT: gestito da desk-deploy.yml

## Rami
- `work/director-claude` HEAD: `40157c3` (Claude, non unire senza OK)
- `work/director-chatgpt` HEAD: `4c1645e3` (Step 6 corretto, piano draft; attende review Claude, non unito)
- `work/research-integrity` HEAD: `b229963` (ChatGPT, non unire)
- `rule-pool` HEAD: `8efc0a9` (audit profitto read-only unito e trigger eseguito; nessun nuovo deploy bot)

## Sequenza ricerca (ChatGPT → Claude)
- [x] 1. Review codice — fatto
- [x] 2. Integrità: complete_window, snapshot, RECON_TOL 0.05$, MFE upper bound, exit code — fatto (commit eab355d)
- [x] 3. Manifesto/hash learning_log (sola lettura, nessun dato grezzo) — fatto (commit 40157c3)
- [x] 4. R per regime BTC proxy e lato — Actions run 39741314265; risultati/limiti nel diario ChatGPT
- [x] 5. Stagionalità A/B su score only — Actions run 39752709258; BOT_CONTAINER_INVARIANCE=PASS; risultati nel diario Claude 22/10
- [ ] 6. Replay economico + validazione out-of-sample → raccomandazione all'utente

## Manifesto e step 4
- Manifesto `learning_log` attivato in sola lettura; schema event-aware verificato nel lavoro dello step 4.
- Misura step 4 completata in Actions run `39741314265`; non riavvia i bot. Risultati e limiti in `diario/2026-10-22_chatgpt.md`.
- Prossimi: step 5 stagionalità A/B in sola lettura; step 6 replay economico e validazione fuori campione.


## Step 5 stagionalità A/B — risultati (Actions run 39752709258)
- BOT_CONTAINER_INVARIANCE=PASS (ID/immagine/StartedAt Hawk e Bull invariati prima/dopo le 4 analisi)
- Soglia 60: Hawk unique=1078, eligible_A=1078, eligible_B=798, changed=280, side_changed=0; Bull unique=1365, eligible_A=1365, eligible_B=1058, changed=307, side_changed=0
- Soglia 63: Hawk eligible_A=686, eligible_B=519, changed=167, side_changed=0; Bull eligible_A=893, eligible_B=677, changed=216, side_changed=0
- side_changed=0 in tutti e 4 i casi: il bonus stagionale non inverte mai la direzione di selezione (long/short)
- Riduzione eligibilità ~22-26% a soglia 60, ~24% a soglia 63 rimuovendo il bonus stagionale (formula B)
- Hawk log sha256: `b14dc35aae8fa64fd1865c4a535888c03e56efb1dcedbaa6fbfbecdcaa466c26`; Bull: `10fa7558abe79195f53fe3f68868f5f063c878d164f691ab8cf37fd605bd9cbb`
- seasonal_sha256: `47c12da1abbe51be0c826fc03b7609af40407e2e101911ded3444def5d6912c7` (identico 4 run)
- ~50% delle righe (recorded) escluse per code_version non revisionata (excluded_unreviewed)
- Nessun dato grezzo pubblicato; nessun bot modificato o riavviato
## Regole inviolabili (sempre valide)
1. Nessun redeploy senza OK esplicito utente
2. DESK_MODE=paper finché utente non dice live
3. Nessuna modifica a strategia/soglie/prompt senza decisione utente
4. Il "cervello" (trade_history, lessons, errors, learning_log) non si cancella/azzera
5. API key solo nei GitHub Secrets
6. Mai toccare HI-TV/hitvprime (Strasburgo)
7. Repo pubblico: nessun segreto, nessun importo/saldo reale
8. Mai git push --force; non unire work/backend-singapore-audit; no push su stable/* e v0.5
9. Un solo autore alla volta per componente


## Aggiornamento 22/10/2026 — step 4 avviato, output Actions da recuperare

- Review Claude di `work/director-chatgpt` `ed3c65c` recepita: newline finale esplicitamente testato; `sys` e `all_trades` inutilizzati rimossi. 8 test manuali e `py_compile` passati.
- In `rule-pool`: analisi read-only (script `3c5853e`, test `27062d6`, workflow `a589635`); trigger dedicato in `595c032` che fissa il codice allo SHA `3c5853e`. Nessun trigger/deploy dei bot modificato.
- L'esecuzione di step 4 è stata attivata, ma il connettore GitHub qui non espone le run Actions da push né il loro riepilogo. Conteggi, hash letti e controllo d'invarianza dei container restano da confermare dall'output Actions/run ID. Non considerare ancora completata la misura.
- Diario dettagliato: `diario/2026-10-22_chatgpt.md` (commit `a7ab54b`).

## Aggiornamento 22/10/2026 — step 4 misurato (Actions run 39741314265)

- Workflow read-only concluso con success. SHA codice verificato: 3c5853e2f7463957199e4dc524395ebb24aa0a09. Controllo prima/dopo container Hawk/Bull passato: nessun cambio ID/immagine/StartedAt.
- Hawk: 130 trade eleggibili, 11 giorni, media +0,10594 R, IC bootstrap per giorno UTC 95% [−0,56208; +0,71016]. Bull: 36 trade, 11 giorni, +0,00500 R, IC [−0,50208; +0,56903]. Intervalli entrambi includono zero.
- Report regime/lato e limiti completi in diario/2026-10-22_chatgpt.md. La stratificazione per run/versione non è recuperabile dal log, troncato da GitHub; niente conclusioni per-run da questo output.
- Nessuna modifica o riavvio dei bot. Nessun dato grezzo pubblicato.

## Aggiornamento 22/10/2026 — step 5 preparato
- PR #1 `work/seasonality-audit`: https://github.com/alexiptv82/SuperBot-Trading/pull/1
- CI test Python 3.11: success (Actions run 39747560290); test locale 12/12 e YAML workflow validati.
- Workflow dedicato è sola lettura, esegue cutoffs tecnici 60/63 per descrivere l'effetto sul punteggio. Non equivale alla confidenza Claude e non misura redditività.
- Nessun merge o run sul VPS. Attende review Claude sul workflow server-side; dopo il merge il trigger dedicato eseguirà il report aggregato.
- Diario dettagliato: `diario/2026-10-22_chatgpt.md` (commit 142cc297).


## Aggiornamento 22/10/2026 — step 5 unito, run Actions da verificare
- PR #1 stagionalità A/B unita in `rule-pool`: merge commit `7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e`; CI head `39747560290` success.
- Review Claude positiva; nota non bloccante: aggiornare `--reviewed-code-version` alle future versioni bot prima di includerle nell'analisi.
- Il report sul VPS e l'invarianza dei container restano da attestare: il connettore disponibile non mostra le run Actions avviate da push.
## Aggiornamento 22/10/2026 — step 5 COMPLETATO (Claude — sera)

- Review Claude PR #1 positiva: splitlines(), PAPER verificato a livello Docker, tripla sha256, scope attestato, 4 container --network none --read-only, invarianza bot verificata.
- Merge PR #1 in rule-pool commit 7a5e795; CI 12/12 test success (run 39747560290).
- Analisi stagionale A/B (Actions run 39752709258): BOT_CONTAINER_INVARIANCE=PASS; side_changed=0; riduzione eligibilità ~22-26%. Dettagli in diario/2026-10-22_claude.md.
- Prossimo: step 6 replay economico + validazione out-of-sample (decisione utente).


## 22/10/2026 — Step 6 in preparazione (ChatGPT)

L'utente autorizza preparazione e push sul ramo work/director-chatgpt di script, workflow e test per replay economico e protocollo prospettico. Nessun merge, trigger o accesso VPS autorizzato in questa fase; review Claude prima dell'esecuzione. Componente step 6 assegnato a ChatGPT.

Il replay sara' offline con OHLC locale verificato: il runner precedente usa rete e non puo' essere eseguito nel container --network none richiesto. Piano e soglie saranno una proposta draft; nessuna modifica ai bot. Ramo realmente letto: work/director-chatgpt 11a9c62 (il riferimento 9255093 nel prompt e' superato).


## 22/10/2026 — Step 6 preparato, attende review Claude

- Codice su work/director-chatgpt: fe50c2ff2f459e4260d7f2f4907ad0f7c590a478. Sei file nuovi; nessuna modifica al motore o ai trigger dei bot. work/director-claude non toccato.
- Proposta dettagliata: deploy/STEP6-REVIEW.md. Script autonomo offline, workflow VPS isolato, CI sintetica, test e piano draft.
- Ipotesi proposta: parziale 50% dopo chiusura a +1,5R, eseguito al next-open; residuo protetto con segnale a barra chiusa. Non equivale al vecchio limite intrabar e non e' un replay di portafoglio o della stagionalita' economica.
- Verifiche locali: Python 3.12.14, 19 test passati, py_compile, YAML e bash -n passati. Test shell reale con git/docker simulati: errore analisi propagato e riavvio container rilevato. CI Python 3.11 predisposta ma non eseguita.
- Stato di esecuzione: nessun merge, nessun trigger creato, nessun accesso/esecuzione VPS. Piano draft con data OOS nulla: blocca l'analisi.
- Prerequisiti da approvare: candidato e criteri prospettici, data futura successiva al commit congelato, baseline, archivio OHLC offline con manifest verificato. Esistenza dell'archivio VPS non verificata; nessun collector installato.
- Step 6 resta APERTO: codice preparato per review, nessun risultato economico nuovo.

## 22/10/2026 — Revisione indipendente Step 6 completata, sintesi esterna aperta

- Oggetto esaminato: fe50c2ff. Relazione strutturata: diario/2026-10-22_step6-review-sintesi_chatgpt.md.
- Raccomandazione: mantenere draft e oos_start_utc=null. Il test che obbliga draft impedisce la futura esecuzione approved; gate versione incompleto; IC assente per pochi episodi classificato come not_supported. Riproduzioni sintetiche locali registrate.
- Da definire prima dell'approvazione: coorte e valutazione finale senza test ripetuti non controllati, continuita' della configurazione, identita' del workflow congelato ed eseguito, archivio OHLC offline.
- Aggiunto a STEP6-REVIEW.md il requisito di report long/short (commit documentale c626c40c); lo script non lo implementa ancora. Osservazione dei trade di oggi riportata dall'utente, non verificata sui registri in questa sessione.
- Contabilita' delle due meta' confermata con calcolo indipendente; 19/19 test originali e py_compile passati con Python 3.12.14. Nessuna run Actions o esecuzione VPS.
- Review Step 6 originali di Claude, DeepSeek e Kimi K3 ancora da ricevere: accordi/divergenze e novita' rispetto a Claude non determinabili. Sintesi provvisoria, non conclusa.
- Solo documentazione aggiornata su work/director-chatgpt e diario. Nessun merge, modifica al piano/codice operativo o push a stable/*.


## 22/10/2026 — Integrazione contributo esterno E1 (senza sorgente)

- Ricevuto un report che dichiara assenza del codice; autore non indicato, quindi non attribuito a DeepSeek/Kimi.
- Confrontato con fe50c2ff: liquidation e' una valorizzazione netta d'uscita, non liquidazione forzata; gestione della finestra conserva baseline, non elimina automaticamente il trade; inverso slippage coerente col motore PAPER.
- Accordi utili: contabilita' proporzionale, aggregazione per episodio, cautela sul singolo giorno e segmentazione long/short. Non confermate adeguatezza universale di 2000 repliche o deduzioni causali live/strutturali.
- Funding e fee exchange reali non sostituiscono senza decisione il modello PAPER; nessuna formula/tariffa esterna usata come prova. Nessun bug aggiuntivo riprodotto dal report.
- Relazione strutturata aggiornata, sezione 8. R1-R6 ancora aperti; piano draft, data OOS nulla. Review nominative Step 6 e attribuzione di E1 ancora da completare.
- Solo aggiornamento documentale sul ramo diario; nessuna run Actions/VPS, modifica funzionale o merge.


## 22/10/2026 — Integrazione metodologica E2

- Ricevuto secondo contributo esterno, autore non indicato; valutato come E2 nella sezione 9 della relazione Step 6.
- Proposte utili da validare: B=10000 con diagnostica Monte Carlo, requisiti su episodi/episodi attivati e leave-one-episode-out. Non sostituire automaticamente numerosita' e durata con una soglia euristica di cluster.
- Holm e' una scelta FWER valida su p-value validi; il runner attuale produce IC percentile e non implementa quei test. Nessuna sostituzione automatica o passaggio automatico a BCa.
- Segmentazione: mantenere episodi interi nelle repliche con long e short congiunti; eventuali pesi fissi cambiano il target e richiedono supporto per entrambi i lati. Il mix non invalida da solo il confronto appaiato sugli stessi trade.
- Corretto l'assunto sull'attivazione: un long sempre perdente non raggiunge necessariamente +1,5R e quindi non viene protetto dall'overlay. Osservazione odierna ancora non misurata sui registri.
- Fonti primarie R/ricerca cluster consultate; percentuali di copertura specifiche citate da E2 non adottate senza fonte e condizioni. Piano ancora draft, oos_start_utc nulla, R1-R6 aperti.
- Aggiornata solo documentazione sul ramo diario. Nessuna modifica al runner, al piano o ai workflow; nessun merge o esecuzione VPS.


## 22/10/2026 — Accesso al sorgente Step 6 chiarito

Il revisore ha cercato nelle directory backend; il percorso corretto del commit fe50c2ff e' deploy/scripts/step6_economic_replay.py. Verificato via GitHub e link raw pubblico: HTTP 200, 415 righe, 20296 byte, sha256 c301489a19df8778eaa4b9f99e175ca5aacd629e9b54a804d7479e69f6350318.

Raw immutabile: https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/fe50c2ff2f459e4260d7f2f4907ad0f7c590a478/deploy/scripts/step6_economic_replay.py

Il messaggio ripete sostanzialmente E1 e conferma che il sorgente non era stato letto: non contato come ulteriore review indipendente. Fornire questo raw per la revisione puntuale. Draft, data OOS nulla e rilievi R1-R6 invariati; nessuna modifica o esecuzione operativa.


## 22/10/2026 — Verifica della replica esterna Step 6 con codice

Confrontata la nuova review con fe50c2ff; dettaglio nella sezione 10 della
sintesi Step 6. Funding long-only coerente con il motore PAPER (limite noto,
non nuovo bug di replica); liquidation() e' una valutazione netta di uscita,
non liquidazione a margine. Il continue su fill_i non elimina il trade.
Gli indici bootstrap 24/1974 sono coerenti con il quantile empirico inverso:
ceil(2000*p)-1. La sostituzione 25/1975 non e' una correzione obbligatoria.
Convenzione verificata con calcolo locale e documentazione primaria R.

Non confermati nuovi bug gravi; resta necessaria la segmentazione long/short,
senza attribuire causalmente l'asimmetria odierna al funding o all'esecuzione.
R1-R6 aperti, piano draft e data OOS nulla. Aggiornata solo documentazione:
nessun merge, esecuzione VPS, modifica bot o push su stable/*.


## 22/10/2026 — Sintesi finale Step 6 integrata con Gemini

Valutata la revisione Gemini, che dichiara di non avere letto il sorgente.
Accolti i suggerimenti di diagnostica per bot x long/short (R medio, win rate,
profit factor con definizione e gestione denominatore zero) e piu' repliche
bootstrap con controllo Monte Carlo. Non confermati i presunti bug:
baseline_ref inverte correttamente lo slippage di uscita; liquidation() valuta
un'uscita netta a close; guard fill_i e fallback baseline esistono gia'.

Il replay non da' una diagnosi causale inequivocabile di bug vs regime e non
simula equity di portafoglio. Bonferroni non risolve pochi episodi, dipendenza
residua o valutazioni ripetute. Dettaglio in sezione 11 della sintesi.
Nessun nuovo bug verificato; R1-R6 e protocollo dati/OOS restano aperti.
Piano ancora draft, oos_start_utc nulla. Solo documentazione: nessun merge,
trigger, esecuzione VPS, modifica bot o push su stable/*.


## 22/10/2026 — Correzioni Step 6 autorizzate e avviate

Alessandro autorizza con «ok procedi» le correzioni di codice, workflow e test
su work/director-chatgpt, mantenendo draft e data OOS nulla. Proposta da
sottoporre a Claude prima di approvazione/esecuzione. Nessun merge o accesso VPS.
Obiettivi: R1-R6, report direzionale, bootstrap 10000, coorte e maturazione
fisse, requisito di evidenza della continuita' operativa. Nessuna modifica ai bot.


## 22/10/2026 — Step 6 corretto su ramo dedicato, pronto per review

- Commit 4c1645e33bdf744817e87e06cbbcc401e6531d72 su work/director-chatgpt, successivo a c626c40c. Cinque file modificati: runner, piano, workflow read-only, test e deploy/STEP6-REVIEW.md. Nessuna modifica al motore o al ramo Claude.
- R1: suite compatibile con piano approved; preflight approvazione prima dell'SSH. R6: verifica blob YAML caricato/congelato prima del checkout. PAPER ricontrollato anche nel trap finale.
- R2: controllo versione esteso a ogni tipo di evento e gate su ledger esterno di deploy/configurazione. Assenza o lacune non permettono supporto alla variante. L'autenticita' e la copertura del ledger restano un prerequisito operativo da revisionare: nessun collector installato.
- R3/R4: campione fisso, ingressi 42 giorni e maturazione 14; effetti OOS nascosti prima del termine. Minimi proposti 100 trade, 50 interventi, 30 episodi e 25 episodi attivati. Insufficienza alla scadenza = inconclusivo, senza estensione. Eventi e candele post-scadenza non recuperano il campione.
- Bootstrap 10000 repliche per seed, due seed fissi e tolleranza proposta 0,02R fra endpoint. Quantile empirico inverso; Bonferroni sui due primari pooled per bot, senza Holm/BCa improvvisati. Sensibilita' leave-one-episode-out oltre alle verifiche precedenti.
- R5: long/short e direzione x regime BTC all'ingresso, risultati in R, win rate, profit factor con null se denominatore zero, durata baseline/leva/stop/costi, censura e conteggi di esclusione per coorte/direzione. Diagnostiche descrittive, nessuna decisione automatica per lato. Stratificazione per singolo run non implementata.
- Contabilita' PAPER, inverso dello slippage e candidato a barra chiusa mantenuti. Nessuna correzione applicata sulla base dei falsi bug delle review esterne.
- Verifiche locali Python 3.12.14: 33/33 test su piano draft e 33/33 con il file di piano temporaneamente approved sintetico, poi ripristinato draft/null; py_compile, YAML, bash -n e git diff --check passati. Shell effettiva con git/docker simulati: mismatch YAML, errore analisi, cambio container e PAPER rilevati. CI Python 3.11 non eseguita.
- Piano pubblicato schema 2, status draft, oos_start_utc null e fingerprint configurazioni null. Nessun trigger presente. Nessun merge, run Actions/VPS, deploy, modifica al cervello o push stable/*.
- Review richiesta a Claude sul nuovo commit e sulle soglie proposte. Prima di approved: conferma baseline reale, archivio OHLC/capacita' (tetto attuale 16MiB per file), snapshot finali immutabili, definizione/provenienza/continuita' ledger, CI e OK esplicito utente. Nessuna data OOS fissata.


## 22/10/2026 — Audit salva-profitto AI e simmetria long/short

- Visione di Alessandro registrata: oltre il 50% sul margine, review AI attiva delle prove di continuazione; meta' se motivate, totale se insufficienti. Punto di attenzione, non trigger cieco. Nessuna attivazione o modifica autorizzata. Non coincide con il candidato meccanico dello Step 6.
- Audit su rule-pool 7a5e795; brain/cli/signals/engine identici a 4aabeb8. Versione runtime odierna non interrogata. Relazione: diario/2026-10-22_salva-profitto-e-simmetria_chatgpt.md.
- Gestione aperte gia' prevista: Claude close/partial/hold/DCA, ma limitata da frequenza, calendario/budget/errori. Fallback a regole senza review ROI dedicata; risposta AI parziale non garantisce copertura di tutte le posizioni.
- Riprodotti localmente: score_ora puo' mostrare il punteggio opposto (LONG 10, SHORT 85 => score_ora 85 sulla posizione LONG); mancano TP/R/ROI netto nella scheda; margine iniziale invece del totale dopo variazioni; hold ignora una proposta di nuovo TP e aggiorna solo timestamp. TP/SL sono processati prima dell'AI.
- DeepSeek H24 e' un conto virtuale separato, senza canale di decisione verso Hawk/Bull. Il profit sidecar legge i bot ma non applica proposte (applied=false); e' deterministico, con ipotesi ROI 15/5/5 e checkpoint 25, non review AI a 50.
- Evidenza odierna dei due casi NON disponibile: il report sidecar nel repo e' del 21/10 04:41 UTC. Non attesta proposte del 22/10. Nessun journal runtime odierno letto; liste Actions vuote/inaccessibili non dimostrano inattivita'. Nessun simbolo/importo dei casi riportato nel repo.
- Long/short: nessuna inversione generale dei segni trovata; prove sintetiche rialzo/ribasso e stop speculari coerenti. Asimmetrie/debolezze verificate: bonus stagionale short statico; uguaglianze EMA/prezzo classificate short (serie piatta senza bonus: L0/S53, sotto soglia); EMA200 4h spesso calcolata con periodo 61 su ~62 barre; incoerenze RR prompt/codice ed esempio Bull. Non attribuita causalmente la perdita dei long a una singola causa.
- Memoria per simbolo e coaching dei chiusi non equivalgono a un apprendimento verificabile delle decisioni hold/profitto. Serve audit fonte rules/claude, versione, setup, costi e uscite prima di cambiare strategia.
- Solo documentazione. Nessun deploy, merge, trigger, prompt o bot modificato. Per i journal del 22 serve un audit VPS read-only dedicato e correlato, con aggregati/hash e invarianza container. Richiede modifica/attivazione workflow non autorizzata dal vincolo attuale: attendere OK esplicito per quel controllo. Step 6 resta draft.


## 22/10/2026 sera — Quattro lavori autorizzati, solo preparazione

Decisioni utente 21:15-21:25 Roma: ordine audit read-only, proposte fix con test,
Step 6 baseline C descrittiva, progetto DeepSeek ombra sulle posizioni dei bot.
Tutto su rami work/, review Claude prima di merge/trigger/deploy. Audit autorizzato
nel perimetro descritto, ma script/workflow vanno prima revisionati: nessuna
esecuzione ora. DeepSeek resta applied=false, non subentra a Claude con esecuzione.
Il contesto serale fornito dall'utente (sole aperture short, prevalenza long nel
conto AI indipendente, budget Claude quasi esaurito) e' una segnalazione, non una
nuova misura verificata da ChatGPT. Nessun importo del conto riportato.
Correzioni operative approvate in futuro: un solo deploy prima di S, nuova baseline;
qualsiasi cambio versione fra S e F invalida OOS. Piano Step 6 resta draft/null.


## 22/10/2026 sera — Quattro proposte consegnate alla review Claude

Ordine rispettato 1 → 3 → 2 → 4. Handoff unico:
diario/2026-10-22_consegna-serale-per-claude_chatgpt.md.

- work/profit-audit-readonly bc8fcef49b72fbe692700147e692f78870097aff: script/workflow senza trigger, PAPER/invarianza/snapshot/manifest/hash chain, output aggregato; 14 test. Decisioni storiche per posizione e causalita' del budget non ricostruibili dal vecchio log sono null, non zero.
- work/profit-correctness-proposals ed36f4fb0ab03a4ad3e3075323bd401dbaa710c6: patch A e test, specifiche B non attivate; 9 test nuovi e 4 controlli CONTO preesistenti. Mirror senza LLM su 16 finestre pubbliche reali e 12 sintetiche, on/off bonus; pubblicati solo aggregati/hash. Non prova di edge o di causa delle perdite long.
- work/step6-baseline-c 9bd51349658483fd7964a22947d4985bb06b62a3, base 4c1645e3: trailing a close +1,5R, distanza 1R, full qty, stesso terminale/costi. C descrittiva senza IC/gate; due primari invariati. 38 test. Draft/null confermato.
- work/deepseek-bot-shadow-design 99c9d544528bbb4e61f11d1a51ba49ea8b4aee16: solo progetto/schema/stima, nessun installer. DeepSeek sempre ombra sui bot, no takeover. Budget complessivo richiede arbitro unico, non due cap separati. JSON/arimetica verificati, validatore formale schema non disponibile.
- Sorgente bot osservata rule-pool 2b491cd (ultimo commit solo trigger resoconto); nessun deploy inferito dal HEAD. Versione runtime e contesto serale non verificati con una nuova run.
- Prerequisiti: review Claude, definizione ROI/DCA comune, decisioni B e budget, acquisizione OHLC/snapshot, runtime-ledger/provenienza, conferma nuova baseline. Un solo deploy dei fix approvati PRIMA di S, poi baseline aggiornata; cambio versione fra S/F invalida coorte.
- Python locale 3.12.14; py_compile, YAML/bash del nuovo workflow e diff check passati. Nessuna CI 3.11 attestata.
- Nessun merge, trigger, deploy, installazione, run VPS o chiamata API modello. Rete usata solo per lettura repository/fonti e candele pubbliche per mirror; nessun dato grezzo pubblicato. Installazione ombra solo con OK esplicito successivo.


## 23/10/2026 — Audit VPS autorizzato dopo review Claude

Alessandro riferisce approvazione Claude dei quattro rami e autorizza esplicitamente il merge del solo work/profit-audit-readonly bc8fcef49b72fbe692700147e692f78870097aff e il trigger desk-profit-review-audit.yml. Nessun deploy o modifica bot. Gli altri tre rami restano proposte non unite; Step 6 draft, nessuna data S.
Verificati quattro soli file audit in diff, 14 test e py_compile passati; nessuna run operativa concorrente nelle ultime run lette. Avvio previsto sulla finestra UTC [2026-10-21T22:00Z, 2026-10-22T22:00Z), con runtime osservato separatamente. Risultati e invarianza ancora da verificare.


## 23/10/2026 — Audit profitto eseguito con successo

Run 39901269211 success; audit bc8fcef unito fast-forward, trigger 8efc0a9. PAPER prima/dopo e BOT_CONTAINER_INVARIANCE=PASS. Nessun deploy o modifica bot. 14 test passati anche su Actions.
Giornata completa Roma 22/10: Hawk 29 e Bull 14 aperture, tutte short/rules/versione fa3e220. Score long sempre <40; bonus ricostruito da codice revisionato, non log diretto. Ultime chiamate Claude 07:20:32 Hawk e 06:52:28 Bull Roma; 28/29 posizioni Hawk e 13/15 Bull senza opportunita' di chiamata durante la vita registrata. Non sono conteggi di review effettive; causa budget non identificabile.
Sidecar: 2 Hawk e 3 Bull osservate >=50% ROI; 14 checkpoint LASCIA_CORRERE in fascia 25–50, uno DATI_NON_VALIDI a 50–100, zero CHIUDI_O_PARZIALE. Applied=false. Conto AI separato: 96 chiamate, 14 fill long, 11 chiusure finali e zero righe vincenti nella finestra.
Runtime 23/10 circa 06:37 Roma: entrambi running/PAPER, calendario allowed, budget <90% e zero posizioni nello snapshot coerente; non descrive il budget storico del 22/10. Dettagli e limiti in diario/2026-10-23_chatgpt.md, JSON aggregato diario/2026-10-23_profit-audit-39901269211.json. Nessuna fonte prevista mancante; snapshot/hash chain verificati.
Restano all'utente fix B, allocazione budget DeepSeek e data S; gli altri rami non uniti, Step 6 draft.
