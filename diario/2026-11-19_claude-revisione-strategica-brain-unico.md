# Claude — Revisione strategica indipendente Brain Unico e Smart Profit Guardian v2

**Data:** 19/11/2026 · **Autore:** Claude Code (Opus 5.5) · **Natura:** solo giudizio; nessuna PR, nessun branch in revisione modificato, nessun dato reale, nessuna azione VPS.

**Fonti lette:** Issue #113 (commenti), diario fino a `113b67c`, PR #117 `6dcdedc`, PR #118 `0833c0d`, PR #119 `d6ed73d`, codice V3 della PR #112 `86288a3` (`risk.py`, `runner/daily_loss.py`, `runner/post_ai_guard.py`, `runner/open_serial.py`, `brain_accounting.py`, `learning/expectancy.py`, `learning/opportunity.py`, `brain_f2/reviewer.py`, `arena/selective_advisors.py`, `arena/configs/deepseek.json`), report Smart Profit Guardian (PDF letto in sessione precedente).
**Non letto:** report Grok (non disponibile in sessione: le sue idee sono valutate solo come riportate nell'incarico). **Limite:** il codice V3 è quello della PR #112; il commit in esecuzione sulla VPS non è verificato.

## 1. Giudizio indipendente

1. **Il problema principale non è il Guardian, è l'edge d'ingresso.** Oggi nessun dato dimostra che DeepSeek abbia EV netto positivo. Il Guardian può ridurre code e restituzioni, non creare rendimento (lo mostra la simulazione PR #119: senza dipendenza tra trade, nessuna regola di stop aumenta l'EV).
2. **Il profilo di rischio Arena è in conflitto con "leva come possibilità".** `min_leverage: 20` più `max_loss_margin_fraction: 0.214` impongono che la leva determini lo stop, non il contrario. Con costi 16 bp andata/ritorno:

   | Leva | Stop massimo | Costi / perdita | Win rate di pareggio (TP = 2× stop) |
   |---|---|---|---|
   | 50× | 0,27 % | 37 % | 53 % |
   | 20× | 0,91 % | 15 % | 39 % |
   | 10× | 1,98 % | 7 % | 36 % |

   A 50× lo stop sta dentro il rumore di 1–5 minuti e più di un terzo della perdita sono costi. Con `min_leverage 20` ogni setup con stop strutturale > 0,91 % è vietato.
3. **Le soglie in USDT perdono senso con il rischio deciso (1–1,5 %).** Espresse in R (perdita massima per trade):

   | Rischio/trade | +300 | +400 | +500 | perdita 50 % (halt attuale) |
   |---|---|---|---|---|
   | 4,29 % (Arena) | 3,5R | 4,7R | 5,8R | 11,7R |
   | 1,5 % | 10R | 13R | 17R | 33R |
   | 1 % | 15R | 20R | 25R | 50R |

   Con 1–1,5 % le soglie A (+400/+500) e B di Grok (+15/+20 %) non scatterebbero quasi mai: protezione inerte. Le soglie vanno espresse in R o in % di equity coerente con il rischio, non in USDT.
4. **Il freno giornaliero esistente è troppo largo.** `daily_loss_halt_fraction 0.50` (decisione 5/11) = 1.000 USDT su 2.000; insieme al pavimento 450 lascia perdere fino a ~1.550 USDT. Nella simulazione PR #119 l'unica regola che migliora le code è un limite di perdita di sessione stretto. Questo pesa più di qualsiasi profit lock.
5. **La contabilità non è ancora mark-to-market verificabile.** `brain_accounting.py` dichiara esplicitamente che il journal ha solo chiusure realizzate; `daily_loss.py` usa l'ultimo minuto chiuso e, **se manca il prezzo, conta solo il realizzato**: per il Guardian questo è fail-open e va invertito.
6. **Molto è già implementato:** motore di rischio deterministico con rischio aggregato, buffer di liquidazione, costi e pavimento (`risk.py`); ricontrollo post-AI e scrittore singolo (`post_ai_guard.py`, `open_serial.py`, candidato P0); freno giornaliero persistente; scoreboard di expectancy con bootstrap a blocchi (`expectancy.py`); etichettatura dei NO_TRADE (`opportunity.py`); pianificatore di consulenti selettivi (`selective_advisors.py`). Non va riscritto: il Guardian e l'anti-reentry devono essere **input** di `risk.py`, non un motore nuovo.
7. **Manca** (e nessuno dei report lo mette al primo posto): lo snapshot causale delle feature nella decisione, il `thesis_id`, i segnali osservati e scartati. Senza questi non c'è apprendimento, né filtro EV, né misura E0 in forward.

## 2. Le tre modifiche più importanti

1. **Registro decisionale v2** (additivo al journal V3): feature al momento della decisione, `thesis_id`, `reentry_index`, `screened_signal` / `full_decision`, rifiuti con motivo, costi stimati. Collegare `opportunity.py` per etichettare NO_TRADE e rifiutati.
2. **Profilo di rischio v2** (configurazione + piccole modifiche): rischio 1–1,5 %; `min_leverage` a 1 (leva = output di stop, rischio, liquidazione); limite di perdita di sessione in R (ipotesi −3R) come freno operativo, il 50 % resta solo come limite esterno; pavimento 450 invariato; contabilità MTM fail-closed (prezzo mancante o vecchio ⇒ nessuna nuova apertura).
3. **Filtro EV + Guardian C + anti-reentry come gate deterministici** che riducono il budget di rischio passato a `risk.py`. Il filtro EV usa lo scoreboard esistente: cella negativa ⇒ veto; cella insufficiente ⇒ "budget esplorativo" a rischio ridotto (ipotesi 0,5R, massimo N al giorno), così l'apprendimento PAPER non si blocca; cella positiva ⇒ rischio pieno. La probabilità dichiarata dall'LLM non entra mai nel sizing.

## 3. Architettura minima

```
dati mercato ─► screener deterministico (detectors/, nessun LLM) ─► screened_signal (sempre registrato)
                         │ candidato
                         ▼
                 DeepSeek (decisore: LONG/SHORT/NO_TRADE, stop strutturale, tesi)   Falco = feature, non voto
                         ▼
   gate deterministici, in ordine:  dati/MTM freschi → limiti globali (450, perdita sessione, daily) →
                                    Guardian (budget) → anti-reentry → filtro EV → risk.py (size/leva)
                         ▼
          post_ai_guard + open_serial ─► executor PAPER ─► exit service (indipendente, mai fermato)
                         ▼
             journal V3 append-only (decisione v2) ─► outcomes/expectancy/opportunity ─► dashboard unica
```

| Componente | Giudizio |
|---|---|
| DeepSeek decisore | Necessario; trattarlo come generatore di tesi, non come stimatore di probabilità |
| Risk engine, exit service, journal | Necessari, **già esistenti** |
| Guardian, anti-reentry, filtro EV | Necessari, piccoli moduli puri che riducono il budget |
| Falco SHORT | Utile come feature registrata; nessun voto |
| Claude revisore | Ridondante finché non c'è prova; resta zero chiamate |
| FreeLLMAPI shadow | Prematuro: aggiunge dipendenza senza SLA mentre manca la baseline. Alternativa a costo zero: valutarlo **offline** sugli snapshot del registro v2 |
| Modello quantitativo addestrato | Non ora (soglie Issue #113: ≥300 esempi/20 giorni). Fino ad allora il "modello" è lo scoreboard |
| Guardian adattivo D | Troppi parametri senza dati: ultimo |

## 4. Politica del Guardian da testare per prima

**C — Risk Budget Scaling**, in unità R, come braccio principale; **B in R** come confronto; **A (+400/+500)** come riferimento storico; **D** solo dopo.

Motivi: C agisce continuamente (anche su profitti piccoli, come chiedi), non ha soglie a gradino da sovra-ottimizzare, ed è una sola funzione `moltiplicatore_rischio(profitto_sessione_R, drawdown_dal_picco_R)` che riduce il budget passato a `risk.py`. Ipotesi iniziale da approvare: rischio pieno fino a +2R, poi rischio nuovo = max(0, (equity − floor)/k) con floor = picco − 25 % del guadagno; LOCKED quando il budget scende sotto 0,5R. Nessun override AI.

Confronto senza nuovi wallet: durante il PAPER finale le politiche B e A si calcolano come **bracci ombra deterministici** sullo stesso flusso di decisioni (cosa avrebbero bloccato o ridotto), a costo AI zero.

## 5. Sessioni

L'orario conta poco per l'EV; conta avere **un solo calendario**. Oggi `daily_loss`, tetto di spesa e contabilità usano il giorno UTC. Proposta: limiti globali, picco e cooldown continui (mai azzerati); il Guardian rilascia LOCKED al confine di giorno **UTC** (01:00/02:00 a Roma), Europe/Rome solo in dashboard. Le 08:00 Roma richiederebbero di cambiare tre moduli o di gestire due calendari, con il cambio d'ora che sposta il confine. Se E0 mostra un effetto dell'orario, si rivaluta.

## 6. Dati che mancano davvero

1. Copie Fase 0 certificate con ancora esterna (consenso).
2. Feature al momento della decisione (perse nel V3).
3. Serie di equity MTM: ricostruibile offline da candele 1m + posizioni, marcata "ricostruita".
4. Etichette forward dei NO_TRADE e dei rifiutati.
5. Costi effettivi per trade (commissioni, funding, slippage) contro stimati.
6. Motivo delle chiusure manuali.

Non mancano altre opinioni AI. I 3 giorni Arena non bastano per alcuna soglia.

## 7. Conflitti con il codice esistente

- `min_leverage 20` vs leva come possibilità.
- `max_loss_margin_fraction 0.214` vieta stop strutturali con leva alta.
- `daily_loss_halt 0.50` troppo largo rispetto al limite di sessione proposto.
- Fallback "solo realizzato se manca il prezzo" in `daily_loss.py` è fail-open per il Guardian.
- Giorno UTC nel codice vs preferenza 08:00 Roma.
- `brain_decision` senza feature.
- Nessun `thesis_id` né logica di reingresso nel runner/brain_f2 (solo `cooldown_bars` nei detector).
- `open_serial` è dichiarato "candidato P0, NOT enabled": da verificare nel runtime.

## 8. Roadmap breve fino al PAPER

- **R0** (consenso): copie Fase 0 + ancora → builder PR #118 → misura E0.
- **R1:** registro decisionale v2 + etichettatura NO_TRADE.
- **R2:** profilo di rischio v2, MTM fail-closed, limite di sessione in R, `open_serial` attivo.
- **R3:** Guardian C, anti-reentry, filtro EV con budget esplorativo; tutti puri, testati, come input a `risk.py`.
- **R4:** replay causale sugli storici certificati: baseline vs C vs B vs A, split cronologici con embargo.
- **R5:** release candidate, un solo GO/NO-GO, PAPER finale integrato e pre-registrato con bracci ombra.

## 9. Rischi che impedirebbero il LIVE

- EV netto non dimostrato fuori campione.
- Esecuzione PAPER ottimistica (slippage 2 bp, niente fill parziali né rifiuti) e liquidazioni a 50× con gap.
- Contabilità MTM non verificata e nessuna riconciliazione con lo stato dell'exchange.
- Concorrenza tra scrittori di aperture.
- Deriva del modello LLM (versione, provider, non determinismo) e indisponibilità API.
- Backup fuori host non installato.
- Soglie scelte a posteriori sugli stessi dati di valutazione.

## Stato

- **Già implementato** (in PR draft, non verificato a runtime): `risk.py`, `daily_loss.py`, `post_ai_guard.py`/`open_serial.py`, `expectancy.py`, `opportunity.py`, builder PR #118, E0 PR #119.
- **Solo proposto:** tutto il resto di questo documento.
- Nessun backtest qui è un risultato reale; le tabelle sono aritmetica sui parametri di configurazione.
