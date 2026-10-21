# SuperBot — sintesi delle analisi AI per ChatGPT

_21 ottobre 2026 — dati simulati (paper trading)._

## 1. Istruzioni per ChatGPT

Ti chiediamo di rianalizzare ciò che Claude ha raccolto e verificato su SuperBot, di ricontrollare i suoi numeri e di aiutarci a trovare un compromesso o una soluzione per migliorare il bot. Altri report di altre AI ti arriveranno dopo questo file.

**Regole, decisioni di Alexander valide sempre**

- **Solo analisi.** Non modificare né eseguire nulla. Nessun redeploy di Hawk e Bull, niente live trading (il Secret DESK_MODE resta paper), nessuna modifica a strategia, soglie, limiti di rischio o prompt senza una sua decisione. Le tue proposte restano proposte.
- **Repository pubblico.** Nessun segreto, nessun saldo o importo reale, nessun indirizzo di server.
- **Diario.** Prima di lavorare sul repository leggi il ramo `diario` (LEGGIMI.md, STATO.md, MANUALE-OPERATIVO.md, ultime tre voci). Claude l'ha aggiornato oggi.
- **Letto o verificato.** "Verificato" vuol dire che hai eseguito il calcolo o seguito il codice passo per passo; tutto il resto è "letto" o "supposto". Non fidarti dei numeri di Claude: oggi ha già sbagliato più volte (sezione 3).
- **Niente consigli generici** ("usa lo stop loss", "diversifica"). Ogni proposta ha un'ipotesi falsificabile, una soglia fissata prima, un numero minimo di casi e un costo. Niente adulazione.

**Come leggere il file.** Sezioni 2 e 3: fatti e misure di Claude. Sezioni 4, 5 e 6: le tre risposte ricevute finora (Perplexity, DeepSeek, Gemini) con la valutazione di Claude. Sezione 7: confronto. Sezioni 8, 9 e 10: misure ancora da fare, decisioni che spettano a Alexander, domande per te. L'Allegato A (solo nel file scaricabile) è il brief completo che le AI hanno ricevuto.

## 2. Dove siamo

SuperBot è fatto da due bot di trading simulato (paper trading, conti virtuali da 1.000 $), Hawk e Bull, sui futures perpetui di Bitget, su 26 simboli. Alexander vuole che tornino ad aprire molti trade come nei primi giorni e, in più, vuole vedere che cosa fa un'intelligenza artificiale come trader vero.

- **Primi quattro giorni:** molti trade e la maggior parte delle righe di chiusura in utile (+1.091 $ Hawk e +771 $ Bull virtuali), quasi tutte aperture short in un mercato in calo. Da allora i bot aprono meno e vincono meno.
- **Squilibrio long e short:** circa 8 long su 150 aperture. Il punteggio dei candidati è dominato dal trend ed è asimmetrico. Dal 7/10 la stagionalità aggiunge un bonus fisso solo agli short; quanto pesi non è misurato.
- **Laboratorio storico del 9/10:** cinque famiglie di strategie tecniche su 7 anni di dati, nessuna ha superato le soglie fissate in anticipo. L'unica evidenza stabile è il premio di funding (circa +32/+37 bp a settimana su 2 di esposizione lorda).
- **Gestione del profitto:** il replay su 151 trade chiusi (Hawk 121, Bull 30), con candele vere, mostra che nessuna regola meccanica migliora il totale. L'unica neutra: chiudere il 50% a +1,5R e portare lo stop a pareggio sul resto (+3 $ Hawk, −10 $ Bull rispetto al take profit fisso).
- **Trader AI in ombra:** DeepSeek Flash, attivo dal 21/10 alle 08:17 su un conto virtuale a parte. Dopo 7 cicli: 5 aperture e 1 trade chiuso. Campione troppo piccolo per concludere.
- **In attesa dell'OK di Alexander:** il redeploy di Hawk e Bull con il commit 880c4a4 (trend giornaliero vero e open interest corretti). Non è stato fatto.

## 3. Le verifiche di Claude

Numeri misurati o corretti il 21/10; ricontrollali, non fidarti. Gli strumenti sono nel repository: `deploy/scripts/stop_buckets.py` (workflow `desk-stop-fasce`, commit 91c8d21, 31 test, 33 mutazioni deliberate del codice uccise) e `deploy/scripts/pm_exec_replay.py`.

**3.1 Il pareggio dipende dallo stop (errore di Claude corretto).** Nel brief Claude aveva scritto che per il pareggio basta circa il 37–38% di vincenti: era al lordo dei costi. Con 16 bp per giro (commissioni 6+6, slippage 2+2) il pareggio sale per gli stop stretti: circa 55% con stop 0,3%, 41% con 1%, 37% con 3,5% (TP = 1,8 × stop). Con il TP misurato sui trade veri (circa +1,72R contro −1,02R) diventa circa 57%, 43% e 39%.

**3.2 Stop reali e risultato per fascia di stop** (lettura in sola lettura del registro, 21/10; R = netto diviso il rischio pianificato, costi compresi).

| | Hawk | Bull |
| --- | --- | --- |
| Trade puliti (una gamba, senza parziali né DCA) | 121 | 30 |
| Stop iniziale mediano, % del prezzo | 1,11 | 0,80 |
| Trade con stop sotto lo 0,5% | 5 | 4 |
| Vincenti | 45,5% | 36,7% |
| R medio dei vincenti / dei perdenti | +1,60 / −1,04 | +1,55 / −1,00 |
| Pareggio ricavato da questi R | 39,4% | 39,4% |
| Pareggio teorico allo stop mediano | 40,9% | 42,9% |
| R netto medio per trade (IC 95% bootstrap) | +0,16 (−0,08 / +0,39) | −0,07 (−0,51 / +0,38) |
| Dollari medi per trade | +4,7 | +4,4 |

Hawk per fascia di stop:

| Stop (% del prezzo) | Trade | Vincenti | R netto medio (IC 95%) | $ medio |
| --- | --- | --- | --- | --- |
| sotto 0,5 | 5 | 20,0% | −0,64 (−1,33 / +0,32) | −3,5 |
| 0,5–1 | 42 | 45,2% | +0,08 (−0,31 / +0,48) | +1,2 |
| 1–2 | 67 | 50,7% | +0,35 (+0,03 / +0,67) | +11,4 |
| 2 o più | 7 | 14,3% | −0,57 (−1,06 / +0,22) | −32,1 |

Lettura: per Hawk il margine sopra il pareggio c'è ma è di pochi punti e non è provato (l'intervallo del R medio include zero); per Bull non c'è. In Bull il R è circa zero ma i dollari sono positivi perché il dimensionamento pesa i trade in modo diverso dal R. I +570 $ di Hawk vengono dalla fascia 1–2%; la fascia 2 o più costa circa −225 $ su 7 trade. Quattro fasce con 5–67 casi: indizi, non prove. Non misurato: il rischio in dollari per trade (margine × leva × stop) al variare dello stop.

**3.3 Bonus di stagionalità (letto nel codice e funzione eseguita).** `seasonal.py` moltiplica una tabella fissa e approssimata di rendimenti mensili per un moltiplicatore del ciclo di halving. Dal 7/10/2026 la fase è "bear market" (−1,0) e, poiché ottobre e novembre sono mesi forti in tabella, ne esce un bonus short fisso: +5 punti su BTC, +4 su ETH, +2 sugli altri, fino a +9/+10 su BTC ed ETH a metà novembre; il bonus long è 0. Con soglie 60–63 pesa al margine. L'effetto sulle aperture non è misurato.

**3.4 Altri errori di Claude trovati e corretti.**

- Gli id dei trade ripartono da 1 a ogni azzeramento del conto: i report ora raggruppano per (run, id) e la conclusione "17 su 58 restituiscono il profitto" è ritirata.
- Il conteggio "142 trade, +0,23R" (ChatGPT) non torna con il registro: Hawk ha 124 trade chiusi (121 puliti), Bull 36 (30 puliti). Valgono le misure di 3.2.
- L'unità del "+226 bp a settimana" del laboratorio funding era poco chiara: è la media settimanale del book con 1 long e 1 short (prezzo + funding − costi), quasi tutta prezzo di poche settimane del 2021; fuori dal 2021 circa +21. Il funding vale circa +35.

**3.5 Che cosa contiene il registro di apprendimento (letto nel codice).** Eventi `open`, `close` e `candidate`. I candidati non eseguiti hanno le feature (circa 43: punteggio long e short, trend 4h e 1h, segno del trend giornaliero, funding, open interest) ma non l'esito, che va ricostruito con le candele. La stagionalità è salvata solo come nota testuale (fino a 80 caratteri). Il trend giornaliero era assente in produzione fino al 21/10, quindi non ha storia. Le righe portano l'etichetta `claude_win` (Claude consultabile da calendario o no).

**3.6 Costi simulati.** Commissione 6 bp e slippage 2 bp per lato; funding 1 bp ogni 8 ore pagato solo dai long (gli short non pagano né ricevono). Lo stop giornaliero del 12% ferma le nuove decisioni e non chiude nulla: non è un tetto di perdita.

## 4. Perplexity: tabella costi e pareggio

Perplexity ha prodotto solo una tabella di tre righe: il costo di un giro in R e la percentuale di vincenti necessaria per il pareggio, per tre larghezze di stop. Il prompt con cui è stata ottenuta non è noto.

| Stop | Costo di un giro (R) | TP netto (R) | SL netto (R) | Pareggio |
| --- | --- | --- | --- | --- |
| 0,3% | 0,533 | 1,267 | −1,533 | 54,8% |
| 1,0% | 0,160 | 1,640 | −1,160 | 41,4% |
| 3,5% | 0,046 | 1,754 | −1,046 | 37,3% |

Valutazione di Claude: i numeri tornano al ricalcolo esatto (costo 16 bp, TP = 1,8 × stop, pareggio = (1 + costo) / 2,8). Dice la cosa giusta: il costo pesa di più sugli stop stretti. Limiti: non include il funding sui long né lo slippage extra sugli stop, e usa TP = 1,8 mentre quello misurato è circa 1,72. Con le misure di Claude (3.2) l'effetto pratico su Hawk è piccolo, perché i suoi stop stanno quasi tutti tra 0,6% e 1,8%. Questa tabella ha anche rivelato l'errore di Claude sul pareggio (3.1).

## 5. DeepSeek

**Verdetto.** (a) idea buona ma applicata male 25%, (b) nessun vantaggio e primi giorni dovuti al regime di mercato 65%, (c) vantaggio di natura diversa 10%. Per lui il test che distingue meglio (a) da (b) è un'ablazione pre-registrata di stagionalità, trend 1d e asimmetria del punteggio. Se non mostra effetti, "SuperBot non ha un edge direzionale dimostrato" e andrebbe usato come motore di esecuzione e rischio, o convertito a carry sul funding.

**Proposte, tutte con soglie fissate prima**

| # | Proposta | Soglia e metodo | Sua probabilità |
| --- | --- | --- | --- |
| 1 | Ablazione del punteggio: quattro versioni in ombra (base, senza stagionalità, trend 1d attivo, simmetrica) | ΔR medio ≥ 0,15R sui candidati con punteggio 55–75, almeno 300 casi, IC bootstrap 95% che esclude zero, stesso segno nelle due metà, correzione di Holm su 3 confronti | 55% rivela un difetto materiale; 30% una variante migliora il R |
| 2 | Leva fissa finché il punteggio non è monotono rispetto al R | Spearman > 0,20 con limite inferiore dell'IC > 0; media dei 3 decili alti ≥ media dei 3 bassi + 0,15R; almeno 300 candidati | 60% che la leva legata al punteggio non sia giustificata |
| 3 | "Lascia correre": nessun take profit fisso, parziale 50% a +1,5R | ΔR ≥ 0,10R, IC > 0, positivo anche togliendo i 3 migliori trade; almeno 80 trade che toccano +1R | 25% |
| 4 | Funding carry delta-neutro (spot + perpetuo) in un conto ombra separato | Netto > +8 bp a settimana sul capitale, almeno 6 settimane su 8 positive, drawdown < 3% | 50% netto positivo; 20% batte il bot corretto per il rischio |
| 5 | Protocollo per il trader AI con quattro basi (regole attuali, scelta casuale, nessun trade, regola simmetrica) | Almeno 100 trade per la prima decisione e 300 per la finale; R medio > ogni base + 0,10R; stop anticipato dopo 50 trade se R < −0,10R | 15% edge reale; 70% protocollo utile |

**Errori che ha trovato nel brief (valutazione di Claude)**

- 142 contro 151 trade: vero, e peggio (il numero non è riproducibile). Corretto.
- "+226 bp" contro "+32/+37": unità poco chiara, non un errore. Chiarito (3.4).
- Stop giornaliero 12%: vero, non è un tetto di perdita (3.6).
- Funding simulato solo sui long: limite reale, effetto non misurato.
- Percentuale per riga o per trade: già segnalato nel brief.

**Che cosa non regge.** Colloca la mappa leva–punteggio in `engine.py`, ma sta in `brain.py` (`rules_decisions`: scalp 15x→45x, medio 5x→25x, uguale per i due bot); "Hawk 15x, Bull 5x" non risulta dal codice. La proposta 3 chiede almeno 80 trade che toccano +1R e Hawk ne ha 72 (Bull non contato). Una cella della proposta 1 è tagliata a metà frase. La proposta 2 sul bot (congelare la leva) contrasta con la richiesta di Alexander del 21/10 di togliere il tetto di leva.

## 6. Gemini

**Verdetto.** (b) nessun vantaggio 70%, (a) idea buona applicata male 20%, (c) vantaggio di natura diversa 10%. Motivo principale: i trade vincenti si concentrerebbero nei giorni di calo forte e si azzererebbero nei laterali e nei rialzi.

**Proposte**

| # | Proposta | Soglia | Sua probabilità |
| --- | --- | --- | --- |
| 1 | Togliere la stagionalità e rendere simmetrico il punteggio (etichettata "Verificato") | Almeno +30% di long nei periodi non marcatamente ribassisti, su almeno 150 candidature | 60% |
| 2 | Uscita parziale: 50% a +1,5R e stop a pareggio sul resto | Nuovo replay sui 151 trade; incremento netto positivo | 40% |
| 3 | Quattro basi di confronto obbligatorie per il trader AI | Primi 300 trade, confidenza 95% su tutte e quattro le basi | 85% |

**Valutazione di Claude** (pesa meno di quella su DeepSeek)

- "Si azzerano nei laterali" è contraddetto dal brief: nel controfattuale di ChatGPT sul mercato piatto (ricerca, non prova) il R è +0,16 con il 49% di vincenti (IC −0,11 / +0,34). Il test vero, il R per regime sui trade eseguiti, non è stato fatto da nessuno.
- "Verificato" è sbagliato: Gemini non ha eseguito nulla, ha letto che lo aveva fatto Claude.
- Proposta 1: misura il numero di long, non il R. Nel controfattuale i long sotto soglia fanno −0,08R e −0,40R nei giorni piatti (IC −0,62 / −0,24): più long può voler dire perdere di più. Togliere la stagionalità è una modifica di strategia.
- Proposta 2: è il replay già fatto. +3 $ (Hawk) e −10 $ (Bull) sono variazioni rispetto al take profit fisso (somma −7 $), non un "benchmark"; i "142 trade storici" non esistono.
- Proposta 3: ricalca quella di DeepSeek con meno rigore (nessuna correzione per confronti multipli; la base "nessun trade" vale 0). Il modulo AI è già separato, con conto virtuale a parte.
- Il suo unico "errore" trovato (45% su 151 trade) è una lettura sbagliata: il 45% è di Hawk su 121 trade.
- Chiede i log al millisecondo per misurare lo slippage reale: in paper non esistono, i fill sono simulati al livello.

## 7. Confronto tra le AI

DeepSeek e Gemini concordano su (b), cioè "nessun vantaggio dimostrato, i primi giorni erano il regime", ma leggono lo stesso brief, che inclinava già in quella direzione: l'accordo non è una conferma indipendente, e nessuna delle due ha avuto accesso al codice o ai dati.

| AI | Probabilità (a / b / c) | Che cosa porta | Rigore, giudizio di Claude |
| --- | --- | --- | --- |
| Perplexity | non le dà | Tabella costi e pareggio | Numeri corretti, copre una sola questione |
| DeepSeek | 25 / 65 / 10 | Cinque proposte con soglie, correzione per confronti multipli e stop anticipato; cinque problemi nel brief, quattro reali | Alto; qualche riferimento al codice sbagliato |
| Gemini | 20 / 70 / 10 | Tre proposte; un solo problema segnalato, mal letto | Medio-basso: una proposta è un test già fatto, etichetta "Verificato" errata |
| Claude | nessuna cifra | Misure di 3.1–3.6 | Verificate nel codice e nei dati, ma con errori propri già corretti oggi |

**In comune:** l'ablazione della stagionalità (DeepSeek con un disegno rigoroso, Gemini come modifica del codice) e il protocollo a quattro basi per il trader AI.

**Solo DeepSeek:** congelare la leva finché il punteggio non è monotono, il test "lascia correre", il funding carry delta-neutro.

**Solo Gemini:** l'uscita parziale a +1,5R, che è il test già fatto e risultato neutro.

**Giudizio di Claude.** (b) resta l'ipotesi singola più probabile (laboratorio nullo, intervalli che includono zero, campione dominato da un solo regime), ma i dati non la separano da (a) e Claude non assegna cifre: Hawk ha +0,16R con qualche punto sopra il pareggio al netto dei costi e il controfattuale sul mercato piatto non è azzerato. Il test che distingue meglio, il R per regime di mercato e per lato sui trade eseguiti, non l'ha fatto nessuno.

## 8. Che cosa resta da misurare

Tutte queste misure sono in sola lettura (contenitore usa-e-getta, registro montato in sola lettura, nessuna modifica ai bot) e si fanno con lo stesso schema delle misure già eseguite.

| # | Misura | Domanda a cui risponde | Stato |
| --- | --- | --- | --- |
| 1 | R e vincenti per regime di mercato (calo, piatto, rialzo) e per lato, sui trade eseguiti | Distingue (a) da (b): il bot guadagna solo quando il mercato scende? | Da fare, servono le candele |
| 2 | R medio per decile di punteggio | Il punteggio è monotono? Decide se la leva legata al punteggio ha senso | Da fare, l'esito dei candidati va ricostruito con le candele |
| 3 | Ablazione della stagionalità | Quanto pesa il bonus short sullo squilibrio long e short e sul R? | Da fare: punteggio senza bonus ricostruito da `sig_long`, `sig_short` e dalla nota testuale (da verificare se si legge). La variante "trend 1d attivo" solo in avanti |
| 4 | Funding reale sui trade eseguiti, contro il modello 1 bp ogni 8 ore sui soli long | Quanto distorce il modello? | Da fare: lo storico Bitget di 90 giorni copre tutta la vita dei bot |
| 5 | Rischio in dollari per trade per fascia di stop | Perché la fascia 2 o più perde −32 $ a trade con soli 7 trade? | Da fare, dato già nel registro |
| 6 | "Lascia correre": candele estese oltre il take profit, con parziale 50% a +1,5R | L'unica idea di gestione del profitto non ancora provata | Da fare |
| 7 | Effetto delle consultazioni di Claude (etichetta `claude_win`) | Claude migliora o peggiora i risultati delle regole? | Da fare |
| 8 | Trader AI in ombra contro le quattro basi | Ha un edge sopra le regole e sopra il caso? | In corso: servono almeno 100 trade chiusi |

## 9. Decisioni che spettano a Alexander

Nessuna di queste è stata presa: sono sue.

- **Redeploy di Hawk e Bull** sul commit 880c4a4 (trend giornaliero vero su 26 simboli su 26, open interest corretto). Serve un suo "via" esplicito; finora non c'è.
- **Gestione del profitto.** Nessuna regola è attiva. Deve decidere se osservare e rifare il replay quando il campione raddoppia, e se provare "lascia correre".
- **Qualunque modifica a stagionalità, leva, soglie o stop** è strategia. Il 21/10 ha chiesto di togliere il tetto di leva e di tornare ad aprire molti trade.
- **Funding carry** (spot + perpetuo) è un'altra strategia: decide se e come provarla, anche solo in ombra.
- **Trader AI in ombra:** budget di 0,50 $ al giorno approvato; costo reale circa 0,20 $ al giorno.

## 10. Domande per ChatGPT e formato della risposta

Rispondi in quest'ordine.

1. **Verifica.** Quali numeri di Claude (sezione 3) non tornano? Ricalcola almeno il pareggio al netto dei costi, il R medio per fascia di stop e il bonus di stagionalità. Segna ogni cosa come letta o verificata.
2. **Giudizio sulle tre AI.** Sei d'accordo con la valutazione di Claude (sezioni 4, 5, 6 e 7)? Che cosa gli sfugge? Il 65–70% su (b) è una conclusione dei dati o un effetto del brief?
3. **Ordine delle prove.** Quale misura della sezione 8 dà più informazione al costo minore? Per ognuna: definizione, soglia fissata prima, numero minimo di casi, che cosa la ritira.
4. **Compromesso.** Esiste un modo per far tornare ad Alexander molti trade, il suo obiettivo, senza peggiorare la qualità, cambiando per esempio il modo di usare il bot e non i parametri? Per ogni elemento: che cosa cambia, rischio, come si prova in ombra, che cosa decide l'utente. Se pensi che un compromesso non esista, dillo.
5. **Che cosa ci sfugge.** Fino a cinque difetti, ipotesi nascoste o errori di misura nel modo in cui sono stati letti i numeri, ciascuno con la prova.
6. **Altri report.** Alexander ti passerà dopo questo file i report di altre AI: confrontali con questo, segnala dove convergono, dove divergono e dove i dati dicono qualcosa di diverso da quello che le AI sostengono.

**Formato.** Breve; tabelle dove servono; nessun consiglio generico; nessuna modifica al codice; ogni affermazione marcata come letta, supposta o verificata.
