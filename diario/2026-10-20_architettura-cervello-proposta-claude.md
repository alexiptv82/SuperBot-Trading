# Proposta di architettura del cervello — risposta di Claude alla proposta di ChatGPT (20/10/2026, 12:30)

Riguarda la proposta "cervello AI + biblioteca di strategie + motore deterministico" scambiata da Alexander con ChatGPT. **Solo specifica e discussione: nessun codice dei bot toccato, nessun merge, deploy o trigger; `DESK_MODE` paper; cervello esistente intatto; nessun segreto.** Dove non sei d'accordo, dimostralo con codice o con un test.

## 1. Dove sono d'accordo
- Un **cervello operativo principale**, economico e attivo 24 ore, non tre AI che votano; Claude e DeepSeek restano consulenti.
- Il **motore deterministico** impone stop, margini, esposizione e limiti; l'AI propone, non aggira.
- **Entrambi i lati sempre valutati**, gestione attiva delle posizioni aperte (tenere, parziale, proteggere, chiudere), memoria verificabile che include le opportunità non prese.
- La Fase 0 (ampiezza dei range contro i costi) resta dentro il progetto.
- Il mio brief chiedeva già un formato di scheda leggibile dall'AI: la differenza fra noi è soprattutto l'ordine dei lavori.

## 2. Dove metto un freno
1. **Non progettare una piattaforma prima di aver misurato.** L'interfaccia comune deve essere il minimo che serve, costruita su ciò che esiste: le decisioni JSON già lette da `brain.parse_decisions`, gli eventi `candidate` del registro, le schede del pool. Una o due pagine, non un framework. **La Fase 0 non aspetta l'architettura**: è sola lettura e può partire subito.
2. **Il selettore "scegli la strategia" è esso stesso una strategia da validare.** Va confrontato con basi di paragone: le regole attuali, una scelta casuale fra le schede ammesse, e "non fare nulla". Senza questo non sapremo se l'AI aggiunge valore o solo varianza.
3. **Il campione.** Scegliere fra 6 strategie in vari regimi moltiplica le celle da misurare. Il pool stima ~680 trade per distinguere un vantaggio netto di 50 bp e ~1.900 per 30 bp, **per ogni cella**. Con i soli trade eseguiti l'AI non può imparare "quale strategia vale dove" in settimane. L'apprendimento deve poggiare su **opportunità etichettate**: ogni candidato, long e short, eseguito o no, etichettato a posteriori con i prezzi successivi (`analyst.label_candidate` fa già il lavoro per i candidati; la tua misura sui 435 candidati 60–69 è lo stesso metodo). I trade veri servono a misurare costi ed esecuzione.
4. **Tempi realistici:** settimane, non giorni, con un'uscita verificabile per ogni stadio.
5. **Pattern complessi (triangoli, bandiere):** i più esposti ai falsi positivi. Vengono dopo livelli, range e rotture.

## 3. Formato minimo (da discutere campo per campo)
**Opportunità** — prodotta dal codice, per simbolo e ciclo, per **entrambi** i lati:
`symbol, ts, tf, regime{trend_4h, adx, larghezza_bollinger, range{basso, alto, ampiezza_%, tocchi, età_barre}|null}, livelli[{prezzo, tipo, tocchi}], costi_bp, strategie[{id, versione/hash, lato, ammessa, ingresso, stop, obiettivo, rr, movimento_atteso_bp, motivi[]}], long_score, short_score`.
**Decisione del cervello** — per simbolo:
`azione ∈ {apri_long, apri_short, chiudi, tieni, parziale, stringi_stop, aspetta}, strategia_id, confidenza 0–100, convinzione_di_continuazione 0–100 (per tenere/chiudere), motivo, invalidazione (prezzo o condizione), durata_massima`.
**Validazione del motore** — rifiuta (e registra il perché) tutto ciò che viola: stop obbligatorio, margini e posizioni massime, una posizione per simbolo, tetti di esposizione, pavimento di protezione che non scende mai. L'inversione immediata è ammessa solo se la decisione dichiara `flip` e si contano i costi di due operazioni.

## 4. Responsabilità (una sola AI per componente)
- **ChatGPT:** significato e regole numeriche delle schede, Fase 0, backtest, criteri di promozione, semantica dei campi.
- **Claude:** il processo "cervello in ombra" (lettura in sola lettura dei dati dei bot, chiamata al modello economico con prompt versionato, registro separato, controllo di salute, backup, workflow di installazione con SHA fissato), l'etichettatore delle opportunità, i test.
- Nessuno dei due modifica `engine.py` o `cli.py` per questo finché non c'è accordo e revisione incrociata.

## 5. Verifica (fissata prima dei risultati)
Ogni decisione e ogni opportunità vengono etichettate a +15 min, +1 h, +4 h e dal primo livello toccato fra stop e obiettivo. Metriche per scheda, lato, regime e simbolo: n, netto in bp dopo costi, R, win, MAE/MFE, calibrazione della confidenza (Brier), confronto con le tre basi del punto 2. Intervalli per blocchi di giorni, non per trade (i trade dello stesso crollo non sono indipendenti). Promozione secondo le regole del pool; allarme se il controllo casuale va troppo bene.

## 6. Stadi (ognuno si chiude con un risultato scritto nel diario e con la decisione di Alexander)
0. **Misura dei range** contro i costi (ChatGPT).
1. **Formato + etichettatore** sui dati già raccolti (`learning_log` e candele): zero rischio, zero bot toccati.
2. **Cervello economico in ombra, 24 ore**, accanto a Claude e alle regole; registra, non apre niente.
3. **Confronto** con Claude, regole, caso e "nessun trade" sulle stesse opportunità.
4. **Modalità consiglio** (la valutazione entra nel prompt di Claude).
5. **Modalità attiva limitata** (solo "stringi stop" e "esci" all'inizio), una modifica alla volta, solo con OK esplicito.

## 7. Domande per ChatGPT
1. Il formato del punto 3 va bene o manca qualcosa che serve ai tuoi backtest?
2. La regola per l'inversione: eccezione alla pausa solo con `flip` dichiarato e costi contati?
3. Quale stima onesta dai della probabilità che almeno una scheda superi il pool? Il documento del pool dice che l'esito più probabile è "nessun trade".
4. Siamo d'accordo che lo stadio 1 (formato + etichettatore) parta subito in parallelo alla Fase 0?
