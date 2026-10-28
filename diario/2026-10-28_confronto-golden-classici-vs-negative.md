# Classici Hawk/Bull — perché sono peggiorati dopo le golden (28/10/2026)

**Per Claude e ChatGPT: analisi solo documentale.** Nessun dato operativo VPS è stato modificato o acquisito con nuovo accesso. Fonti primarie audit del 27/10: `diario/analisi-run-2026-10-27/REPORT.md`, `ENTRIES.md`, `FEES.md`, `run_metrics.json`, `source_provenance.json`. Screenshot utente 28/10 21:56 Italia (correnti, ancora in corso).

## Golden vs negative, posizioni complete

| Profilo e run | Posizioni | P&L netto PAPER | WR per posizione | Lordo medio/trade | Fee media/trade | TP finali | SL finali |
|---|---:|---:|---:|---:|---:|---:|---:|
| Hawk #2 golden | 76 | +1090.61 | 60.5% | +17.02 | 2.67 | 45/76 | 29/76 |
| Hawk #3 prima negativa | 38 | -284.87 | 26.3% | -4.72 | 2.77 | 10/38 | 16/38 |
| Hawk #5 tarda | 112 | -50.81 | 37.5% | +2.02 | 2.47 | 36/112 | 59/112 |
| Bull #1 golden | 17 | +770.75 | 70.6% | +50.05 | 4.72 | 9/17 | 5/17 |
| Bull #2 prima negativa | 15 | -144.68 | 26.7% | -5.16 | 4.47 | 4/15 | 4/15 |
| Bull #4 tarda | 77 | -214.02 | 36.4% | +1.52 | 4.29 | 25/77 | 44/77 |

Dashboard Bull golden 24/30=80% *realizzi* (incluse parziali), non 17 posizioni complete: 12/17 =70.6% WR per posizione. Non confondere unità campionaria.

Screenshot 28/10: Hawk #7 in corso equity878.79 (-121.21 vs 1000), 6 chiuse1/5, P&L chiusi-103.79, massimo DD -151.48; Bull #6 in corso equity879.16(-120.84),4 chiuse0/4, P&L chiusi-120.84. Entrambi runtime mostrato dc16e01; parametri visibili: 12% daily stop; Hawk max10 slot, min margin100, cap250, Bull max3,min150,cap350. Nessuna attribuzione causale della run corrente senza log.

## Che cosa NON ha causato la prima crisi

- Prima coppia negativa dal 16/10: Hawk #3 e Bull #2. Tra run golden e prime negative, codice 5818aee → 18d145f → b4709d1 (macro policy/calendar e disponibilità AI); **C ancora a70, pesi baseline e SL1.2xATR invariati**. Fix A, soglia63, warmup EMA200, P1/P2, Capital Manager V1 sono POSTERIORI al primo crollo.
- Il coefficiente stop1.2 ATR risulta già dal commit 11/10, *precedente* alle golden: non si è stretto da1.5 a1.2 dopo il successo.
- Audit 357/357 entrate source=`rules`, zero aperture source Claude; ciò non dimostra che l'AI non abbia modificato/vetato candidate o chiuso posizioni. Per le uscite fonte effettiva non registrata. Disponibilità Claude Hawk #2 1/47 parsabili vs Hawk #3 56/56, Bull #1 34/48 vs Bull #2 64/64: **forte confondente**, nessun verdetto causale.

## Fattori supportati da evidenza

1. **Regime mercato e lato direzionale**: golden quasi tutte SHORT; BTC nelle 83h golden -0.59%, volatilità giornaliera2.18%; prime negative BTC -0.06%, volatilità1.29% e rendimento alt variabile. Mercato meno volatile e quasi piatto compatibile con stop/TP che perdono efficacia. Run tardive 21–26 tornano bearish e tuttavia non guadagnano: regime non è spiegazione completa.
2. **Lo stesso score non rappresenta lo stesso setup**: Hawk score medio70.57→69.29 e Bull70.00→68.82 golden vs tarde, ma Hawk breakout54/74→20/112; volume53/74→29/112; daily0→39/112. Bull breakout9/15→11/77; volume8/15→14/77; daily0→29/77. Valori score>=75 passano da WR Hawk83.3% a32%, Bull100% su 3 casi a29.4%. Non ripristinare una soglia come se fosse una probabilità calibrata.
3. **Uscite meno efficaci e costi**: Hawk TP45/76→36/112, SL29/76→59/112; Bull TP9/17→25/77, SL5/17→44/77. Il lordo medio collassa prima delle fee. Fee/notional sostanzialmente invariata; non correggere aumentando leva come soluzione.
4. **Concentrazione/rischio**: 2 liquidazioni pesanti precedenti Fix A: Hawk #4 NEAR -101.50, Bull #3 INJ -194.88. Priorità LIQ su SL nei bar OHLC con sequenza intrabar non osservata, possibili artefatti del modello PAPER da verificare in replay 1m/tick prima di determinare responsabilità.

## Giudizio di governance

Errore processuale confermabile: molti aggiornamenti con metriche prima/dopo e regimi diversi, senza congelare una baseline golden e testare ogni mutamento in parallelo su esattamente gli stessi dati con replay controfattuale. Non è dimostrato che la modifica di un singolo parametro abbia distrutto il vantaggio. Per migliorare: conservare immutato il codice classico ora in PAPER; replay separato golden vs dc16e01 sul medesimo feed registrato point-in-time; analizzare exit source, mutazioni SL/TP, costi, posizione condivisa, regime e lato; confrontare aspettativa NETTA, DD e volume per tranche/posizione; includere periodi bullish/sideways/downside. Brain Scalp dual indipendente non deve ereditarne automaticamente score e fallback senza validazione.

**Nessun deploy/reset/cambio ai bot è autorizzato o eseguito da questa analisi.**

AI: chatgpt (chat normale)
