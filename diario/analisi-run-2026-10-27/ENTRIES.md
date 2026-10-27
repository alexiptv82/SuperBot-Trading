# Condizioni d’ingresso: golden contro run negative

27 ottobre 2026. Solo analisi PAPER sullo snapshot già riconciliato delle 14:30 UTC / 15:30 Zurigo. Nessuna modifica a bot, strategia, parametri, prompt, memoria o deploy. Fonti: [positions.csv ](positions.csv), [run_metrics.json ](run_metrics.json), [cronologia e limiti dell’audit ](REPORT.md). Tutti gli importi sono del simulatore PAPER.

## Risultato

Il punteggio medio scende poco, ma cambia la sua composizione e peggiora il risultato anche a parità di fascia di score, tier e simbolo. La direzione resta quasi tutta SHORT. Il passaggio verso più altcoin non basta a spiegare il crollo: le prestazioni peggiorano dentro entrambi i gruppi. Orario e volume non distinguono stabilmente i vincitori tra periodi. Nelle run tarde emerge invece un’associazione tra ATR più basso e risultati peggiori, da verificare senza trasformare una soglia esplorativa in regola.

## Metodo e limiti

282 posizioni complete: 76+112 Hawk, 17+77 Bull. Sommo tutte le tranche prima di classificare vincitori e perdenti; netto positivo identifica il vincitore. Score raw disponibile per 278/282 ingressi: mancano le prime due posizioni di ciascuna golden; non sostituisco score con confidence. I risultati sono per posizione, non normalizzati per size; leva e margine differiscono moderatamente, come documentato nell’[analisi fee ](FEES.md). Le condizioni sono osservate all’ingresso, ma il P&L successivo dipende anche da gestione e uscite: questa analisi non identifica da sola un difetto dell’ingresso.

Per gli orari uso UTC, così non mescolo il cambio d’ora del 25 ottobre: fino al 24 aggiungere 2 ore per Zurigo/Italia, dal 25 aggiungerne 1. Le fasce sono sei ore di calendario, non sessioni di mercato ufficiali. Un batch è solo il quarto d’ora dell’apertura, non un ID certo della decisione. Hawk e Bull spesso trattano gli stessi simboli nello stesso movimento: non sono due repliche indipendenti. Tutti i sottogruppi sono esplorativi e scelti dopo aver osservato dati; nessuna validazione fuori campione o ottimizzazione di soglie è stata eseguita.

## 1. Score medio e composizione del portafoglio

| Run | Score medio (n) | A / B / C | SHORT / LONG | Lordo medio |
| --- | --- | --- | --- | --- |
| Hawk #2 | 70.57 (74) | 12 / 12 / 52 | 74 / 2 | 17.02 |
| Hawk #5 | 69.29 (112) | 10 / 9 / 93 | 110 / 2 | 2.02 |
| Bull #1 | 70.00 (15) | 7 / 5 / 5 | 17 / 0 | 50.05 |
| Bull #4 | 68.82 (77) | 9 / 8 / 60 | 76 / 1 | 1.52 |

Tier A=BTC/XAU/XAG, B=ETH, C=altre altcoin. Hawk passa da C 52/76 (68,4%) a 93/112 (83,0%); Bull da 5/17 (29,4%) a 60/77 (77,9%). Lo score medio scende soltanto 70,57→69,29 Hawk e 70,00→68,82 Bull: circa 1,2 punti. La media aggregata nasconde il forte cambio di mix Bull; il confronto per tier è necessario.

| Run | Tier | n | Lordo medio | Netto medio | WR netto |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | A | 12 | 10.19 | 7.69 | 66.7% |
| Hawk #2 | B | 12 | -1.24 | -3.51 | 33.3% |
| Hawk #2 | C | 52 | 22.81 | 20.01 | 65.4% |
| Hawk #5 | A | 10 | -2.92 | -5.03 | 30.0% |
| Hawk #5 | B | 9 | -3.36 | -5.64 | 33.3% |
| Hawk #5 | C | 93 | 3.07 | 0.54 | 38.7% |
| Bull #1 | A | 7 | 22.77 | 18.14 | 71.4% |
| Bull #1 | B | 5 | 9.41 | 5.16 | 40.0% |
| Bull #1 | C | 5 | 128.90 | 123.59 | 100.0% |
| Bull #4 | A | 9 | -1.14 | -4.93 | 33.3% |
| Bull #4 | B | 8 | -12.93 | -16.68 | 25.0% |
| Bull #4 | C | 60 | 3.84 | -0.60 | 38.3% |

La parte C aveva prodotto +1.040,47 netti di Hawk #2 e +617,95 di Bull #1: nel secondo caso cinque sole posizioni, tutte vincenti, generano circa 80% del profitto della run. Nelle tarde C rende soltanto +50,26 Hawk e −36,24 Bull. A/B insieme passano da lordo medio +4,48 a −3,13 Hawk e +17,20 a −6,69 Bull. La regressione avviene dentro i gruppi, non soltanto perché cambia il loro peso.

## 2. Lo stesso score non mantiene lo stesso risultato

| Run | Score | n | Lordo medio | Netto medio | WR netto |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | 60–62 | 7 | -1.70 | -3.55 | 42.9% |
| Hawk #2 | 63–69 | 9 | -0.36 | -2.58 | 33.3% |
| Hawk #2 | 70–74 | 46 | 17.16 | 14.37 | 60.9% |
| Hawk #2 | 75+ | 12 | 37.26 | 34.21 | 83.3% |
| Hawk #2 | missing | 2 | 36.28 | 33.54 | 100.0% |
| Hawk #5 | 60–62 | 8 | 2.91 | 1.18 | 50.0% |
| Hawk #5 | 63–69 | 60 | 4.76 | 2.50 | 41.7% |
| Hawk #5 | 70–74 | 19 | -4.17 | -6.92 | 26.3% |
| Hawk #5 | 75+ | 25 | -0.14 | -3.16 | 32.0% |
| Bull #1 | 60–62 | 3 | -9.23 | -12.10 | 33.3% |
| Bull #1 | 63–69 | 2 | -36.47 | -40.07 | 0.0% |
| Bull #1 | 70–74 | 7 | 77.46 | 72.04 | 85.7% |
| Bull #1 | 75+ | 3 | 65.49 | 59.54 | 100.0% |
| Bull #1 | missing | 2 | 106.42 | 102.14 | 100.0% |
| Bull #4 | 60–62 | 7 | 3.20 | 0.36 | 42.9% |
| Bull #4 | 63–69 | 43 | 5.88 | 2.13 | 44.2% |
| Bull #4 | 70–74 | 10 | -14.48 | -19.64 | 10.0% |
| Bull #4 | 75+ | 17 | -0.78 | -6.58 | 29.4% |

La fascia 75+ passa da 83,3% WR Hawk golden a 32,0% Hawk tarda, e da 100% Bull golden (solo 3 casi) a 29,4% Bull tarda. Dentro i soli C con score >=70, Hawk golden ha 51 ingressi loggati, lordo medio +21,89 e WR 64,7%; Hawk tarda 40, lordo−0,28 e WR 32,5%. Bull golden 4, lordo+109,09 e WR 100%; Bull tarda 23, lordo−1,95 e WR 26,1%. Non è quindi dimostrato che basti tornare alla soglia 70. I C 63–69 effettivamente eseguiti nelle tarde restano positivi nel loro complesso.

| Run | Score medio vincitori netti | Score medio perdenti netti |
| --- | --- | --- |
| Hawk #2 | 71.41 | 69.33 |
| Hawk #5 | 68.10 | 70.01 |
| Bull #1 | 72.40 | 65.20 |
| Bull #4 | 67.36 | 69.65 |

Nelle golden i vincitori hanno score più alto; nelle tarde il rapporto si inverte. Lo score non è una probabilità calibrata. Non trasformo questo rovesciamento in una regola “preferire score bassi”: intervengono periodo, ricetta dello score, simboli e gestione.

## 3. Cambia la ricetta del segnale

| Run | Ingressi loggati | Breakout nel lato scelto | Punti volume | Punti trend 1d | Vol ratio mediano |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | 74 | 54/74 | 53/74 | 0/74 | 2.21 |
| Hawk #5 | 112 | 20/112 | 29/112 | 39/112 | 0.76 |
| Bull #1 | 15 | 9/15 | 8/15 | 0/15 | 1.53 |
| Bull #4 | 77 | 11/77 | 14/77 | 29/77 | 0.78 |

Hawk: breakout 54/74→20/112; contributo volume 53/74→29/112; daily 0→39/112. Bull: breakout 9/15→11/77; volume 8/15→14/77; daily 0→29/77. I vecchi 75+ Hawk avevano tutti un breakout (12/12); nei nuovi soltanto 7/25, mentre 19/25 hanno contributo daily. Nei 75+ Bull il breakout passa 3/3→3/17, daily 0→14/17. Lo stesso totale numerico può quindi descrivere setup molto diversi.

Nel codice il volume confronta l’ultima barra ricampionata 1h con la media delle 24 precedenti; la 1h può essere incompleta. Sono cambiati gli input 15m in formazione/chiusi e le definizioni 4h/daily. Differenze nei volumi possono riflettere sia mercato sia modalità di osservazione: senza input originali non separo i due effetti. Non è un confronto di indicatori perfettamente omogenei su dati identici.

Controllo contro una conclusione troppo facile: nelle run tarde i breakout con contributo volume NON sono il gruppo vincente. Hawk #5:16 posizioni, WR 12,5%, netto−220,76; Bull #4:10 posizioni, WR 20%, netto−69,55. Il ritorno meccanico a “breakout+volume obbligatori” non è sostenuto da questi trade. Anche volume>1,3 non è un filtro universale vincente.

## 4. Simboli più frequenti e confronto degli stessi asset

| Run | Simboli più frequenti (posizioni) |
| --- | --- |
| Hawk #2 | ETH 12, BTC 7, DOGE 6, XAG 5, BNB 5, SOL 5, XRP 5, AVAX 5 |
| Hawk #5 | ADA 9, BTC 9, ETH 9, DOGE 9, DOT 9, SOL 8, OP 6, BNB 6 |
| Bull #1 | BTC 6, ETH 5, UNI 1, XAG 1, LTC 1, AVAX 1, ADA 1, SOL 1 |
| Bull #4 | BTC 9, ADA 9, ETH 8, DOT 6, ATOM 6, SOL 6, DOGE 6, BNB 5 |

| Simbolo | Hawk #2 n / lordo medio | Hawk #5 n / lordo medio | Bull #1 n / lordo medio | Bull #4 n / lordo medio |
| --- | --- | --- | --- | --- |
| BTC | 7 / 9.77 | 9 / -3.27 | 6 / 25.78 | 9 / -1.14 |
| ETH | 12 / -1.24 | 9 / -3.36 | 5 / 9.41 | 8 / -12.93 |
| ADA | 4 / 36.29 | 9 / -8.74 | 1 / 134.45 | 9 / -18.73 |
| DOGE | 6 / 7.40 | 9 / -6.29 | 0 / — | 6 / -9.72 |
| SOL | 5 / 31.21 | 8 / -5.00 | 1 / 84.32 | 6 / -5.80 |
| UNI | 4 / 76.09 | 5 / -0.69 | 1 / 208.13 | 3 / 49.16 |
| OP | 2 / -62.83 | 6 / 26.59 | 0 / — | 4 / 20.16 |

BTC ed ETH peggiorano anche confrontando gli stessi asset; ADA e SOL passano da vincite golden a risultati medi negativi. UNI pesa molto nelle golden, ma con soli 4 ingressi Hawk e 1Bull: il Bull UNI da solo vale +202,80 netti. Non è prova di un simbolo sempre redditizio. ETH era già negativo in Hawk #2: non tutte le componenti del portafoglio golden avevano edge positivo. Una blacklist di simboli costruita qui sarebbe adattamento al campione, non una causa dimostrata.

## 5. Orario di apertura: il risultato si inverte

| Run | Fascia UTC | n | Lordo medio | Netto totale | WR netto |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | 00–06 | 24 | -18.85 | -515.47 | 12.5% |
| Hawk #2 | 06–12 | 6 | 6.67 | 24.37 | 50.0% |
| Hawk #2 | 12–18 | 33 | 32.50 | 983.30 | 81.8% |
| Hawk #2 | 18–24 | 13 | 48.73 | 598.42 | 100.0% |
| Hawk #5 | 00–06 | 26 | 19.02 | 432.42 | 57.7% |
| Hawk #5 | 06–12 | 22 | 0.46 | -44.51 | 36.4% |
| Hawk #5 | 12–18 | 47 | -4.45 | -326.72 | 34.0% |
| Hawk #5 | 18–24 | 17 | -4.08 | -112.00 | 17.6% |
| Bull #1 | 00–06 | 4 | -12.34 | -67.22 | 25.0% |
| Bull #1 | 06–12 | 1 | -34.47 | -37.95 | 0.0% |
| Bull #1 | 12–18 | 9 | 96.10 | 818.18 | 100.0% |
| Bull #1 | 18–24 | 3 | 23.27 | 57.73 | 66.7% |
| Bull #4 | 00–06 | 21 | 25.68 | 459.62 | 57.1% |
| Bull #4 | 06–12 | 13 | -5.76 | -134.99 | 23.1% |
| Bull #4 | 12–18 | 33 | -8.45 | -425.23 | 33.3% |
| Bull #4 | 18–24 | 10 | -6.86 | -113.43 | 20.0% |

Le golden guadagnano soprattutto tra 12–24 UTC e soffrono 00–06. Le tarde mostrano l’opposto:00–06 è la fascia migliore. Quindi non emerge un orario universalmente buono. In Hawk #5 il solo batch 24/10 04:00UTC (9 posizioni) vale +460,03, più dell’intero netto della fascia 00–06 (+432,42): togliendo quel gruppo il resto della fascia scende a −27,61. In Bull #4 il batch 24/10 04:30UTC (5 posizioni) vale +358,69 sui+459,62 della fascia. La correlazione tra posizioni riduce fortemente il numero di osservazioni indipendenti.

Tabelle complete per tutte le 24 ore e per giorno/batch nel CSV allegato; nessun blocco orario proposto o applicato.

## 6. Pista aggiuntiva: volatilità disponibile rispetto al costo

Ho usato ATR1h/prezzo 1% come semplice taglio esplorativo tondo, NON come soglia preesistente o ottimizzata e NON come parametro da applicare. La metrica è nota all’ingresso e non usa esiti futuri.

| Run | ATR | n loggati | Lordo medio | Netto totale | WR netto |
| --- | --- | --- | --- | --- | --- |
| Hawk #2 | >=1% | 35 | 17.65 | 521.65 | 54.3% |
| Hawk #2 | <1% | 39 | 15.47 | 501.87 | 64.1% |
| Hawk #5 | >=1% | 44 | 15.21 | 556.68 | 52.3% |
| Hawk #5 | <1% | 68 | -6.51 | -607.49 | 27.9% |
| Bull #1 | >=1% | 5 | 33.65 | 147.63 | 40.0% |
| Bull #1 | <1% | 10 | 46.98 | 418.84 | 80.0% |
| Bull #4 | >=1% | 25 | 33.32 | 723.94 | 60.0% |
| Bull #4 | <1% | 52 | -13.77 | -937.97 | 25.0% |

Nelle tarde ATR<1% raccoglie 68Hawk con netto−607,49 e 52Bull con−937,97; ATR>=1% raccoglie 44Hawk con+556,68 e 25Bull con+723,94. Il segno migliore per ATR alto ricompare separando le date 22/24/25 ottobre in entrambi i profili, quindi non dipende soltanto dal batch del 24 mattina. Il 26 ottobre entrambi i gruppi perdono: non è una protezione universale. Nelle golden ATR alto non mostra lo stesso vantaggio di WR; Bull golden è anzi migliore nel gruppo ATR basso. Associazione interessante per il regime tardo, non regola stabile dimostrata.

Coerente con la meccanica: a coefficiente 1,2ATR invariato, minore ATR può ridurre la distanza SL/TP e il movimento disponibile rispetto a fee proporzionali al notional. Ma ATR influisce anche sui livelli e si associa a simbolo, orario, trend e gestione. Non dimostro da questo raggruppamento che un cutoff ATR abbia causato o risolva il crollo. Serve verifica fuori campione e confronto a parità di contesto.

## 7. Concentrazione per data e gestione successiva

| Run | Giorno apertura UTC | n | Lordo medio | Netto finale delle posizioni |
| --- | --- | --- | --- | --- |
| Hawk #2 | 2026-10-12 | 22 | 43.03 | 887.76 |
| Hawk #2 | 2026-10-13 | 19 | -12.64 | -290.14 |
| Hawk #2 | 2026-10-14 | 24 | 31.69 | 695.85 |
| Hawk #2 | 2026-10-15 | 11 | -15.75 | -202.86 |
| Hawk #5 | 2026-10-22 | 25 | 5.44 | 78.15 |
| Hawk #5 | 2026-10-24 | 50 | 6.72 | 213.95 |
| Hawk #5 | 2026-10-25 | 28 | -1.62 | -120.83 |
| Hawk #5 | 2026-10-26 | 9 | -22.27 | -222.07 |
| Bull #1 | 2026-10-12 | 6 | 59.61 | 331.39 |
| Bull #1 | 2026-10-13 | 5 | 33.10 | 142.06 |
| Bull #1 | 2026-10-14 | 4 | 75.01 | 277.94 |
| Bull #1 | 2026-10-15 | 2 | 13.86 | 19.36 |
| Bull #4 | 2026-10-21 | 1 | -37.37 | -42.11 |
| Bull #4 | 2026-10-22 | 14 | 31.39 | 382.01 |
| Bull #4 | 2026-10-24 | 33 | 9.86 | 185.87 |
| Bull #4 | 2026-10-25 | 19 | -13.00 | -336.32 |
| Bull #4 | 2026-10-26 | 10 | -36.36 | -403.46 |

Sono coorti di APERTURA: il netto può essere realizzato nei giorni successivi. Nelle tarde non esistono nuove aperture datate 23 ottobre, ma alcune 24 mattina sono ancora sotto codicef 87 prima del deploy 297 delle 06:35UTC. Non attribuire la differenza tra coorti al solo SHA: entrate e uscite possono attraversare versioni diverse. Ad esempio tutti 10 ingressi Hawk e 6Bull con entryf 87 finiscono positivi, ma condividono una finestra di mercato molto ristretta; non certificano superiorità causale del codicef 87.

Le durate medie si riducono 5,95→4,97 ore Hawk e 11,86→5,19 ore Bull. Il tempo non è qui una condizione d’ingresso ma un esito della gestione: potrebbe concorrere ai guadagni medi differenti. Per separarlo servono fonte di ogni uscita e cronologia dei livelli; lo score di ingresso da solo non basta.

## Cosa distingue i buoni dai cattivi, con quale confidenza

| Pattern | Evidenza | Lettura |
| --- | --- | --- |
| Score medio quasi invariato, risultato molto diverso | Hawk #70,57→69,29;Bull #70,00→68,82;anche 70+peggiora | Alta descrittiva; score non calibrato |
| Cambia la ricetta dello score | Meno breakout/volume, piùdaily;75+non è lo stesso setup | Alta sui log; causa del P&L non isolata |
| Regressione dentro tier e stessi asset | A/B e C peggiorano, non soltanto cambio mix | Alta descrittiva |
| LONG/SHORT | Golden e tarde quasi tutte SHORT | Non separa da solo vincitori e perdenti |
| Orario | Fascia migliore si inverte, con grossi cluster simultanei | Non robusto per una regola oraria |
| Breakout e volume come filtro | Tardi breakout+volume WR 12,5% Hawk/20% Bull | Non sostenuto come correzione automatica |
| ATR e regime | ATR basso associa perdite tardive, ricorre in piùdate;non nelle golden | Pista da validare, confidenza causale bassa |
| Gestione delle uscite | Durate e comportamento motore/Claude cambiano nel tempo | Possibile contributo, non separabile dai soli ingressi |

Conclusione: il pattern più utile da approfondire è **stesso score apparente, diversa composizione del segnale e diversa efficacia nel regime osservato**, con molte aperture correlate e un rapporto volatilità/costi peggiore in parte delle run tarde. Non ho trovato una condizione singola che separi stabilmente buoni e cattivi in tutte e quattro le run. Nessun filtro, soglia, blacklist o orario viene implementato o presentato come soluzione già provata.

Allegato: [entry_groups.csv ](entry_groups.csv), raggruppamenti perscore/tier/direzione/simbolo/ora/giorno/batch/versione e diagnostiche. I gruppi diversi si sovrappongono: non sommarne i P&L come se fossero portafogli indipendenti.

