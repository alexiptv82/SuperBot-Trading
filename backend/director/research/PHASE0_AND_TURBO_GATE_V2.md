# Fase 0 e Turbo Scalp — preregistrazione v2

**20 ottobre 2026. STATO: BOZZA DA REVISIONARE, NON ANCORA CONGELATA.** Fonte canonica: backend/director/research/phase0_preregistration_v2.json. La v1 resta intatta e consultabile. Revisione richiesta da Claude nel diario commit 42e5dde. Nessun risultato reale di mercato è stato analizzato da ChatGPT per costruire la v2.

## P1 — Eliminazione del range circolare

La v1 misurava tocchi sugli stessi minimi/massimi usati per costruire i quantili; così un random walk trovava quasi inevitabilmente almeno due tocchi per lato. Nella v2 il riferimento contiene SOLTANTO otto ore di barre già chiuse (96 x 5m o 32 x 15m). Congela p10 dei minimi come supporto e p90 dei massimi come resistenza; nessun ricalcolo durante formazione/episodio. Servono ampiezza >=60 bp, ADX14 dell'ultima ora COMPLETATA <20 e spostamento assoluto del prezzo nella finestra di riferimento <=50% dell'ampiezza. Tolleranza = max(2bp del prezzo, 0,1 ATR14).

La fase successiva di qualificazione usa candele DIVERSE dal riferimento, al massimo 48 barre da 5m o 16 da 15m. Un tocco è riconosciuto solo se entro le successive 1–2 barre CHIUSE il prezzo respinge il livello di almeno 2 tolleranze; quattro rimbalzi confermati e ALTERNATI S-R-S-R o R-S-R-S (due per bordo, separazione dello stesso bordo >=3 barre). Primo close oltre limite +/- tolleranza annulla l'episodio. L'attivazione possibile parte dalla OPEN della barra SUCCESSIVA alla quarta conferma; non crea trade sul passato. Episodi non sovrapposti per simbolo/timeframe con scansione cronologica.

Il file puro range_detector_v2.py implementa il congelamento dei livelli e la conferma: **non implementa ancora lo scanner storico completo o il portafoglio**. Lo scanner con deduplicazione ed esecuzione paper dovrà rispettare la specifica ed essere revisionato prima dell'uso su OHLC reali.

**Test sintetico locale, non dato finanziario:** 100/100 serie sinusoidali ideali riconosciute, 0/100 random walk e 0/100 trend simulati, con ADX=14 imposto uguale a tutte le serie. Sono dati generati e un controllo di non-circolarità, NON prova di profitto. In Fase 0, prima del congelamento stabilire 200 repliche per simbolo/timeframe di passeggiata casuale con volatilità comparabile e 200 di permutazione a blocchi dei rendimenti di sviluppo. Stessi costi, calendario, qualità, regimi, numero di barre e regole. L'effetto netto dei veri episodi rispetto al placebo deve superare zero con limite inferiore bootstrap giornaliero al 95% >0, ed essere positivo in entrambe le metà cronologiche. Senza questo risultato la strategia range NON è validata.

## P4 — Definizione operativa del movimento catturabile

Dopo attivazione del range, ogni nuovo rimbalzo confermato sul supporto può proporre LONG e sulla resistenza SHORT; la quarta conferma può proporre soltanto sulla barra seguente. Ingresso alla prima OPEN ammissibile, stop oltre il bordo difensivo +/- tolleranza, take profit vicino al bordo opposto al netto della tolleranza. Se stop/target hanno lato errato rispetto al prezzo effettivo d'ingresso, registrare NO_TRADE. Uscita a stop, target, breakout o tempo (massimo 48 barre 5m /16 barre 15m), con priorità da fissare nei test del replay prima di dati veri; la convenzione comune outcomes.evaluate_path già definisce stop prima di TP nella medesima candela, gap sfavorevole all'OPEN, TP senza miglioramento da gap favorevole. Nessun doppio long/short sullo stesso simbolo nella stessa simulazione.

**net_captureable_move_after_costs** = media aritmetica dei movimenti realizzati NETTI in basis point sui trade che diventano eseguibili dopo la conferma, con costi dedotti una sola volta, report di net_R, mediana, percentili, conteggio, percentuale episodi senza ingresso (null e non profitto zero), drawdown, IC a blocchi per giorno e breakdown per lato/simbolo. Mai usare il massimo HIGH meno minimo LOW del futuro come rendimento conseguibile.

## P2 e P3 — Turbo: costo e prior esplorativi

Il **costo di riferimento** è 16 bp di giro; il **costo che decide l'eventuale promozione** è 20 bp. Scenari addizionali 12 e 30 bp. Turbo usa la funzione VERA desk.turbo_scalp.strategy.step: sei simboli già esistenti, EMA20/50, trend slope 6, stop 1,2 ATR, TP1,5R, time exit 24 barre 5m, cooldown2 contro cooldown3. Parametri congelati senza ottimizzazione sugli esiti.

Dichiarata esplorazione precedente riportata da Claude: otto varianti di pullback S4 15m su BTC/ETH (2019–2026), lordo circa -1,8..+1,0 bp, netto circa -16 bp, nessuna promossa. Non è un test eseguito da ChatGPT e non è la stessa implementazione Turbo 5m. Tuttavia è la stessa famiglia: per prudenza usiamo **K=10** (otto prove precedenti + due nuovi cooldown) per Bonferroni, z unilaterale circa 2,576 a alpha=0,05; K=2 (z circa 1,960) varrebbe solo per il sotto-confronto interno, non per l'intera esplorazione. Se vengono scelte varianti extra o sottogruppi di simboli, K deve aumentare.

Conferma richiesta: una sola analisi DEVELOPMENT 2025-08-21..2026-08-20 (senza tuning), poi UNA apertura dell'HOLDOUT cieco 2026-08-21..2026-10-19, quindi >=30 giorni FUTURI shadow dopo nuova autorizzazione e solo poi pilot paper isolato dopo altro OK. Gate sviluppo: >=300 trade chiusi in >=6 mesi, singola moneta <=40% dei trade, almeno 30 trade per moneta per dichiarare valida QUELLA moneta, netto medio >0 a 20bp sulle due metà, controllo random abbinato sconfitto, IC 95% del vantaggio netto >0, rule_pool.evidence per trade e per mese con K=10. Holdout positivo o inconcludente, con IC comunicati senza riottimizzazione: un fallimento impedisce promozione. Non implica mai 5 slot Bull + 5 Turbo o budget 1500 USD, decisione NON presa.

## P5 — Rapporto dati prima di osservare prezzi

Prima una tabella dei 26 mercati (sei Turbo inclusi) e timeframe 5m/15m: identificatore exchange, tipo contratto, listing, prima/ultima candela, disponibilità per sessioni aperte, gap, duplicati, timestamp incoerenti, prezzi invalidi e calendario speciale XAU/XAG. Copertura richiesta >=99,5% delle barre dovute nelle sessioni di mercato realmente aperte; segnali/riempimenti con dati consecutivi, nessuna interpolazione. Gli ultimi 60 giorni ciechi possono essere ispezionati SOLO per metadata e integrità, non distribuzioni prezzo, efficacia del detector o P&L. **Nessun download storico è stato effettuato da ChatGPT.** Claude attende il via dell'utente per scrivere il raccoglitore pubblico.

## P6 — Vantaggio minimo rilevabile, esempio non empirico

Approssimazione one-sided a 80% di potenza, alpha Bonferroni 0,05/10, Zcrit 2,576 e Zpot 0,842: MDE = 3,417 x SD_bp / sqrt(N_eff). **N_eff è il numero efficace di unità indipendenti (blocchi giorno/shock), non semplicemente il numero grezzo di trade.** La tabella vale soltanto nel caso ipotetico N_eff = N indicato.

| N nominale | SD ipotetica 50 bp | SD ipotetica 100 bp | SD ipotetica 200 bp |
|---|---:|---:|---:|
| 300 | 9,87 bp | 19,73 bp | 39,46 bp |
| 1.000 | 5,40 bp | 10,81 bp | 21,61 bp |
| 3.000 | 3,12 bp | 6,24 bp | 12,48 bp |

Le SD non sono osservate. Dopo aver acquisito soltanto i dati di sviluppo, sostituirle con SD reale, autocorrelazione e N_eff stimato; dichiarare la potenza effettiva anche se il gate risulta insufficiente.

**Ordine operativo:** revisione Claude + decisione utente, congelamento v2, rapporto integrità, test sviluppo, valutazione placebo, holdout finale, shadow e pilot separato. Nessun codice dei bot cambiato, nessun merge/deploy/trigger/LIVE.
