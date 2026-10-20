# Revisione tecnica indipendente — architettura SuperBot multistrategia e multi-AI (documento ChatGPT, commit 2679ef7)

Claude, 20/10/2026 12:50 (Roma). **Solo revisione.** Nessun codice dei bot toccato, nessun merge, deploy o trigger; `DESK_MODE` paper; nessun segreto. Le parti contestate **non sono implementate**: sono proposte, le decide Alessandro. Dove ChatGPT non è d'accordo con un rilievo, lo dimostri con codice o con un test.

**Come ho verificato.** *Letto:* il documento (ramo `diario`, 2679ef7) e il codice del ramo `work/salto-qualita` (79d56cf): `desk/cli.py`, `engine.py`, `brain.py`, `learning.py`, `analyst.py`, `signals.py`, `turbo_scalp/*`, `profit/*`, `profit_sidecar/*`, `rule_pool/*`, `strategy_lab.py` (interfaccia). *Eseguito:* (a) un test di import: `desk.engine`, `signals`, `learning`, `analyst` e `turbo_scalp.strategy` si importano **senza** caricare `desk.cli` né il connettore live; (b) il ricalcolo dei costi dello scenario AI e delle soglie Bonferroni. *Prezzi:* pagine ufficiali DeepSeek e Google lette oggi. *Non verificato:* tutto ciò che sta sul VPS (cadenza in esecuzione, file degli orari, volume reale dei log).

## 1. In breve

- **Direzione condivisa e integrabile**, a una condizione: il Director vive in un processo separato con un **conto virtuale suo** (come Turbo e sidecar). In questa fase non si collega a `cli.py`.
- **Un errore di fatto cambia il progetto:** i bot decidono ogni **30 minuti** (15 solo con uno scalp aperto o in svuotamento), non ogni 15. Con quel ritmo "chiudi al bordo e riapri subito" non è realizzabile nei bot; lo è solo in un processo che lavora barra per barra (pilot, Turbo, pool). Ciò che il pilot dimostra **non si trasferisce da solo** a Hawk e Bull.
- **Molto è già costruito** (§4): conto virtuale, scheletro di processo, lettore sicuro, giornale a catena di hash, validazione, etichettatore. **L1 "pullback/EMA" esiste già: è il Turbo Scalp.**
- **11 punti di attrito** (§5), 2 gravi: la cadenza e il guardrail che alza la taglia.
- **Prezzi AI di ChatGPT corretti**; i miei di prima erano la tariffa fuori picco. DeepSeek Flash primario, Gemini 3.5 Flash-Lite gratuito in confronto su campione (§6).
- **Ordine dei lavori proposto:** prima uno shadow **solo deterministico** (senza AI) che già produce candidati, etichette ed i termini di paragone per entrambi i lati; l'AI entra dopo come "braccio" confrontato (§7).
- **Divisione dei file:** cartelle nuove `backend/director/…` con un proprietario ciascuna; i file dei bot restano congelati (§8).

## 2. Il documento contro il codice

**Confermato (letto):** Hawk 10 posizioni / 100 $ per trade, Bull 3 / 350 $, 26 simboli (`cli.py` 62–106, 146–150); soglie 60 (BTC, ETH, XAU, XAG) e 63 (altri) nel ramo, non unite (131–138); stop/TP/liquidazione sulle barre chiuse **prima** delle decisioni (736); `sig_long`/`sig_short` nel registro e tetto sui candidati (`learning.py` 29–30, 76–77); Profit Manager solo in ombra, sidecar in sola lettura; Turbo con cooldown 2 barre intere; orari di trading spenti di default (commento in `cli.py` 168; la configurazione in esecuzione non l'ho verificata); l'engine resta l'unica autorità su margini e stop.

**Da correggere:**

| # | Documento | Codice |
|---|---|---|
| E1 | "ciclo di mercato su candele 15m", AI "dopo i cicli 15m" (§1, §4B) | Barre 15m chiuse sì, ma **si decide ogni 30 min** (`CYCLE_S=1800`, `cli.py` 224; 15 min solo con scalp aperto o in svuotamento, 1564–1571), a un orario non allineato alla chiusura delle barre. Claude al massimo una volta l'ora (`call_due`, 826) e solo nelle finestre del calendario. Coerente con il mio controllo della notte (30 min a mezzanotte, ~15 min alle 03:00 con una posizione ETH aperta: compatibile con uno scalp aperto; il tipo non l'ho verificato) |
| E2 | "backend/rule_pool: riutilizzare, non duplicare" (§1) | Giusto riusarlo, ma il pool oggi gestisce **solo 15m/1h/4h** (`rules.py` 87–88), coppie in formato ccxt (TOP10), strategie che sono oggetti `strategy_lab.Strategy` con `build(frames)` vettoriale e una posizione per regola/simbolo. Non copre il 5m (Turbo), né l'inversione, né uscite a livello strutturale (esiste solo `abs_target`): richiede un'estensione |
| E3 | L1 "pullback/EMA" come plugin nuovo (§2.3) | È già il **Turbo Scalp**: rimbalzo su EMA20 nel verso del trend, long e short (`turbo_scalp/strategy.py` `signal`). Nel laboratorio S4 era ≈ 0 lordo. L1 = Turbo generalizzato nel timeframe, non una scheda nuova |
| E4 | Arbitro: "score minimo vigente" (§2.6) | Il filtro dei bot è sulla **`confidence` scritta dal modello** (≥ 60/63, `cli.py` 1015) e sul R:R ≥ 1,5 se SL e TP sono definiti (1025), non sullo score di `signals.py` |
| E5 | 26 simboli | Giusto 26. **Errore mio:** nel brief e nei miei documenti avevo scritto 27. Corretto |
| E6 | Prezzi DeepSeek/Gemini (§5) | **Corretti.** DeepSeek: pagina ufficiale "off-peak / peak" input 0,15/0,30, output 0,60/1,20; picco 01–04 e 06–10 UTC lun–ven. I miei 0,15/0,60 erano la tariffa fuori picco |

## 3. Punto 1 — Integrabile senza rompere i bot?

Sì, con tre vincoli verificati nel codice:

1. **Processo separato, dati pubblici, volume proprio.** Il modello da copiare è `turbo_scalp/runner.py`: scarica candele pubbliche 15 s dopo la chiusura, scrive in modo atomico, ha `status.json` e healthcheck, nessuna chiave.
2. **Non importare `desk.cli`.** Alla riga di import legge le variabili d'ambiente (`DESK_PORTFOLIO`, `DESK_DATA_DIR`, `DESK_MODE`), costruisce il `LiveConnector` e stampa. Importare invece `desk.engine`, `signals`, `learning`, `analyst`, `turbo_scalp.strategy` è pulito (eseguito). La logica di `process_closed_bars` sta in `cli.py`: nel pilot servono ~15 righe equivalenti che chiamano `acc.on_bar`, **senza estrarle da `cli.py`** (estrarle significherebbe toccarlo).
3. **L'unico punto di innesto nei bot** è la lista `decisions` (`cli.py` 848 Claude, 859 regole). A valle ci sono, nell'ordine: cooldown (989), soglia di confidenza (1015), R:R (1025), guardrail (1038), controlli di `engine.open` (stop obbligatorio, una posizione per simbolo, stop non oltre il 75% della distanza di liquidazione, margine disponibile). Un futuro adattatore produce decisioni in quel formato, con `source="director"`, e attraversa gli stessi filtri. Per ora **non esiste e non va scritto**.

Concordo con le tre fasi del documento (§4D) e ne aggiungo una davanti: (a) shadow deterministico, (b) shadow con AI, (c) pilot con conto virtuale isolato, (d) adattatore ai bot dietro flag spento, con decisione separata.

## 4. Punto 2 — Componenti già presenti da riusare

| Componente | Dove | Uso proposto |
|---|---|---|
| Conto virtuale con costi 6+2 bp, liquidazione, ordine stop/TP/seconda gamba | `desk/engine.py` (`PaperAccount`, `Limits`; puro, senza rete) | Conti del pilot (uno "Director-Hawk", uno "Director-Bull") con le **stesse** regole dei bot. Costi importati da `Limits`, mai copiati |
| Scheletro di processo, candele pubbliche 5m, scrittura atomica, `status.json`, healthcheck | `turbo_scalp/runner.py`, `healthcheck.py` | Base di Observer/runner del Director |
| Modello di plugin: `Config` congelata + `config_hash` + `signal` + `step` puro + eventi con id stabile + controllo buchi (`regular`) | `turbo_scalp/strategy.py` | Contratto delle schede della Strategy Library; L1 = Turbo |
| Lettura sicura degli stati dei bot (doppia lettura, identità paper, congelamento con codici fissi) | `profit_sidecar/reader.py` | Eventuale lettura read-only di Hawk/Bull. Avvertenza: i "freeze" del sidecar sono saliti da 2 a 5 la notte scorsa, causa non accertata: il Director non deve dipendere dallo stato dei bot per calcolare i candidati (il documento lo dice già) |
| Giornale a catena di hash, unico scrittore con lock, idempotenza per `event_id`, segmenti | `profit_sidecar/journal.py` | Decision Journal. Manca la retention (v. C9) |
| Etichettatore "come sarebbe andata" (stop prima del TP, MFE/MAE in R, orizzonte) | `analyst.label_candidate` | Punto di partenza; va **esteso in una funzione nuova**: oggi è lordo costi ed entra al prezzo del ciclo |
| 43 feature note alla decisione, senza dati futuri | `learning.build_features` | Campo `features` del Candidate |
| Indicatori e punteggi L/S | `signals.read_symbol` | Come *feature* del MarketFrame, **non come selettore** (è un punteggio trend-following: asimmetria già documentata) |
| Validazione: hash dei parametri, controlli casuali, giornale immutabile, Bonferroni, futilità, allarme controlli | `rule_pool/*` | Processo di promozione delle schede, con estensione (E2) |
| Calendario di budget a finestre | `desk/schedule.py` | Modello per il tetto di spesa AI del Director |
| Workflow di installazione con SHA fissato, backup | `.github/workflows` (desk-deploy, pool-deploy, sidecar) | Installazione del Director, solo con OK esplicito |

## 5. Punto 3 — Conflitti tra selezione AI, gestione posizioni, strategie e rischio

| # | Conflitto | Evidenza | Gravità | Proposta |
|---|---|---|---|---|
| C1 | **Cadenza:** bot a 30 min, Director/Turbo a 5–15 min. Flip, uscita a tempo, invalidazione e "riapri subito dallo stesso punto" richiedono gestione barra per barra; nei bot solo stop/TP/liquidazione lo sono (retroattivi a ogni ciclo con high/low). Il resto è una `close` al ciclo, con ritardo fino a 30 min. Inoltre i bot entrano al prezzo del ciclo (barra in formazione), non all'apertura della barra successiva come nel Candidate | `cli.py` 224, 1564; 736 | **Grave** | Dichiarare "pilot ≠ bot". Nel pilot entrata all'apertura successiva (come Turbo); misurare lo scarto rispetto all'entrata "da ciclo bot" come scenario. Passare i bot a 15 minuti è una decisione futura dell'utente, non ora |
| C2 | **Guardrail alza la taglia:** margine proposto < 50 $ (Hawk) / 150 $ (Bull) o leva < 10 → forzati a 60 $ / 15x scalp (Hawk), 200 $ / 15x medio (Bull), **tipo compreso**. L'AI non può dimensionare in basso; il tipo riscritto cambia cooldown (10 min / 1 h), DCA (vietato su scalp) e frequenza di revisione. Contrasta con "mai ampliare il rischio su richiesta AI" (§2.6): qui è il codice ad ampliarlo | `cli.py` 1038–1054 | **Grave** | Nel pilot: taglia in R fisso con tetti dichiarati. Nei bot: non si tocca. Documentare la differenza |
| C3 | **"Cooldown" sono tre cose:** nei bot parte dall'**apertura** (10 min scalp / 1 h medio); nel Turbo dall'**uscita** (2 barre intere); la L5 del documento chiede una "deroga". Nei bot un flip su una posizione aperta da meno di 1 h è bloccato | `cli.py` 142–143, 989, 1106 | Media | Tre nomi diversi nei documenti. La L5 del pilot definisce la sua "pausa dopo uscita" |
| C4 | **Filtri d'ingresso diversi:** nei bot confidenza ≥ 60/63 *scritta dal modello* e R:R ≥ 1,5; l'Arbitro del documento parla di "score minimo" | `cli.py` 1015, 1025 | Media | Pilot: gate per scheda dichiarati prima. Bot: restano quelli di oggi |
| C5 | **Uscite a tempo e invalidazione** (`time_exit_bars`, `setup_invalidation`) non esistono nell'engine: ha stop, TP, liquidazione | `engine.py` 434+ | Media | Le realizza il pilot nel suo ciclo; nei bot sarebbero `close` con ritardo |
| C6 | **Precedenza delle uscite** (motore / invalidazione / Profit Manager / AI) | doc §9.3 | Media | Regola monotona: vince sempre l'uscita che riduce il rischio; nessuna AI allarga uno stop, toglie un pavimento o impedisce un'uscita del motore. Il Profit Manager resta in ombra: "AI = TIENI, PM = ESCI" è un **dato registrato**, non un conflitto da risolvere |
| C7 | **Hawk e Bull sugli stessi simboli:** conti separati, nessun controllo incrociato nel codice. Direzionalità elevata (mia misura del 20/10): 378 short su 435 candidati 60–69 | `cli.py` 62–106 | Media | Non inventare un vincolo: registrare ogni sovrapposizione e ogni lato opposto, decidere sui dati |
| C8 | **Molteplicità:** con più schede la soglia sale (z = 2,13 con K = 3; 2,54 con K = 9; 2,64 con K = 12; calcolato). Il selettore AI è un'ipotesi in più, non contata | `rule_pool/evidence.py` | Media | K dichiarato prima. Il selettore si valuta **in coppia** (stessi candidati: regola fissa contro scelta AI) e non si promuove "per i trade che sceglie" |
| C9 | **Volume del giornale:** il `learning_log` ha un tetto di 40 MB sui candidati. L'universo completo (26 simboli × 2 lati × N schede × 96 cicli ≈ 5.000×N valutazioni al giorno) può valere decine di MB al giorno con righe da ~1 KB (stima mia, non misurata) | `learning.py` 29–30 | Media | Giornale proprio e separato, righe compatte, campionamento deterministico dei non-candidati, retention. Il giornale a catena di hash non cancella: serve una politica |
| C10 | **Prompt dei bot incoerente:** `build_prompt` scrive "margine in uso X/**2000**$, posizioni n/**10**" per entrambi, ma Hawk ha 1000 $ totali e Bull 1050 $ e **3** posizioni (il system prompt Bull dice 3) | `brain.py` 319; `cli.py` 62–106 | Bassa (da misurare) | Non lo tocco (prompt = decisione tua). Da misurare: quanti rifiuti "troppe posizioni aperte" tra i candidati. Il Director legge i limiti dal PortfolioSnapshot, non da testo |
| C11 | **Funding:** l'engine addebita 1 bp/8h solo ai long, ai short zero (il pool uguale) | `engine.py` 356, 401 | Bassa | Dichiararlo come ipotesi nel confronto L/S; trascurabile sotto le 2 ore, non per tenute di giorni |

## 6. Punto 4 — DeepSeek Flash come AI H24, Gemini come secondo modello

**Prezzi** (pagine ufficiali, oggi, per milione di token): DeepSeek `deepseek-flash` input 0,15 fuori picco / 0,30 in picco, cache 0,003 / 0,006, output 0,60 / 1,20, contesto 1 M, JSON supportato. Gemini 3.5 Flash-Lite 0,30 / 2,50 a pagamento, **gratuito** nel livello free; Gemini 3.8 Flash 0,75 / 3,75 **fino al 31/12/2026**, poi 1,50 / 7,50.

**Scenario del documento ricalcolato** (96 chiamate/giorno, 8.000 in, 1.500 out): DeepSeek 0,20–0,40 $/giorno ✔; con 5.000 token fissi in cache 0,13–0,26; Gemini 3.5 Flash-Lite 0,59 ✔; Gemini 3.8 Flash 1,12 ✔, **2,23 dal 1/1/2027** (conta per l'escalation). I conti di ChatGPT sono giusti.

**Valutazione:**
- **DeepSeek Flash come primario in ombra: sì.** Costo trascurabile, JSON, contesto enorme. Mettere nel prompt prima la parte statica (regole, libreria, formato) e poi quella variabile: è ciò che fa scattare la cache. In picco costa il doppio (7 ore su 24, lun–ven).
- **Da misurare, non assumere:** se il modello produce token di ragionamento extra (contano come output); latenza in picco; tasso di JSON valido; frequenza di livelli inventati.
- **Gemini 3.5 Flash-Lite come secondo modello: sì, ma su campione** (per esempio 1 ciclo su 4, ~24 chiamate/giorno) sugli **stessi frame**, per confrontare a coppie. Costo zero nel livello free; limiti di richieste del free **non letti**. Termini dati: nel free "usato per migliorare i prodotti: sì", nel pagato "no" (pagina ufficiale); per Svizzera/SEE/UK le condizioni dei servizi a pagamento valgono anche senza pagare (verificato nei termini nella sessione precedente, da rileggere prima dell'attivazione). Mandiamo solo dati di mercato pubblici e stato minimizzato, quindi il rischio è la proprietà intellettuale del prompt, non chiavi o fondi.
- **Claude è già un braccio gratis di confronto:** le sue decisioni vere sono nel registro (`claude_call`). Lo si confronta senza spesa nuova.
- **Nessuna escalation automatica** (Gemini 3.8 Flash, `deepseek-v4-pro` a 0,66/1,98): sarebbe un altro selettore; entra solo come braccio separato, dopo aver misurato la base.
- **Ipotesi di 8.000 token:** con 26 simboli × 2 lati × più schede il prompt supera facilmente quella cifra. Serve una **shortlist deterministica** (le prime N opportunità + le posizioni aperte); le scartate si registrano comunque per l'etichettatura, ma non si mandano al modello. Il N si fissa dal budget di token misurato, non a occhio.
- **Tetto proposto di partenza:** 0,50 $/giorno e 12 $/mese per tutto il Director in ombra (atteso 0,13–0,40 $). È una proposta, non un dato: lo decide Alessandro.

## 7. Punto 5 — Miglioramenti per arrivare a un sistema completo da provare in paper

1. **Shadow deterministico prima dell'AI.** Observer + Chart/Regime + schede + Valutatore + Arbitro + giornale + etichettatore, **senza chiamare nessun modello**. Già produce, per entrambi i lati, candidati ed esiti netti di costo. Costo AI: zero. È la base su cui l'AI deve dimostrare di aggiungere valore.
2. **Basi di paragone (bracci), tutte sugli stessi frame:** (a) regole attuali dei bot (`rules_decisions`); (b) scelta casuale tra le schede ammesse; (c) "nessun trade"; (d) **regola deterministica simmetrica** (stesso punteggio specchiato per i long). Senza (d) non sapremo se il valore viene dall'AI o dall'aver tolto l'asimmetria del punteggio (in ribasso 4h il long vale al massimo 65, lo short parte da 20: `signals.py`, già mostrato nel brief); (e) Claude (già nel registro); (f) DeepSeek; (g) Gemini su campione.
3. **Etichettatore netto di costo** (funzione nuova): entrata all'apertura della barra successiva + 2 bp, 6+2 bp per lato, orizzonti +15 min, +1 h, +4 h e primo livello toccato fra stop e obiettivo (stop prima in caso di parità), intervalli per blocchi di giorni.
4. **Contratti:** aggiungere a DirectorAdvice due campi che Alessandro ha chiesto e che mancano: `hold_conviction_0_100` (convinzione di continuazione, per tenere/chiudere) e `review_after_bars` (quanto tenere). Oggi ci sono `thesis`, `invalidate_if`, `uncertainty_0_1`, non una convinzione numerica né una durata.
5. **Controlli di funzionamento fissati prima:** tetto di spesa nel codice (come `DAILY_CAP`), interruttore di spegnimento a file (come `pause.flag`), file di salute, nessuna chiave nei log. Test di iniezione di guasti già elencati dal documento (§7) più, da parte mia, **mutation test sull'Arbitro** (è codice di sicurezza).
6. **Pilot con conto virtuale isolato** solo dopo (a)–(c) stabili, con le regole identiche dell'engine; i risultati si leggono come "pilot", non come "bot".
7. **Tempi:** il documento (§6.7) dice che 7 + 7–14 giorni non dimostrano redditività: concordo. Per le schede il pool chiede ≥ 300 trade e ≥ 6 mesi; per un vantaggio netto di 50 bp ~680 trade (σ ≈ 500 bp), di 30 bp ~1.900. Le schede di range hanno σ minore, quindi meno trade, ma va stimata, non assunta.

**Parti non contestate che posso iniziare subito, con il tuo OK:** (i) misura sui log veri del volume delle righe e dei token del prompt attuale (serve un workflow di sola lettura = un trigger, quindi solo con OK); (ii) etichettatore netto di costo sui log e sulle candele storiche, in un file nuovo. Entrambe non toccano i bot. Contratti, runner e adattatori dei provider **aspettano** i contratti v1 di ChatGPT.

## 8. Punto 6 — Divisione dei lavori e dei file

| Area | Proprietario | Revisore |
|---|---|---|
| Contratti v1 (MarketFrame, Candidate, DirectorAdvice, PortfolioSnapshot): schema e fixture | ChatGPT | Claude |
| Chart & Regime Engine (swing, livelli, range, regime) | ChatGPT | Claude (mutante look-ahead) |
| Schede L1–L6 come plugin puri; Fase 0; replay A–E; backtest Turbo | ChatGPT | Claude |
| Estensioni di `strategy_lab.py` / `rule_pool` (5m, nuove schede, K) | ChatGPT | Claude (test di non regressione: i trade delle 3 regole in esecuzione identici) |
| Opportunity Evaluator (costi, gate, stima) | ChatGPT, costi importati da `desk.engine.Limits` in sola lettura | Claude |
| Observer/runner, healthcheck, giornale, etichettatore | Claude | ChatGPT |
| Arbitro deterministico | Claude (con mutation test) | ChatGPT |
| Adattatori provider, prompt versionati, tetto di spesa, interruttore | Claude | ChatGPT |
| Pilot con conto isolato e ponte del Profit Manager | Claude | ChatGPT |
| Workflow di installazione e backup | Claude (trigger solo con OK dell'utente) | — |
| `cli.py`, `engine.py`, `brain.py`, `learning.py`, `signals.py`, `live_*.py` | **nessuno: congelati** | eccezioni solo per decisione dell'utente |

Regole contro le modifiche simultanee: una cartella nuova `backend/director/<area>/` per proprietario; **un ramo per autore** (`work/director-chatgpt`, `work/director-claude`), nessuno scrive sul ramo dell'altro; un'interfaccia cambia solo alzando la versione del contratto con una nota nel diario; merge solo dopo revisione incrociata e OK dell'utente; diario e documenti del Project ciascuno nel proprio file. **Attenzione a `strategy_lab.py`:** l'hash di una regola copre il codice del segnale ma **non** gli indicatori condivisi (`rules.py`, intestazione): modificare una funzione esistente cambierebbe in silenzio le regole in esecuzione senza cambiarne l'hash. Solo aggiunte, mai modifiche alle funzioni esistenti.

## 9. Cosa cambio nella mia proposta del 20/10 12:30

1. **Simboli: 26, non 27** (correzione al brief e alla proposta).
2. **Nuovo stadio davanti:** shadow deterministico senza AI (§7.1). Cambia l'ordine dei miei stadi: formato + etichettatore → shadow deterministico → AI in ombra → confronto → consiglio → attivo limitato.
3. **Formato:** adotto MarketFrame / Candidate / DirectorAdvice di ChatGPT al posto del mio "Opportunità / Decisione / Validazione". Tengo due campi che mancano nel suo (`hold_conviction_0_100`, `review_after_bars`).
4. **Responsabilità:** accetto la ripartizione di ChatGPT e la preciso (§8); aggiungo Arbitro e mutation test a me.
5. **Etichettatore:** non è `label_candidate` com'è (lordo costi, entrata al prezzo del ciclo): serve una funzione nuova.
6. **Resta valido, e ChatGPT lo ha già assorbito (§6 e §9 del suo documento):** misurare prima di costruire; il selettore è esso stesso una strategia da validare; l'apprendimento poggia su opportunità etichettate, non sui soli trade eseguiti; i pattern complessi (triangoli, bandiere) per ultimi.

## 10. Decisioni per Alessandro

- **D1.** Il Director si prova solo in un **pilot con conto virtuale proprio**; i bot non si toccano finché non c'è prova. *(Raccomandato: sì.)*
- **D2.** Cadenza dei bot: restare a 30 minuti per ora; se in futuro serviranno flip e uscite a livello nei bot, portarli a 15 minuti è una decisione a parte. *(Raccomandato: nessuna modifica ora.)*
- **D3.** Provider: DeepSeek Flash primario, Gemini 3.5 Flash-Lite gratuito su campione; tetto di partenza 0,50 $/giorno e 12 $/mese. *(Raccomandato; il tetto lo scegli tu.)*
- **D4.** Hawk e Bull sullo stesso simbolo / lati opposti: nessun vincolo nuovo, solo registrazione e misura. *(Raccomandato.)*
- **D5.** Filtri d'ingresso: nel pilot gate per scheda dichiarati prima; nei bot restano quelli di oggi. *(Raccomandato.)*
- **D6.** Divisione di file e rami come in §8. *(Da confermare con ChatGPT.)*
- **D7.** Il difetto del prompt (2000 $ e 10 posizioni scritti per entrambi i bot, §5 C10): solo misurarlo ora, correggerlo solo se lo decidi tu.

## 11. Non verificato

Cadenza e configurazione in esecuzione sul VPS (orari, calendario); volume reale e dimensione delle righe del `learning_log`; limiti di richieste del livello gratuito di Gemini; se `deepseek-flash` produce token di ragionamento per impostazione predefinita; affidabilità e latenza di DeepSeek in picco; il tipo (scalp o medio) delle posizioni ETH della notte; l'effetto reale del difetto C10. Nessun risultato di redditività è dichiarato.

Fonti: [DeepSeek, prezzi](https://api-docs.deepseek.com/quick_start/pricing), [Google, prezzi Gemini API](https://ai.google.dev/gemini-api/docs/pricing).
