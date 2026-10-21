# SuperBot — brief per l'analisi di più AI

_21 ottobre 2026 — dati simulati (paper trading)._

## 1. Istruzioni per chi legge

Ti chiediamo di studiare un progetto di trading automatico e di dirci, con prove, che cosa cambieresti: anche "l'idea di fondo non regge" è una risposta utile e la accettiamo.

**Il contesto in due righe.** SuperBot è un insieme di bot che fanno trading *simulato* (paper trading: nessun denaro reale in gioco) sui futures di Bitget. Il proprietario, Alexander, pensa che l'idea di partenza sia buona ma applicata male, e vuole sapere se qualcuno vede qualcosa che a noi sfugge. Non escludiamo l'ipotesi opposta: che il vantaggio (edge) non esista.

**Le regole per te**

- **Solo analisi.** Non modifichi, non esegui e non deployi nulla. Claude (che mantiene il bot) e Alexander valuteranno ogni tua proposta prima di toccare qualunque cosa.
- **Distingui sempre *letto* da *verificato*.** "Verificato" vuol dire che hai eseguito il calcolo o seguito il codice passo per passo con numeri. Tutto il resto è "letto" o "supposto": scrivilo.
- **Contesta la premessa.** Prima di proporre modifiche, dicci se secondo te i dati mostrati sono compatibili con un vantaggio reale oppure con il caso. Se pensi che serva cambiare natura al bot, dillo.
- **Niente consigli generici.** "Usa lo stop loss", "diversifica", "fai più backtest", "gestisci il rischio" li sappiamo già. Vogliamo proposte specifiche, con una regola precisa, un parametro e un modo per smentirle con i nostri dati.
- **Niente adulazione.** Se un pezzo è fatto male, dillo senza giri di parole. Se una cosa è fatta bene, bastano due righe.
- **Non inventare numeri.** Se citi uno studio o un risultato, indica la fonte; se non sei sicuro, scrivi "non so" o "non verificabile".
- **Non servono chiavi, accessi o credenziali.** Non ne forniremo. Tutti gli importi in questo documento sono simulati.

**Se puoi leggere il codice.** Il repository è pubblico: github.com/alexiptv82/superbot-trading. Il ramo `main` è vecchio e non va guardato. Il codice attuale è nel ramo `rule-pool` (cartella `backend/desk/`: `engine.py`, `signals.py`, `cli.py`); lo stato aggiornato e il diario condiviso tra le AI sono nel ramo `diario` (`STATO.md`, `MANUALE-OPERATIVO.md`). Se non puoi leggerlo, questo documento basta: dove abbiamo un dubbio sul codice, lo diciamo.

**Come rispondere** è descritto nell'ultima sezione (§11). Le domande specifiche sono nel §10.

## 2. In una pagina

SuperBot è un sistema di trading automatico sui futures perpetui di Bitget (26 simboli: crypto principali più oro e argento), oggi solo in simulazione, che nei primi quattro giorni ha aperto molti trade e ne ha chiusi in utile la maggior parte, e da allora apre meno e vince meno: non sappiamo se il motivo è il mercato, un difetto nostro o un vantaggio che non è mai esistito.

**Che cosa è.**

- Due bot indipendenti su conti virtuali da circa 1.000 $: **Hawk** (scalping, fino a 10 posizioni contemporanee, 100 $ di margine ciascuna) e **Bull** (trade più lunghi, 6 posizioni, 150–350 $ di margine). Leva alta (media reale circa 20x; tetto per simbolo da 25x a 45x).
- Le **aperture** le decidono sempre regole fisse: un punteggio tecnico da 0 a 100 su candele da 15 minuti, 1 ora, 4 ore e 1 giorno, con una soglia di ingresso.
- Un modello linguistico (Claude Sonnet), interrogato in finestre orarie con un budget di spesa, **gestisce** le posizioni già aperte (chiusure, chiusure parziali, spostamento dello stop, DCA). Non ha mai aperto un trade.
- Accanto ai bot girano due componenti **in ombra** (osservano e registrano, non mandano ordini): un "trader AI" completo (DeepSeek) su un conto virtuale a parte, e una strategia di scalping su candele da 5 minuti.

**Che cosa vuole Alexander.** Un sistema che apra molti trade con un'alta percentuale di vincenti, come nei primi giorni; che **non restituisca il profitto** già maturato (la gestione del profitto è la sua priorità numero uno); e, a tendere, un "cervello" AI che si comporti come un trader vero. Il trading con denaro reale non è attivo e non è in programma finché lui non lo decide.

**Il sospetto.** Alexander pensa che l'impianto sia sensato ma usato male, e che un'altra AI possa notare qualcosa che a noi sfugge. Noi non lo diamo per scontato. Ci sono tre ipotesi, e chiediamo a te di pesarle con i dati qui sotto:

1. **Idea buona, applicazione sbagliata** (parametri, uscite, gestione del rischio, modo di usare l'AI).
2. **Nessun vantaggio reale**: i primi giorni erano un mercato in calo e un bot quasi solo short (circa 8 long su 150 aperture); il risultato era il regime, non l'abilità.
3. **Vantaggio reale ma di natura diversa** da quella cercata (per esempio il premio di funding, o un uso diverso dell'AI).

**Perché non siamo tranquilli.** In un laboratorio eseguito il 9 ottobre, prima dell'avvio dei bot attuali (7 anni di dati, cinque famiglie di strategie tecniche, costi inclusi) nessuna regola ha superato le soglie fissate in anticipo. Il bot però ha fatto bene nei primi giorni. I due fatti vanno conciliati, e non è ancora stato fatto in modo convincente.

## 3. Come funziona oggi

Il bot trasforma 26 grafici in due punteggi (long e short) a ogni ciclo (ogni 30 minuti, ogni 15 con uno scalp aperto), apre dove il punteggio supera una soglia fissa, e chiude con stop e take profit fissi, con regole di inversione o, nelle finestre previste, su decisione di Claude. Tutto quanto segue è letto dal codice (`backend/desk/`) salvo dove indicato.

### Il ciclo

1. A ogni ciclo (ogni 30 minuti, ogni 15 se ci sono scalp aperti) il bot scarica da Bitget le candele chiuse di 26 simboli: BTC, ETH, BNB, XRP, SOL, ADA, DOGE, AVAX, DOT, LINK, UNI, ATOM, LTC, BCH, APT, ARB, OP, NEAR, FIL, INJ, SUI, TIA, RUNE, STX, XAU, XAG. Le candele da 1 ora e 4 ore si ricavano dalle 15 minuti; quelle giornaliere si scaricano a parte.
2. Per ogni simbolo calcola un punteggio long e uno short (0–100); vince il lato più alto.
3. Se il punteggio supera la soglia, il simbolo non ha già una posizione, il rapporto rendimento/rischio è almeno 1,5 e i limiti lo permettono, il bot apre. Questa è la fonte "regole".
4. Le posizioni aperte escono per stop, per take profit, per inversione del segnale (punteggio del proprio lato sotto 35, oppure punteggio opposto da 60 in su) o per una decisione di Claude.
5. Ogni decisione, ogni candidato scartato e ogni esito finiscono in un registro di apprendimento che non viene mai cancellato.

### Il punteggio d'ingresso

| Componente | Punti | Come si assegna |
| --- | --- | --- |
| Trend 4h | 20 | EMA50 sopra/sotto EMA200 (barre 4h) |
| Trend 1h | 15 | EMA20 sopra/sotto EMA50 (barre 1h) |
| Trend 1d | 15 | EMA50 sopra/sotto EMA200 giornaliere (vedi §7: finora non si è mai attivato) |
| Prezzo contro EMA50 1h | 8 | sopra = long, sotto = short |
| Momento 24h | 0–12 | proporzionale al rendimento 24h, saturo a ±3% |
| Rottura 20 ore | 10 | chiusura oltre il massimo (minimo) delle 20 ore precedenti |
| RSI 1h | 8 | 50–70 favorisce il long, 30–50 lo short |
| Volume | 4 | volume dell'ora oltre 1,3 volte la media, nella direzione della candela |
| Pattern a candela | 8 | hammer / engulfing / shooting star; il doji toglie 5 a entrambi |
| Penalità RSI estremo | −12 | RSI sopra 78 penalizza il long, sotto 22 lo short |
| Stagionalità | 0–15 | tabella fissa di rendimenti mensili e fase del ciclo di halving (vedi §7) |

**Soglie di ingresso.** 60 per BTC, ETH, oro e argento; 63 per gli altri 22 simboli (70 nei primi giorni, 65 per una mattina, 63 dal 21/10 per scelta di Alexander).

**Lettura nostra, da contestare.** Circa 80 punti su 100 misurano la stessa cosa (la persistenza del trend su più orizzonti). Quando il mercato scende in modo coerente, molti simboli arrivano insieme a 70–85 dalla parte short e il bot apre una raffica di posizioni correlate; quando il mercato è laterale, i trend si contraddicono e nessun simbolo arriva alla soglia.

### Dimensionamento, uscite e rischio

| Voce | Valore |
| --- | --- |
| Stop loss | 1,2 × ATR(1h), limitato tra 0,3% e 3,5% del prezzo |
| Take profit | 1,8 × lo stop; misurato sui trade veri ≈ +1,7R contro −1,02R dello stop (al lordo dei costi) |
| Leva | cresce con il punteggio: da 15x (punteggio 60) a 45x (100) per gli scalp, da 5x a 25x per i trade "medi"; tetto per simbolo: BTC, oro, argento 45x; ETH 30x; altri 25x. Quasi tutti i trade sono scalp (punteggio ≥ 55). Leva media reale: Hawk circa 22x |
| Margine per trade | Hawk 100 $; Bull 150–350 $ |
| Posizioni contemporanee | Hawk 10; Bull 6 |
| Costi simulati | commissione 6 bp per lato, slippage 2 bp per lato, funding 1 bp ogni 8 ore sui soli long |
| Stop e take profit | giudicati sulle candele da 15 minuti; se la stessa candela li tocca entrambi vale lo stop (ipotesi prudente) |
| Limiti di rischio | stop giornaliero 12% (smette di decidere, non chiude nulla); blocco totale se l'equity scende a 450 $ su 1.000; stop sempre dentro il 75% della distanza dalla liquidazione |
| Limiti che NON esistono | per quanto risulta dal codice, nessun tetto per direzione, per correlazione tra simboli o per perdita totale a stop (da ricontrollare) |

L'ingresso frazionato (metà del margine subito, il resto dopo un ritracciamento di circa 0,5%) e il DCA (aggiungere a una posizione in perdita; al massimo 1 volta per gli scalp, 2 per i "medi") esistono, ma li può scegliere solo Claude: le regole aprono sempre con un solo ingresso.

### Il ruolo di Claude

Claude (modello Sonnet) viene consultato **al massimo una volta all'ora**, solo in finestre orarie stabilite da Alexander (un calendario che il bot rilegge da solo), con un budget di 0,70 $ al giorno per bot. Riceve le letture dei 26 simboli, le posizioni aperte, le statistiche dei trade passati, il calendario macro, titoli di notizie e dati di derivati. Può chiudere, chiudere in parte, spostare lo stop, fare DCA. Non ha mai aperto un trade: tutte le aperture vengono dalle regole. Fuori dalle finestre decidono solo le regole. Ogni sera riscrive degli appunti (`lessons.md`) che vengono riletti nel prompt del giorno dopo.

### Componenti in ombra (osservano e registrano, nessun ordine)

- **Trader AI in ombra** (modello DeepSeek Flash, attivo dal 21/10 alle 08:17 Roma). Ogni 15 minuti vede le candele a 15 minuti, 1 ora, 4 ore e 1 giorno dei 26 simboli e propone aperture, chiusure, chiusure parziali e spostamenti di stop su un conto virtuale a parte, con gli stessi limiti di Hawk. La dimensione della posizione (rischio 1% dell'equity allo stop) la calcola il codice, non il modello; un arbitro scarta le proposte fuori regola. Costo misurato: circa 0,002 $ a chiamata, 0,20 $ al giorno.
- **Profit Manager** (scritto da ChatGPT): osserva le posizioni di Hawk e Bull e registra che cosa avrebbero fatto varie regole di protezione del profitto (pareggio dopo +1R, parziali, ROI a gradini, trailing basato su ATR). Non esegue nulla.
- **Turbo Scalp**: strategia su candele da 5 minuti, in ombra dal 21/10.
- **Registro di apprendimento**: per ogni candidato salva i valori su cui si è deciso, l'esito in multipli di rischio (R), la massima escursione favorevole e sfavorevole. Serve per un futuro modello di probabilità (servono almeno 300–500 trade chiusi).

### Dati e infrastruttura

Candele pubbliche di Bitget; funding, open interest e rapporto long/short (OI e long/short erano rotti dall'inizio e Claude non li ha mai ricevuti: sono corretti nel codice ma non ancora in produzione); notizie; calendario macro. Tutto gira in container Docker su un solo server, in simulazione, con test automatici e un diario condiviso tra le AI che lavorano al progetto.

## 4. Le idee e la visione di Alexander

La priorità di Alexander è che il bot torni a comportarsi come nei primi tre giorni (tanti trade, circa l'80% in utile) e che sopra le regole ci sia un cervello AI che gestisca il profitto e, a tendere, operi come un trader vero. Le idee che seguono sono sue (le virgolette sono sue parole riportate); la colonna "Stato" dice che cosa ne è stato fatto.

| Idea | Che cosa vuole esattamente | Stato |
| --- | --- | --- |
| **Tornare ai primi giorni** | Nei primi 3 giorni ricorda 80+ trade e grandi profitti, e pensa che dopo "sia cambiato qualcosa oltre al mercato". Riconosce che il mercato era più favorevole ma non accetta che da solo spieghi i pochi trade e le perdite di oggi. | Verificato: segnali, soglie e motore non erano cambiati; leva e puntata nemmeno (§6). Resta aperta la domanda se il bot funzioni solo nei mercati in calo. |
| **Gestione del profitto (priorità n. 1)** | Spesso 8 posizioni su 10 sono in profitto del 25–30% sul margine ma il bot non chiude, e dopo circa due ore molte sono in perdita. Vuole un Profit Manager "intelligente", non una regola fissa: a quel livello controlla il mercato e decide se chiudere (il trend è cambiato) o lasciar correre anche per ore; chiusure parziali permesse; lo slot liberato può riaprire anche nella direzione opposta. La decisione deve essere una previsione con un livello di convinzione, non "chiudi perché sei in profitto". | Sistema in ombra dal 19/10 (nessun effetto sui bot); replay sui trade veri: nessuna regola meccanica migliora il totale (§6). |
| **Un'AI come trader vero** | Un'AI che legge i grafici come un professionista (linee, medie mobili, supporti, resistenze) su tutti i simboli insieme, decide dove aprire e chiudere, lavora 24 ore su 24 e non a finestre, costa poco (anche open source) e viene confrontata con Claude. | Trader AI in ombra (DeepSeek) attivo dal 21/10, con conto virtuale a parte (§6). Primi dati: pochissimi. |
| **Long come short** | Il bot deve lavorare bene su entrambi i lati, anche nello stesso contesto: rimbalzi su medie e supporti, rotture di resistenza, range con rimbalzi avanti e indietro, triangoli e altri pattern, ciascuno come strategia da verificare. L'AI può chiudere uno short in profitto e riaprire subito long dallo stesso punto, e viceversa. | Non implementato nelle regole. Oggi circa 8 long su 150 aperture. |
| **Trend giornaliero** | Serve per capire se andare più long o più short. | Era nel codice ma non si attivava mai; correzione pronta (§7). |
| **Sempre al lavoro** | Niente ore o mezze giornate a zero posizioni; si accontenta del profitto in corso (chiude in verde e riapre sullo slot liberato). Il bot non va mai fermato. | Soglia abbassata a 63; strategia a 5 minuti (Turbo Scalp) in ombra. |
| **La sua strategia manuale** | Da trader manuale faceva scalp da pochi minuti a poche ore con sole medie mobili: long su rimbalzo da una media, uscita quando il prezzo arriva all'altra; leva fino a circa 45x; la definisce molto rischiosa ma abbastanza redditizia se fatta bene. | **Mai formalizzata in una regola testabile**: Alexander non ha ancora dato i parametri esatti. |
| **Apprendimento continuo** | Il bot impara dagli errori; dopo 300–500 trade le lezioni di Claude vanno "cristallizzate" in regole fisse, così il bot funziona bene anche senza Claude. Un "analista" offline rilegge il registro e propone modifiche, che approva solo lui. | Registro di apprendimento attivo; analista e distillazione non ancora costruiti (servono più dati). |
| **Notizie e calendario macro** | Nei giorni con eventi forti (CPI, FOMC, discorsi della Fed) il bot lavora in modo diverso per tutto il giorno, non solo con uno stop poco prima: molti trade chiusi in rosso a ridosso del CPI. | Filtro implementato, ma dal 16/10 solo in osservazione (registra cosa avrebbe fatto). |
| **Più dati, in fretta** | Soglia più bassa (63) per raccogliere 400–500 trade in tempi brevi; 2–3 settimane di test bastano. | Applicato il 21/10. |
| **Idee per dopo** | Un terzo bot che aggreghi i segnali di Hawk, Bull e strategie open source (ensemble); estensione a forex e azioni dopo i test su Bitget; a tendere il trading con denaro reale, con un sub-account separato per bot. | Non iniziate. |

**Vincoli che Alexander ha fissato.** Tutto resta in simulazione finché non decide lui; la strategia (soglie, rischio, uscite, prompt) la cambia solo lui; lo storico dei trade e gli appunti dell'AI non si cancellano mai; spesa massima 0,70 $ al giorno per Claude per bot e 0,50 $ al giorno per l'AI in ombra (gli sta bene arrivare a 15–20 euro al mese per provare un'AI che dia un vantaggio vero). Vuole la massima autonomia delle AI, perché non ha il tempo di operare a mano.

## 5. Che cosa abbiamo fatto, in ordine cronologico

In dodici giorni il progetto è passato da una ricerca su dati storici a due bot in simulazione con un cervello AI in costruzione; il punteggio d'ingresso (signals.py) e il motore (engine.py) sono rimasti identici dal 12 al 16/10 (verificato); dopo sono cambiati la soglia di ingresso (per scelta di Alexander), i limiti di Bull, un filtro macro poi messo in sola osservazione e alcune correzioni del motore. Date in ora italiana.

| Quando | Che cosa è successo |
| --- | --- |
| fino all'8/10 | Versioni precedenti (V0.5, V1) e primo monitor: una stima lorda di circa +8 bp a operazione, su una finestra sola e con campioni sovrapposti. |
| 9/10 | **Laboratorio su dati storici** (cinque famiglie di strategie, costi inclusi): nessun vantaggio netto robusto. Vedi §6. |
| 12/10 | **Nascono Hawk e Bull** (versione "V2"). Memoria permanente (storico trade, appunti di Claude) e registro di apprendimento. Entrata frazionata. Quattro AI (DeepSeek, Gemini, Kimi, ChatGPT) consegnano algoritmi e schede di regole: nessuno viene integrato. Alexander decide di non cambiare la strategia finché i trade vanno bene. Sera: Hawk ha 10 short aperti, 9 in utile. |
| 13/10 | Si scopre che circa 15 chiamate a Claude su 17 non danno una risposta leggibile (probabile troncamento) e consumano il budget. Si aggiunge un registro delle chiamate e un **calendario**: Claude viene consultato solo in certe finestre orarie. |
| 14–15/10 | Preparazione del trading reale (sub-account separati, limiti di perdita): poi messa in stand-by. Il "cervello" diventa intoccabile. Filtro sul calendario macro (CPI, FOMC); dal 16/10 solo in osservazione perché i bot quasi non aprivano. |
| 16/10 | Alexander azzera i conti virtuali a 1.000 $ per ripartire puliti con la nuova versione. |
| 17–19/10 | Migrazione di tutto su un nuovo server (da Strasburgo a Singapore), backup verificati, deploy resi più sicuri. Nessuna modifica alla strategia. Il 19/10 è il giorno con meno movimento di mercato del mese e Hawk apre 4 posizioni e Bull 3. Sera: parte in ombra il **Profit Manager** di ChatGPT; nuove run con 1.000 $ virtuali. |
| 20/10 | Alexander nota che i bot aprono pochissimo. Indagine: nessun blocco tecnico, nessun segnale arriva alla soglia. Soglia degli altcoin 70 → 65 → 63. ChatGPT scopre che il trend giornaliero non si è mai attivato (vedi §7). Tre proposte di architettura per un "direttore" AI sopra i bot. Codice del Turbo Scalp. |
| 21/10 05:20 | **Rilascio di 12 modifiche** ai bot, tra cui correzioni del motore, soglia 63, Bull a 10 posizioni e un **tetto di leva** (Hawk 20x, Bull 15x). |
| 21/10 06–08 | Si scopre che il tetto di leva avrebbe scartato circa l'80% (Hawk) e il 96% (Bull) dei segnali storici, perché la leva sale con la convinzione. Alexander lo fa togliere; Bull torna a 6 posizioni. Parte il trader AI in ombra (DeepSeek). |
| 21/10 mattina | Si scopre che il trend giornaliero non si attivava perché Bitget restituisce 89 candele giornaliere e ne servono 200; correzione pronta e provata ma **non ancora in produzione**. Replay della gestione del profitto sui trade veri. Turbo Scalp installato in ombra. Resoconto serale automatico. |

**Chi fa che cosa.** Alexander decide tutto. ChatGPT fa il lavoro pesante e la revisione (ha scritto il Profit Manager, i contratti del futuro "direttore" e molte verifiche); Claude fa interventi mirati, infrastruttura e controlli; DeepSeek viene consultato come terzo parere. Una sola AI alla volta per componente, e l'altra rivede prima di ogni rilascio. Le AI non hanno un canale diretto: usano un diario condiviso nel repository.

## 6. Che cosa abbiamo misurato

Tutti gli importi sono in dollari **virtuali** (conti simulati da 1.000 $). I numeri hanno un campione piccolo, un solo regime di mercato forte e costi simulati: leggili come indizi, non come prove.

### 6.1 I primi giorni contro oggi (Hawk e Bull)

Il bot ha guadagnato molto nei primi quattro giorni e poi ha smesso, con lo stesso codice di punteggio.

| Periodo | Hawk: chiusure, in utile, netto | Bull: chiusure, in utile, netto |
| --- | --- | --- |
| A: 12–15/10 | 76, 61%, +1.091 $ | 30, 80%, +771 $ |
| B: 16–19/10 | 38, 26%, −285 $ | 18, 39%, −145 $ |
| C: 20/10 (un giorno) | 9, 11%, −210 $ | 4, 0%, −312 $ |

*Avvertenza:* sono righe di chiusura, e una chiusura parziale conta come riga a sé, quindi la percentuale di "in utile" per riga **sovrastima** quella per trade. Sui 151 trade "puliti" (una gamba, senza parziali né DCA) fino al 21/10 i vincenti sono il 45% per Hawk (121 trade, +570 $ complessivi) e il 37% per Bull (30 trade, +131 $). La percentuale di vincenti del solo periodo A a livello di trade non è stata ricalcolata.

**Che cosa non è cambiato** (verificato): il punteggio e il motore sono identici tra il 12 e il 16/10, e le soglie sono rimaste invariate fino al 21/10; leva media di Hawk 22–23x in ogni giorno e margine di Hawk 100 $ costante, quindi "riportare leva e puntata come all'inizio" non cambia nulla perché erano già così; tutte le aperture vengono dalle regole.

**Che cosa è cambiato**: il mercato; l'uscita per take profit (era il 61% delle uscite di Hawk in A, poi il 38% e l'11%; la perdita media per stop è rimasta circa −33 $ e −29 $); l'ingresso di un filtro macro e di Claude con più token (16–18/10); il limite di Bull a 3 posizioni (273 candidati rifiutati per "troppe posizioni" in A); dal 21/10 un tetto di leva poi tolto.

**Le aperture seguono il movimento del mercato.** La tabella confronta le aperture di ogni giorno (UTC) con il mercato dei 26 simboli.

| Giorno | Aperture Hawk (long/short) | Aperture Bull | Mediana 24h dei 26 simboli | Movimento medio assoluto | Simboli giù / su oltre 2% |
| --- | --- | --- | --- | --- | --- |
| 12/10 | 20 (0/20) | 4 | −1,5% | 2,6% | 10 / 3 |
| 13/10 | 19 (1/18) | 5 | −3,1% | 3,2% | 22 / 0 |
| 14/10 | 24 (1/23) | 4 | +1,7% | 2,5% | 0 / 12 |
| 15/10 | 11 (0/11) | 2 | −0,7% | 3,1% | 5 / 6 |
| 16/10 | 10 (1/9) | 5 | −2,3% | 3,1% | 13 / 0 |
| 17/10 | 23 (0/23) | 6 | −1,6% | 2,2% | 12 / 0 |
| 18/10 | 2 (0/2) | 2 | +1,8% | 2,5% | 0 / 10 |
| 19/10 | 4 (2/2) | 3 | +0,4% | 0,7% | 0 / 2 |

Circa 150 aperture, circa 8 long. Le raffiche coincidono con i giorni di calo diffuso; il 14/10 (rialzo, 12 simboli su oltre 2%) ha comunque 23 short su 24. Il bot guadagna quando le monete scendono con decisione e perde nei rimbalzi e nei laterali.

**Perché la matematica dei trade lascia poco margine.** Take profit a circa +1,7R e stop a −1,02R, misurati al lordo dei costi (R = rischio iniziale in prezzo). I costi simulati sono circa 16 punti base per giro (commissioni e slippage) e pesano di più quando lo stop è stretto. La percentuale di vincite necessaria per il pareggio dipende quindi dalla larghezza dello stop: con TP a 1,8 volte lo stop è circa 55% con stop allo 0,3%, 41% all'1% e 37% al 3,5%; con il TP effettivamente misurato (circa 1,72R) sale a circa 57%, 43% e 39% (ricalcolo nostro, confermato da una tabella di un'altra AI; funding sui long e slippage extra sugli stop non inclusi). Gli stop reali dei bot dipendono dall'ATR (tra 0,3% e 3,5%) e la loro distribuzione sui trade chiusi non è ancora misurata: finché non lo è, non sappiamo se il 45% di vincite di Hawk sia sopra o sotto il pareggio. Su 142 trade l'intervallo di confidenza al 95% del risultato medio va da −0,19R a +0,60R: non possiamo escludere zero.

### 6.2 Il laboratorio storico (9 ottobre)

Prima dei bot attuali abbiamo provato cinque famiglie di strategie tecniche su dati storici di Bitget (BTC ed ETH a 15 minuti dal 2019, 53 coppie a 1 ora), con soglie di accettazione fissate **prima** di guardare i risultati e costi realistici (circa 16 punti base andata e ritorno, funding incluso). Nessuna le ha superate.

| Famiglia | Esito |
| --- | --- |
| Rottura di Donchian su 4h e 1h (BTC, ETH, 7 anni) | Lordo positivo (+20/+36/+50 bp a operazione su 4h) ma t-stat 0,1–1,6 per periodo; dopo i costi circa +8 bp (4h) e +1 bp (1h): indistinguibile da zero. Servirebbero migliaia di operazioni per misurare 20 bp; ne abbiamo 427 e 1.480. |
| Mean reversion su Bollinger (1h e 15m) | Lordo negativo; sul 15m significativamente negativo nel test (t = −3,5). |
| Pullback nel trend e squeeze Bollinger (15m) | Lordo circa zero (−3,4…+2,6 bp), quindi netto circa −16 bp. |
| Donchian su 53 coppie (4h, 1h, giornaliero) | 4h: peggio di ingressi casuali. 1h: il lordo (+12 bp) è spiegato dal trend del mercato, non dal segnale (il casuale fa +17 bp). Giornaliero: media enorme ma fragile (le 10 migliori operazioni valgono l'83% del totale, bias di sopravvivenza). |
| Momentum/reversal settimanale tra coppie, neutrale al mercato | Il segno cambia tra periodi (7 giorni: −392 bp/settimana in sviluppo, +125 nel test); p di permutazione 0,19–0,79. |
| Funding carry tra coppie, neutrale al mercato | Totale +226 bp/settimana netto, ma il prezzo domina (poche settimane estreme); non supera le soglie. |

**L'unica evidenza stabile**: il premio di funding, circa +32/+37 bp a settimana su 2 di esposizione lorda (cioè 1 long + 1 short), costante in tutti i periodi e in tutti gli anni 2021–2026. Per catturarlo senza il rumore di prezzo servirebbe una copertura vera (spot e perpetuo sulla stessa coppia), che un bot solo-futures non ha. I tassi usati sono quelli di Binance come sostituto: Bitget conserva solo 90 giorni di storico.

**Conclusione di allora**: a questa frequenza e con questi costi non c'è un vantaggio tecnico sfruttabile; ogni famiglia in più provata aumenta la probabilità di un falso positivo. Il bot attuale usa invece un punteggio composito che quel laboratorio non ha mai testato come tale.

### 6.3 Che cosa sarebbe successo con una soglia più bassa

Un'analisi controfattuale fatta da ChatGPT (ricerca, non prova): 435 candidati scalp con punteggio 60–69 (soglia di allora 70), 8 giorni, stessi stop e take profit, costi e funding del motore, ma senza DCA e senza limiti di portafoglio.

| Sottoinsieme | R netto medio | Note |
| --- | --- | --- |
| Tutti | +0,29 (IC 95% +0,02 / +0,60) | vincenti 56,8% |
| Mercato in calo | +0,57 (IC −0,10 / +1,06) | vincenti 72% |
| Mercato piatto | +0,16 (IC −0,11 / +0,34) | vincenti 49% |
| Short / long | +0,35 (378 casi) / −0,08 (57 casi) | nel piatto i long fanno −0,40 (IC −0,62 / −0,24) |

Lettura prudente: nei giorni piatti, quelli in cui il bot apre poco, i candidati sotto soglia hanno attesa vicina a zero e i long sono negativi. Abbassare la soglia darebbe più trade senza prova di più profitto. Campioni correlati.

### 6.4 Gestione del profitto: replay sui trade veri

Per verificare la priorità n. 1 di Alexander abbiamo rigiocato 151 trade chiusi (Hawk 121, Bull 30) con le candele vere a 15 minuti, applicando a ciascuno regole di protezione del profitto; ogni trade è un controfattuale a sé (non si simula il rientro nello slot liberato). Lo strumento è stato verificato contro il motore dei bot e con 20 mutazioni deliberate del codice.

Il problema esiste: 72 trade di Hawk su 121 toccano +1R, e 17 di questi finiscono in perdita (−473 $; usciti a pareggio avrebbero fatto −54 $). Ma le regole tagliano più vincenti di quanti perdenti salvano.

| Regola applicata a ogni trade | Hawk: variazione del totale | Bull: variazione del totale |
| --- | --- | --- |
| Pareggio dopo +1R | −410 $ | −78 $ |
| Pareggio dopo +1,5R | −159 $ | −5 $ |
| Chiudi 50% a +1R, pareggio sul resto | −186 $ | −112 $ |
| Chiudi 50% a +1,5R, pareggio sul resto | +3 $ | −10 $ |
| Trailing basato su ATR (proposta di ChatGPT), 15m | −464 $ | −117 $ |
| ROI a gradini 15/5/5, 15m | −375 $ | −248 $ |

L'unica regola neutra è la chiusura parziale del 50% a +1,5R. Il risultato dipende dal regime: nella prima metà dei trade (trend forte) quasi tutte le regole perdono molto, nella seconda (più laterale) quasi tutte guadagnano. Limiti: 9 giorni di dati; nessun rientro nello slot liberato (favorirebbe un po' le regole); regole di ChatGPT descritte come illustrative, non calibrate. **Non abbiamo ancora provato l'opposto**: lasciare correre oltre il take profit.

### 6.5 Il trader AI in ombra (primi dati)

Dopo 7 cicli (21/10, ore 10:00): 14 voci accettate, 5 aperture, 1 proposta scartata dall'arbitro, 1 trade chiuso (NEAR long a take profit, +17,7 $), 4 posizioni aperte; conto virtuale a 1.031,90 $ su 1.000 (+3,2%); costo reale circa 0,0021 $ a chiamata. È un campione troppo piccolo per concludere qualsiasi cosa. Un dato qualitativo: nelle stesse ore in cui le regole di Hawk e Bull vedevano "mercato fermo", il modello leggeva un "risk-on" guidato dagli altcoin e apriva long di momentum su rotture pulite.

### 6.6 Claude sulle uscite

Le chiusure decise da Claude passano da 2 (periodo A) a 16 (periodo B, Hawk e Bull insieme), per circa −225 $ in totale, perdite piccole per trade. Non c'è prova che facciano danno né che facciano bene.

## 7. Problemi e difficoltà

Il problema principale è che non sappiamo distinguere un vantaggio dal mercato che ha accompagnato i primi giorni, e che altri difetti, in parte nostri, rendono ogni confronto sporco. In ordine di importanza per noi:

1. **Il vantaggio non è dimostrato e potrebbe non esistere.** Il laboratorio non ha trovato regole tecniche con edge netto; il campione dei bot è di 142 trade con intervallo di confidenza che include zero; molte posizioni dei primi giorni erano short nella stessa mossa di mercato, cioè quasi un solo campione indipendente.
2. **Un pregiudizio short strutturale, appena scoperto.** Il termine di "stagionalità" del punteggio (`seasonal.py`) è una tabella fissa di rendimenti mensili approssimativi moltiplicata per una fase del ciclo di halving. Dal 7/10/2026 la fase è "bear market" (moltiplicatore −1,0): poiché ottobre e novembre sono storicamente forti nella tabella (BTC +22% e +38%), il prodotto diventa un bonus **short** (e, per lo stesso meccanismo, un bonus long nei mesi storicamente deboli come maggio, giugno, agosto e settembre). Abbiamo eseguito la funzione: aggiunge **+5 punti short a BTC, +4 a ETH, +2 agli altri altcoin** dal 7 al 21/10, e salirà a +9/+10 per BTC/ETH a metà novembre. Con soglie di 60–63 e candidati che cadevano a 63–69, 2–5 punti decidono se un trade si apre. Non sappiamo quanto abbia pesato sulle 8 long su 150 aperture: va misurato con il registro (vedi §10).
3. **Il trend giornaliero (15 punti su 100) non si è mai attivato.** All'inizio il bot scaricava solo circa 10 giorni di candele a 15 minuti, troppo poche; una prima correzione del 20/10 scarica le candele giornaliere vere, ma il codice richiede 200 giorni e Bitget ne restituisce 89 sul canale usato. La scala effettiva è quindi circa 85. Una prima diagnosi di Claude ("il trend 1d è ribassista") era sbagliata: era assente. La correzione è pronta e provata (con barre vere: 17 simboli rialzisti, 9 ribassisti, +15 punti al lato concorde, quindi più long) ma **non è in produzione** e cambierebbe parecchio il comportamento: è una decisione di Alexander.
4. **Dati di contesto mancanti.** Open interest e rapporto long/short non sono mai arrivati a Claude (endpoint sbagliati; corretti nel codice, non in produzione; il long/short esiste solo per 6 simboli). Bitget conserva 90 giorni di storico del funding e nessuno storico dell'open interest.
5. **La gestione del profitto non ha una soluzione meccanica.** Con take profit a +1,7R e stop a −1R, bloccare il profitto a +1R o +1,5R taglia più vincenti di quanti perdenti salva (§6.4). Resta da provare l'idea opposta.
6. **Poche aperture quando il mercato è laterale, e nessun modo di sapere se aprire di più aiuterebbe.** I candidati sotto soglia nei giorni piatti hanno attesa circa zero (§6.3). Alexander vuole comunque un bot che lavori sempre.
7. **Confronti sporchi.** In pochi giorni sono cambiati insieme soglia, numero di posizioni di Bull, filtro macro, token di Claude, tetto di leva e correzioni del motore: non c'è un test A/B pulito di nessuno. Gli identificativi dei trade ripartono da 1 a ogni azzeramento del conto; questo ha prodotto un nostro errore (una conclusione sui trade che "restituiscono il profitto" ritirata). Le percentuali per riga sovrastimano quelle per trade.
8. **Rischio di concentrazione.** Non c'è un limite per direzione o correlazione. Il 12/10 Hawk aveva 10 short insieme con nozionale lordo pari a circa 22 volte l'equity; la perdita se fossero scattati tutti gli stop era il 26% del conto. Il 20/10 un rialzo improvviso ha prodotto stop a grappolo e una liquidazione (NEAR, −102 $).
9. **Realismo dell'esecuzione.** Fill al tocco del livello, ordini limite non modellati, slippage fissa di 2 bp (sugli altcoin sarà peggiore), funding costante a 1 bp ogni 8 ore. Il trading reale non è mai stato provato con denaro vero.
10. **Il ruolo di Claude è poco chiaro.** Ha il budget per poche chiamate, le sue risposte sono state spesso illeggibili (circa 15 su 17 il 13/10, probabile troncamento a 1.100 token), e non ha mai aperto un trade. Dal codice (letto, non verificato in esecuzione): nei cicli in cui Claude viene consultato e restituisce almeno una decisione, le regole non aprono nulla.
11. **Un nostro errore evitabile.** Il 21/10 abbiamo rilasciato un tetto di leva (Hawk 20x, Bull 15x) senza accorgerci che la leva cresce con la convinzione del segnale: scartava i segnali più forti. L'abbiamo trovato dopo, misurando i dati.
12. **Limiti del metodo di lavoro.** Più AI scrivono sullo stesso progetto senza un canale diretto; un'AI ha riportato una simulazione senza averla eseguita (poi corretto); regole proposte da AI avevano errori logici (vedi §9). Per questo distinguiamo "letto" da "verificato".

## 8. Che cosa è andato bene

La parte meglio riuscita è l'infrastruttura di misura: possiamo verificare quasi qualsiasi ipotesi senza rischiare nulla e senza fidarci di una sola AI.

- **Un periodo di risultati forti, anche se non sappiamo perché.** Nei primi quattro giorni Hawk e Bull hanno chiuso in utile la maggior parte delle righe di chiusura (+1.091 $ e +771 $ virtuali). Sul periodo intero il risultato medio per trade di Hawk è positivo (+0,23R su 142 trade), anche se non significativo.
- **Un motore di simulazione verificato.** Le formule di costo tornano al centesimo su 151 trade su 151; abbiamo usato il motore come oracolo per controllare gli strumenti di analisi (replay con 175 prove e 20 mutazioni del codice su 20 individuate).
- **Un registro di apprendimento che registra tutto.** Per ogni candidato, anche scartato, salva i valori su cui si è deciso e l'esito in multipli di rischio: è quello che permette controfattuali come quello del §6.3 senza aspettare nuovi dati.
- **Disciplina di ricerca.** Soglie fissate prima di guardare, calibrazioni su dati casuali, errori propri trovati e dichiarati (un errore di segno trovato da un test prima di leggere i risultati). Il 9 ottobre questa disciplina ci ha risparmiato mesi dietro a strategie senza vantaggio.
- **Un premio di funding stabile** come unica evidenza robusta, che indica una direzione diversa da quella tecnica.
- **Il trader AI in ombra costa poco e il costo è controllato dal codice.** Circa 0,20 $ al giorno, con tetto giornaliero e mensile nel codice, caso peggiore calcolato prima di ogni chiamata, registro delle spese che non si cancella.
- **Sicurezza operativa.** Tutto in simulazione; nessuna chiave di trading sui server; ogni rilascio riguarda un commit preciso con backup e ritorno indietro; backup cifrati fuori dal server con ripristino provato; punto stabile salvato.
- **La revisione incrociata funziona.** ChatGPT ha trovato il trend giornaliero assente, difetti nel controllo dei backup e un errore di Claude; Claude ha trovato difetti nei contratti e nella preregistrazione di ChatGPT. Molti dei difetti seri sono stati trovati da un'altra AI, non da chi aveva scritto il codice.

## 9. Che cosa hanno già detto le altre AI (per non ripeterlo)

Quattro AI hanno già consegnato specifiche e algoritmi, e nessuno è stato integrato nei bot: quando li abbiamo controllati con codice o simulazioni, tutti avevano difetti seri, e la nostra valutazione (di Claude e ChatGPT) è che un filtro o un modello probabilistico non crea un vantaggio che i segnali sotto non hanno.

| AI e data | Che cosa ha proposto | Difetti trovati (verificati con codice o simulazioni) |
| --- | --- | --- |
| DeepSeek, 12/10 | Regressione logistica bayesiana che stima probabilità di successo e "affidabilità" 0–100, con valore atteso e Kelly; poi schede di regole. | Un ramo del codice mai usato; il modello bayesiano senza intercetta non può imparare il tasso base di vittorie; la funzione di calibrazione è vuota; soglie incoerenti (il bot non aprirebbe mai). Nelle schede: il target della media mobile sul lato sbagliato; uno "shock di open interest" che richiede uno storico che non esiste. |
| Gemini, 12/10 | "Cervello adattivo": regressione logistica online in Python puro. | Una sola feature NaN rende per sempre NaN tutto il modello. Senza alcun vantaggio reale, con un learning rate alto il 15–21% dei segnali sembra "vincente al 55%" per puro caso. Salvataggio non atomico. |
| Kimi, 12/10 | Schede di regole con una simulazione di rovina. | Target della media sul lato sbagliato; la regola di riempimento degli ordini limite dipende dal futuro (su una passeggiata casuale produce +34 bp finti); simulazione senza costi. |
| ChatGPT, 12/10 | "Probability Brain" (boosting + logistica, validazione cronologica, astensione se non ci sono prove) e un report di specifiche di ricerca e rischio. | Il cancello di validazione ai minimi dichiarati promuove un modello senza vantaggio con la stessa frequenza di uno con vantaggio forte (6% contro 6%); boosting con poche centinaia di trade; carry che quasi non scatta mai come scritto; tetti di rischio incompatibili con le posizioni attuali. Il report è il più rigoroso dei quattro e la sua simulazione di rovina è riproducibile. |
| ChatGPT, 19–20/10 | Profit Manager in ombra; audit delle soglie; contratti e preregistrazione per un "direttore" AI; architettura multi-strategia e multi-AI. | Nella preregistrazione, il rilevatore di range dà 100% di rilevamenti anche su una passeggiata casuale; nei contratti, la chiusura parziale non ha la frazione da chiudere. D'altra parte ha trovato per primo che il trend giornaliero non si attivava, e la sua convenzione di esito coincide col motore su 38.000 percorsi. |

**Conclusioni su cui Claude e ChatGPT sono già d'accordo (non ancora decise da Alexander):**

- Un modello che filtra o calibra i segnali non crea vantaggio; impara solo dai trade che il bot ha aperto, quindi serve **etichettare anche i candidati non eseguiti** (altrimenti la selezione distorce e il sistema non parte mai).
- Servono almeno 300–500 trade chiusi per pesi stabili, molti di più per distinguere vantaggi piccoli (circa 680 trade per 50 bp, circa 1.900 per 30 bp). Un cancello di validazione che accetta con meno è un sorteggio.
- Ogni nuova ipotesi provata aumenta la probabilità di un falso positivo: le soglie vanno corrette per il numero di ipotesi.
- Il "direttore" AI va provato in un processo separato con conto virtuale proprio, e deve battere quattro basi di confronto sugli **stessi** dati: le regole attuali, una scelta casuale tra le schede ammesse, "nessun trade", e una **regola deterministica simmetrica** (lo stesso punteggio specchiato per i long). Senza l'ultima non sapremo se il valore viene dall'AI o dall'aver tolto l'asimmetria del punteggio.
- Il punteggio attuale è asimmetrico per costruzione: con trend 4h ribassista e giornaliero assente un long vale al massimo 65 punti su 100, mentre lo short parte da 20 e arriva a 85.
- Strategie su entrambi i lati (rimbalzi su livelli, rotture, range, inversioni) vanno specificate con regole numeriche fisse e provate con ingressi casuali come controllo, ma **non sono state ancora scritte né provate**.

**Che cosa non ti chiediamo.** Un altro algoritmo di probabilità (ne abbiamo tre, tutti da sistemare), un'altra architettura generica di "direttore" (ne abbiamo tre), o un altro elenco di indicatori.

## 10. Le domande a cui vogliamo risposta

Vogliamo sapere se l'impianto ha un vantaggio, dove sta, e che cosa cambierebbe radicalmente il modo di usarlo. Rispondi alle domande in cui hai qualcosa di specifico da dire e salta le altre; le prime due sono le più importanti.

**A. Sulla premessa**

1. **Quale delle tre ipotesi del §2 è più plausibile?** (a) idea buona, applicazione sbagliata; (b) nessun vantaggio, i primi giorni erano il regime di mercato; (c) vantaggio di natura diversa. Dai una probabilità a ciascuna (somma 100%) e indica quali test, eseguibili con i dati che abbiamo (registro di apprendimento con circa 43 caratteristiche per candidato e l'esito in R, candele a 15 minuti, 142 trade chiusi), le distinguerebbero. Per ogni test: definizione, soglia di accettazione fissata prima, numero minimo di casi.
2. **Il bot è in pratica una macchina da short nei mercati in calo?** Circa 8 long su 150 aperture; punteggio dominato dalla persistenza del trend e asimmetrico; un bonus short fisso dalla stagionalità (§7, punto 2). Quale ablazione misurerebbe quanto pesano, separatamente, il termine di stagionalità, il trend giornaliero e l'asimmetria del punteggio? Cosa ti aspetteresti di vedere se fosse solo un effetto del regime?

**B. Su come viene usato (il sospetto di Alexander)**

3. **Se l'idea è buona ma applicata male, che cosa è sbagliato nella costruzione, non nei parametri?** Candidati nostri, da ordinare per probabilità e da smentire se puoi: punteggio composito molto collineare; take profit fisso a 1,8 volte lo stop di 1,2 ATR; stop spesso stretti rispetto ai costi (con stop dello 0,5% il costo di 16 bp vale circa un terzo del rischio e il pareggio richiede circa il 49% di vincenti); leva che cresce con il punteggio (15x→45x) senza che la calibrazione del punteggio sia stata verificata; raffiche di posizioni correlate; una decisione ogni 30 minuti su candele a 15; un modello linguistico limitato alle uscite. Aggiungi quelli che non abbiamo visto.
4. **Il punteggio ha potere predittivo monotono?** Cioè: i candidati con punteggio più alto hanno un R medio più alto, a parità di regime? I dati per rispondere sono nel registro. Se non è monotono, la leva legata al punteggio è un errore; dicci come lo verificheresti.
5. **Gestione del profitto.** Il replay (§6.4) dice che nessuna regola meccanica tra +1R e +1,7R migliora il totale. Quale impostazione diversa varrebbe la pena provare: lasciar correre oltre il take profit (possiamo estendere le candele dopo l'uscita), un take profit più lontano con stop più stretto, uscita basata su un modello di continuazione, uscita a tempo? Con quale metrica sulla distribuzione di MFE/MAE decideresti prima di guardare i risultati?
6. **Il trader AI.** Come costruiresti un trader AI che abbia una probabilità reale di un vantaggio (dati forniti, frequenza, ruolo dell'arbitro, uso di più modelli, memoria delle decisioni)? Che cosa dovremmo misurare nelle prime 2–3 settimane per decidere se tenerlo, con quanti trade, contro quali basi di confronto? Cosa non potremo concludere con quel campione?

**C. Su strade diverse**

7. **Funding.** Il premio di funding è l'unica evidenza stabile trovata. C'è un modo concreto di sfruttarlo con i vincoli reali (Bitget, futures con leva, eventualmente spot e perpetuo sulla stessa coppia), con costi, capitale necessario, rischi (base, liquidazione, funding che cambia segno) e confronto con quello che il bot fa oggi?
8. **Strategie lato long e in range.** Quali due o tre strategie, specificate con regole numeriche fisse, hanno la maggiore probabilità di avere un vantaggio netto dopo costi di circa 16 bp su questi simboli e timeframe? Per ciascuna: stima onesta della probabilità che superi un cancello statistico corretto per il numero di ipotesi (il pool chiede almeno 300 trade e 6 mesi) e che cosa sappiamo già che la rende poco promettente.
9. **Cambiare natura al bot.** Se la tua conclusione è che un bot direzionale a leva alta non ha un vantaggio sfruttabile, che cosa dovrebbe diventare SuperBot (motore di esecuzione e rischio per segnali scelti, carry, market making, altro)? Dillo chiaramente: lo vogliamo sapere.

**D. Su quello che non vediamo**

10. **Cosa ci sfugge?** Elenca fino a cinque difetti, ipotesi nascoste o errori di misura che non abbiamo nominato in questo documento (look-ahead, bias di sopravvivenza, costi sottostimati, dipendenza tra i trade, errori nel modello di esecuzione, qualcosa nel modo in cui sono stati letti i numeri), ciascuno con la prova: una riga di codice, un calcolo, un numero del documento che non torna.
11. **Se dovessi scegliere una sola modifica**, quale faresti per prima, quale test la valida, e quale risultato ti farebbe dire che hai sbagliato?

Tutte le proposte sono **raccomandazioni**: nessuna modifica a strategia, soglie, rischio o prompt avviene senza decisione di Alexander, dopo revisione incrociata.

## 11. Come rispondere

Usa lo stesso schema per tutta la risposta, perché confronteremo le risposte di più AI una accanto all'altra e verificheremo le proposte con i nostri dati prima di fidarci di una qualsiasi.

**1. Verdetto (massimo dieci righe).** Le probabilità che assegni alle tre ipotesi del §2 (somma 100%), la ragione principale, e che cosa ti ha convinto di più in questo documento.

**2. Al massimo cinque proposte, ordinate per rapporto tra valore atteso e costo.** Per ciascuna, una scheda con questi campi:

| Campo | Contenuto |
| --- | --- |
| Titolo | Una riga. |
| Ipotesi falsificabile | Una frase che un test può smentire. |
| Che cosa cambia nel bot | La regola o, se hai letto il codice, il file e la funzione. Nessun codice completo: pseudocodice va bene. |
| Come si prova con i nostri dati | Quale dato, quale metrica, soglia di accettazione fissata prima, numero minimo di casi, controllo casuale o basi di confronto, correzione per il numero di ipotesi. |
| Che cosa la fa ritirare | Il risultato che ti farebbe dire "mi sbagliavo". |
| Costo e rischio | Lavoro, spesa, rischio di fare danni se applicata male. |
| Livello di prova | *verificato* (hai eseguito il calcolo o seguito il codice con numeri), *letto* o *supposto*. |
| Probabilità che funzioni | 0–100%, con il motivo in una riga. |

**3. Che cosa non hai potuto verificare**, e che cosa ti servirebbe per farlo.

**4. Errori o contraddizioni in questo documento**, se ne trovi.

**Cose da evitare.** Consigli generici; elenchi di indicatori; percentuali di vittoria o rendimenti promessi senza un test; numeri che non sai spiegare; adulazione. Se non sai, scrivi "non so". Se citi uno studio o un risultato, metti la fonte. Preferiamo una risposta breve e precisa a una lunga: bastano poche pagine.

**Lingua.** Italiano o inglese, come preferisci.

---

*Fonti dei numeri di questo documento: documenti interni del progetto (laboratorio del 9/10, replay del profitto del 21/10, confronto per periodi del 21/10, audit del 20/10, resoconto dell'AI in ombra del 21/10), il codice nel ramo `rule-pool` e una verifica diretta della funzione di stagionalità eseguita il 21/10. Dati simulati, conti virtuali.*
