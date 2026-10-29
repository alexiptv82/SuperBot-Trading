# Modifica long (P1): esito del laboratorio — 29/10/2026 (Claude)

**Verdetto in una riga:** la modifica P1 non e' una correzione dei long e non va rilasciata; nessuna delle versioni nuove
(v2) supera i criteri fissati prima dei risultati; il codice del 13/10 resta com'e'. Nessun bot, deploy o file di
produzione toccato (ramo isolato `work/long-lab-claude-20261029`, mai unito a `rule-pool`).

## Cosa e' stato misurato
- Codice VERO del 13/10 (`desk.signals.read_symbol`, `desk.brain.rules_decisions`, `desk.engine.PaperAccount`), 26 simboli,
  candele 15m pubbliche Bitget da maggio 2025 a ottobre 2026 (~18 mesi, 5000 trade simulati per variante), costi del
  motore (16 bp a giro), soglie come in produzione (60 BTC/ETH/oro/argento, 70 le altre), cadenza 30/15 minuti.
- Il punteggio del laboratorio e' identico a `read_symbol` (test numerico barra per barra, anche con P1 applicata).
- Criteri G1–G9 scritti in `PREREGISTRAZIONE.md` PRIMA di vedere i risultati; due errata dichiarate dopo (placebo della
  famiglia sbagliata, corretto; controlli aggiunti per capire). Tabelle complete in `results/report.md`.

## Risultati
1. **Il bonus "rimbalzo" di P1 non cambia nulla.** Scatta 4240 volte in 18 mesi, ma quando scatta il punteggio long e' mediano 0–1
   (massimo 37) contro uno short di ~57: +10 punti non portano mai un long sopra soglia. 22–26 decisioni cambiate, **0 nuovi long
   aperti**, trade e netto identici al 13/10.
2. **Il peso 4h 20→14 non e' una correzione long: e' "apri meno".** I trade scendono da 5084 a 2529 (−50%) e il netto sale di
   +9900$ solo perche' ogni trade medio perde (R per trade peggiora: −0,181 contro −0,160). Alzare le soglie di 6 punti
   fa lo stesso (+9000$). Una P1 con il bonus a caso fa lo stesso (+9700$ mediana dei placebo): fallisce G5 e G7. Se il
   bot invece guadagnasse per trade, dimezzare le aperture dimezzerebbe il profitto: l'effetto dipende dal segno di
   qualcosa che P1 non tocca.
3. **Il segnale di rimbalzo non ha vantaggio proprio.** Long dopo "RSI<35 e mom1h>+0,3%" su 4240 eventi: −0,196 R contro
   −0,179 R di un'entrata a caso (differenza non significativa); su BTC/ETH/oro/argento −0,43 R (significativamente peggio).
   Coerente con la letteratura: Zaremba et al. 2021 (Int. Rev. Financial Analysis) trovano inversione solo nelle crypto poco
   liquide e momentum nelle piu' grandi (orizzonte giornaliero).
4. **Versioni nuove (v2), nessuna passa.** `g_long` (long solo se il regime e' su): +1700$ ma peggio di un filtro a caso
   (placebo mediano +6800$ e secondo +8100$): i long che il filtro lascia passare, quelli in regime "su", sono proprio i piu' perdenti (R −0,25 su 1449 trade). `t_bonus` (+10 al lato
   dell'inversione di mercato confermata, simmetrico): batte il suo placebo e lordo e' positivo (+0,024 R, +5200$ senza costi),
   ma netto e' solo +900$ con intervallo [−2900, +5200] che include lo zero, e con la stagionalita' storica (S1) diventa
   −230$ (G3, G9 falliti). E' l'unico filone con un segnale lordo: vale un test a parte, non un rilascio. `r_reb` (rimbalzo confermato)
   e `ref_gate` (filtro di regime su entrambi i lati) non superano il caso.
5. **Il punteggio di base non ha potere predittivo misurabile.** Senza costi il bot del 13/10 e' a R −0,004 (PF 0,96): le
   commissioni (~0,16 R a trade) decidono il segno. I trade con punteggio piu' alto non rendono di piu' (short su altcoin:
   −0,04 R a 60–64, −0,21 R a 80+). 16 mesi su 18 chiudono in perdita nella replica.

## Calibrazione e limiti (da leggere prima di fidarsi dei valori assoluti)
- **La replica non riproduce l'entita' dei giorni d'oro.** Struttura e lato dei trade tornano (12–26/10: 203 trade, 11 long e
  192 short nella replica, contro 247 aperture reali, 13 long e 234 short), ma nel periodo d'oro la replica fa R +0,06 e 43% di
  vittorie (12–16/10, 67 trade), i bot veri R +0,54 e 61% (12–15/10, 89 trade, 87 short e 2 long). Finestre non identiche,
  ma il divario resta. Cause possibili (non misurate): il bot
  vero rivaluta ogni ciclo la candela in formazione e salta la parte della candela d'ingresso; il lavoro di Claude nelle
  chiusure; il tempismo. **Il valore assoluto della replica (−0,16 R) e' quindi probabilmente pessimista; i confronti tra varianti
  sullo stesso banco restano validi.**
- Un solo periodo di mercato (18 mesi); i long reali del 12–26/10 sono solo 13: nessuna conclusione dal campione reale.
- Il laboratorio simula solo le regole (come nei giorni reali: Claude non aveva aperto nulla).

## Raccomandazione (decisioni dell'utente)
1. P1 resta in stand-by e non si rilascia; la si puo' considerare chiusa. Nessuna v2 da rilasciare.
2. Prima di qualunque cambio di strategia conviene un **test di fedelta' con candele da 1 minuto** (solo laboratorio): dice se i
   giorni d'oro dei bot veri sono riproducibili o se il paper e' ottimista rispetto a un'esecuzione reale — conta soprattutto prima del live.
3. Poi un laboratorio "dove guadagna il bot" (condizioni di mercato, costi/ordini limit, soglie), con pre-registrazione e
   validazione fuori campione, in linea con l'idea "non perdere la base" e i giorni da 100$.
