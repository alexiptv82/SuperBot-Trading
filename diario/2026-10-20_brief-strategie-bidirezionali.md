# Brief per ChatGPT — strategie su entrambi i lati, range e inversione (20/10/2026)

Scritto da Claude su richiesta di Alexander. **Solo analisi e specifica: nessun merge, nessun deploy, nessun trigger, `DESK_MODE` paper, cervello intatto, nessun segreto nel repository.** Proprietà dei file nuovi: ChatGPT (specifica e backtest); Claude non li tocca mentre li scrivi. Se non sei d'accordo con qualcosa, dimostralo con codice o con un test.

## 1. La visione di Alexander (riassunta, non sostituita)
- Il bot lavora **24 ore su 24** e apre/chiude di continuo, **su entrambi i lati**: long e short alla pari, valutati **nello stesso contesto**.
- Strategia che gli interessa in particolare: **ping-pong in range**. Mercati laterali dove il prezzo rimbalza fra due livelli: entra short al bordo alto, chiude in profitto, e se il prezzo rimbalza su una media importante, un supporto o una resistenza, **riapre subito long dallo stesso punto**, e così via. Esempio fatto da lui: chiudere a +25% di margine e riaprire subito dal lato opposto.
- Tutto il vocabolario del long va inserito come **strategie da verificare**: rimbalzi, rotture, resistenze/supporti, triangoli, bandiere e simili. Non solo il range: il sistema deve restare aperto a qualsiasi strategia che regga i dati.
- Un'AI (economica, in ombra, 24 ore) ragiona come un trader su tutti i simboli e decide dove aprire, chiudere e quanto tenere. Stop, limiti e margini restano nel codice.
- Obiettivo pratico: tanti trade (400–500) per avere uno storico ampio.

## 2. Che cosa sappiamo già (non ripartire da zero)
- **Laboratorio 9/10** (BTC/ETH, 15m/1h/4h dal 2019, costi round trip 16 bp = 12 commissioni + 4 slippage; funding 1 bp/8h solo long): nessuna variante passa. In particolare la mean reversion Bollinger 2,5σ con ADX < 20 ha lordo **negativo** (15m: −3,7/−3,5/−8,4 bp, t −3,5 nel test; 1h: ≈ −10 bp); pullback e squeeze ≈ 0. **Non è la tua idea**: era una regola meccanica, su due simboli, senza livelli veri. Non va letta come smentita, né ignorata.
- **Pool di regole** (`specifica-pool-regole`): schede con regole fissate prima, controllo con ingressi casuali, idoneità con ≥300 trade, ≥6 mesi, t-stat corretto per K, netto positivo in entrambe le metà, migliore del controllo; ritiro per futilità dopo 100 trade con t ≤ −1; allarme se il controllo ha t ≥ 3. Ordini di grandezza: per distinguere un vantaggio netto di 50 bp servono ~680 trade, di 30 bp ~1.900.
- **Il punteggio attuale** (`signals.py`) segue il trend: un long con trend 4h ribassista e 1d assente vale al massimo 65/100, lo short sulla stessa moneta parte da 20 punti (massimo 85). Esempio eseguito (dati sintetici miei, illustrativo): calo continuo → long 1, short 61; rimbalzo forte (+9%/24h) → long 38. Per questo il bot apre quasi solo short: 378 short su 435 candidati 60–69, ~8 long su ~150 aperture reali. **Struttura del punteggio + periodo di calo**; non un errore di codice.
- **Costi**: a 6+2 bp per lato un giro costa ~16 bp sul nozionale = ~2,4% del margine a leva 15x. Un'inversione paga due operazioni.

## 3. Che cosa ti chiedo (in tre fasi, ciascuna con un risultato scritto nel diario)
**Fase 0 — misura prima di costruire.** Per ciascuno dei 27 simboli attuali (e per i 6 del Turbo): quanto è ampio un rimbalzo tipico fra due livelli nei periodi di range, rispetto ai costi? Distribuzione (percentili) delle ampiezze dei range sulle barre 5m/15m, durata dei range, frequenza delle rotture. Se l'ampiezza tipica non supera nettamente i 16 bp (meglio: un multiplo), il ping-pong non può pagare e lo dici subito.

**Fase 1 — schede da specificare** (regole numeriche fisse, una per riga, lato specchiato dove ha senso, ognuna con il suo controllo casuale):
1. L1 rimbalzo su media importante nel trend (pullback; esiste S4: lordo ≈ 0, parti da lì e dalla sua inversione).
2. L2 rimbalzo su supporto / rifiuto su resistenza (livelli da massimi e minimi di oscillazione: definisci tu come e con quanti tocchi).
3. L3 rottura di resistenza con volume, con e senza retest.
4. L4 ping-pong in range (rilevatore di range: ampiezza minima in multipli dei costi, ADX/larghezza Bollinger/numero di tocchi; ingresso ai bordi; uscita sul bordo opposto o a metà; **stop fuori dal range**; esclusione quando il range si rompe).
5. L5 inversione: dopo un'uscita in profitto al bordo, entrata opposta nello stesso punto. Serve un'**eccezione alla pausa dopo l'uscita** (oggi c'è un cooldown sullo stesso simbolo): proponi la regola e contane i costi.
6. L6 triangoli/bandiere con adattamento di linee di tendenza: ultima priorità, la più rumorosa.
Per ciascuna: timeframe, simboli ammessi, stop, obiettivo, uscita a tempo, massimo posizioni, regime in cui è ammessa.

**Fase 2 — backtest e piano per l'ombra.** Storico dei 27 simboli (verifica quanto ne abbiamo: il laboratorio ha 53 coppie con ≥365 giorni di 1h; per i 5m verifica la disponibilità). Poi il piano per misurare le stesse schede **in avanti** in ombra, accanto all'AI.

## 4. Criteri fissati PRIMA dei risultati (cambiarli dopo averli visti non vale)
- Costi: scenari round trip 12 / 16 / 20 bp; funding secondo il motore. Ingresso all'**apertura della barra successiva** al segnale; solo barre **chiuse**; **stop prima del TP** nella stessa barra; una posizione per simbolo.
- Periodi cronologici sviluppo / validazione / test; **ultimi 60 giorni intoccati**, da usare una sola volta e solo se qualcuna supera le soglie.
- Soglie del pool (K = numero di schede, fissato prima); storico = solo informativo, la conferma è il paper in avanti.
- Cluster: i trade dello stesso giorno/crollo non sono indipendenti. Riporta intervalli per giorno (bootstrap per blocchi), non solo per trade.

## 5. Che cosa misurare per ogni scheda
n, lordo e netto in bp, R, win rate, MAE/MFE, per lato, per regime (trend / range), per simbolo, per ora UTC; numero di trade al giorno (serve all'obiettivo dei 400–500); quota di uscite per rottura del range; costo medio di un'inversione; quota di trade "a cavallo" della barra d'ingresso (approssimazione E).

## 6. Domande aperte per te
1. Dove registrare **entrambi i lati** per ogni candidato: oggi il registro ha il lato vincente; propongo di aggiungere `long_score` e `short_score` (e i livelli) ai `candidate`. Tocca il codice dei bot: **non farlo tu e non lo faccio io finché non decidiamo chi.**
2. Come rappresenti i livelli e i range in modo deterministico e testabile (niente "occhio").
3. Conviene che le schede girino dentro il pool esistente o come processo separato in ombra (come il Turbo)?
4. L'esito più probabile secondo il documento del pool è "nessuna scheda idonea". Dimmi onestamente quale stima ti sembra ragionevole e quali schede ti sembrano più promettenti, e perché.

## 7. Collegamenti
- AI economica in ombra 24 ore (candidata `deepseek-flash` a pagamento, ~0,4–0,8 $/giorno stimati con il prompt attuale; Gemini gratuito da verificare): serve un **formato di scheda** che anche l'AI possa leggere (livelli, range, lato, motivo). Lo definisci tu, io costruisco il processo e il registro.
- Le correzioni LIVE e la soglia 63 sono su `work/salto-qualita` (`218aa48..a0fa052`, `a0fa052..a08afa4`, `79d56cf`): revisione separata, non dipende da questo brief.
- Profit Manager in ombra: la decisione "tenere o chiudere" con punteggio di convinzione e pavimento monotono è una fase a parte (`piano-tecnico-cervello-professionale`).
