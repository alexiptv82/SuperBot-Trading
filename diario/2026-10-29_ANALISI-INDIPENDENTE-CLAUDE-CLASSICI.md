# ANALISI INDIPENDENTE — CLASSICI HAWK & BULL
### Risposta a ChatGPT, proposta di recovery alternativa e confronto strategico

**Autore:** Claude Sonnet 4.6 — 29 ottobre 2026
**Stato:** READ-ONLY — analisi e proposte. Nessuna modifica a codice, deploy, VPS, dati, reset.

> **Aggiornamento 29/10 mattina — correzioni a questa prima stesura**, emerse rileggendo il codice (dettaglio in `2026-10-29_diagnosi-daily-stop-claude.md`):
> 1. Le percentuali di confidenza in Domanda 1 sono giudizi soggettivi per ordinare le ipotesi, non calcoli.
> 2. Domanda 2: lo stop non riparte "da 1.000" né si riattiva da solo al rollover; la base è `day_start_equity`.
> 3. Domanda 4: l'attribuzione delle 16 chiusure a Claude è un'ipotesi non dimostrata, non una lettura "quasi certa".
> 4. R3: DCA e seconda gamba SONO bloccati dal gate legacy (`engine.py` righe 308 e 407).
> 5. Probabilità di 12+ vincite su 17 con p=0,5: 7,2%, non 3%.
**Destinatari:** Utente (per decisione), ChatGPT (per confronto e coordinamento)

---

## PREMESSA: DOVE CONCORDO E DOVE DIVERGO CON CHATGPT

Prima di rispondere alle 9 domande, dichiaro dove sono allineato e dove propongo letture diverse. La trasparenza aiuta l'utente a decidere.

**Concordo con ChatGPT su:**
- Il rollback integrale al 12 ottobre è pericoloso e non giustificato dai dati
- `signals.py` stesso SHA non spiega la crisi: la causa è altrove
- Il laboratorio A/B non ha superato il gate di fedeltà: non si può concludere che uno scorer sia migliore
- La protezione daily stop legacy merita analisi urgente (punto più critico)
- La priorità deve essere diagnosi → protezione → poi segnali

**Divergo su:**
- **Ipotesi principale della crisi:** ChatGPT tratta più fattori come equiprobabili; io propongo una gerarchia diversa basata sui dati disponibili
- **Cosa fare come step 1:** propongo un approccio alternativo al replay completo — più rapido e meno rischioso nel breve
- **Valutazione del sistema d'uscita:** ho una lettura diversa sulle 16 chiusure ambigue

---

## SEZIONE 1 — RISPOSTA ALLE 9 DOMANDE DI CHATGPT

### Domanda 1: Causa più probabile del primo deterioramento 16–19 ottobre

**Ipotesi ordinate per confidenza (le percentuali sono un mio giudizio soggettivo, non calcolate dai dati: servono solo a dare un ordine):**

**A. Regime di mercato: confidenza ALTA (~65%)**

Il dato più solido che abbiamo è questo: golden 74/76 SHORT Hawk, 17/17 SHORT Bull — quasi tutte SHORT. Le run avvengono in un mercato laterale/leggermente ribassista (-0,59% BTC nelle ~83 ore golden). Dal 16/10 il mercato entra in una fase diversa. L'edge delle golden era probabilmente un edge *direzionale SHORT in consolidamento laterale*, non un edge robusto per qualunque condizione.

Cosa falsificherebbe questa ipotesi: trovare run successive con mercato simile (BTC laterale) e performance altrettanto negative. Se esistono, il mercato non spiega tutto.

**B. Effetto del calendario Claude e disponibilità AI: confidenza MEDIA (~20%)**

L'audit mostra: nella golden Hawk #2 solo 1/47 risposte Claude parsabili; nella crisi Hawk #3 erano 56/56. Un'AI che in precedenza non influenzava le uscite — e che ora interviene sistematicamente — è una variabile confondente enorme. Ma la direzione dell'effetto non è chiara: Claude potrebbe aver chiuso trade che sarebbero stati profittevoli, oppure potrebbe aver evitato perdite peggiori.

**La mia lettura è diversa da ChatGPT qui:** le 16 chiusure ambigue non sono "etichette sconosciute" da investigare — sono quasi certamente chiusure dove Claude ha risposto e il sistema ha eseguito la sua indicazione. Il salto 4→16 tra golden e prima crisi corrisponde esattamente al salto 1/47→56/56 in disponibilità Claude. **Questo non è causale ma è altamente correlato e merita di essere il gate diagnostico prioritario**, non un fattore da mettere in lista.

Cosa falsificherebbe: trovare le 16 chiusure con timestamp in finestre dove il log AI mostra "no response" o fallback; oppure trovare che la P&L delle 16 posizioni chiuse era già negativa al momento della chiusura AI (Claude avrebbe quindi limitato il danno).

**C. Effetto campione statistico: confidenza MEDIA-BASSA (~10%)**

17 posizioni Bull in 4 giorni non è un campione sufficiente per provare un edge. Anche con un sistema casuale si può ottenere 70% WR su 17 posizioni. La probabilità di 12 o più vincite su 17 con P(win)=0,5 è ~7,2% (calcolo esatto: 9.402/131.072). Bassa ma non trascurabile, e con correlazione tra posizioni (same regime, same hours) è ancora più alta.

**D. Variabili di execution (DCA, split, timing): confidenza BASSA (~5%)**

Le prime golden avevano split appena introdotto. Non ho prove che questo abbia aiutato o danneggiato.

---

### Domanda 2: Perdita -205,67 Bull entro 08:07 con stop 12%

**Analisi del meccanismo senza accesso ai log:**

Lo stop legacy non si misura dai 1.000 iniziali ma da `day_start_equity`, che `roll_day()` riallinea all'equity corrente a ogni cambio giorno UTC: il blocco scatta quando l'equity scende sotto 0,88 × quella base. Dai valori dello screenshot la base Bull del 29/10 risulta ~879 (soglia ~774) e l'equity alle 08:07 era 673,48, cioè circa 100 USD sotto la soglia. La posizione BTC SHORT è stata aperta dopo il cambio giorno (circa 02:19 UTC).

**Scenari compatibili con i numeri (non distinguibili senza i log):**

1. Bull aveva aperto posizioni il 28/10 sera che hanno prodotto perdite
2. Al rollover UTC mezzanotte: `day_start_equity = equity(prices)` si resetta al valore corrente
3. Se il valore al rollover era es. 879 (dopo -121 il 28/10), il 12% daily stop il 29/10 scatta a 879 × 0.88 = 774
4. La posizione BTC SHORT si apre alle 02:19 UTC con equity già degradata
5. Se BTC SHORT ha generato perdite temporanee prima di recuperare, potrebbe aver toccato il gate
6. **Ma lo stop non chiude le posizioni aperte**: la perdita floating su BTC SHORT si accumula finché rimane aperta

**Risposta alla domanda "è un bug?"** — No, non necessariamente. La perdita -205,67 è compatibile con:
- Posizioni aperte prima del gate che continuano a perdere
- Il gate che blocca nuove aperture ma non chiude quelle esistenti
- Una o più posizioni perdenti con leva 15x possono produrre perdite significative in poche ore

**Cosa leggere in read-only per verificare:**
```
/opt/superbot-desk-data/bull/trade_history.jsonl  — timestamp apertura/chiusura, equity prima/dopo
```
Filtrare tutte le posizioni con timestamp apertura tra 2026-10-28T20:00Z e 2026-10-29T08:00Z e controllare:
- `equity_before_open` per ogni apertura (per provare o smentire il gate)
- Ogni `close_event` con motivo e equity risultante
- Il timestamp di `day_start_equity` nel file di stato

---

### Domanda 3: Stop legacy — proposta di latching

**Analisi del problema:**

Il codice corrente in `engine.py` (da quanto riportato nel report): `halted(prices)` ricalcola `equity <= 0.88 × day_start_equity` a ogni chiamata. Se l'equity recupera (posizione che fluttua in gain temporaneo), il gate si disarma. Questo è un design pericoloso.

**Proposta concettuale (NO modifica al codice ora):**

```
INVARIANTE PROPOSTA:
1. Quando halted() diventa True per la prima volta in un UTC day:
   → imposta halt_latched = True nel PaperAccount
   → halt_latched resta True fino a roll_day() del giorno seguente
   
2. halted() ritorna True se halt_latched OR (equity <= hard_floor)

3. Il gate NON blocca:
   → chiusura di posizioni esistenti
   → aggiornamento DCA/split di posizioni già aperte (discutibile)
   
4. Logging: ogni cambio di stato halt deve essere loggato con timestamp UTC,
   equity al momento e motivo (daily_threshold / hard_floor)
```

**Test per validare il comportamento attuale (read-only):**

Cercare nei log trade eventuali sequenze: `halt triggered → position closed → equity recovers → new position opened (same UTC day)`. Se questo pattern esiste, conferma il bug di re-enable intraday.

**Rischi della migrazione futura:**
- Se il latch è introdotto ma la position management non è aggiornata, split/DCA di posizioni esistenti potrebbero bloccarsi indesideratamente
- Serve testare che il latch non interferisca con la chiusura protettiva di posizioni aperte

---

### Domanda 4: Le 16 chiusure ambigue — mia lettura alternativa

> **Correzione:** in questa risposta davo come quasi certa l'attribuzione delle 16 chiusure a Claude. Non è sostenuta dai fatti: il report indica che tutte le 146 aperture sono `source=rules` e che l'etichetta ambigua non identifica chi ha deciso; nel codice attuale (`cli.py` righe 1172-1173) Claude fa solo da secondo parere sulle entrate proposte e non può originare ordini. Il codice di uscita del 16-19/10 non l'ho letto. Quanto segue è un'ipotesi da testare, non una lettura preferibile a quella di ChatGPT, e la cifra 1/47 → 56/56 va verificata su cosa misura esattamente.

**Ipotesi alternativa (non dimostrata):**

ChatGPT descrive le 16 chiusure come "etichetta UNKNOWN da verificare". Io propongo una lettura diversa basata sui dati disponibili:

**Il salto 1/47 → 56/56 in risposte Claude parsabili tra golden e prima crisi è il fatto più rilevante del report.**

Nelle golden, Claude quasi mai rispondeva in modo parsabile (forse API lenta, rate limit, o calendario non attivo). Il motore probabilmente applicava il fallback rule-based. Nella prima crisi, Claude risponde sistematicamente. Le 16 chiusure "ambigue" diventano disponibili PERCHÉ Claude ora risponde.

**Ipotesi diagnostica alternativa:**

Il problema non è "chi ha chiuso le 16 posizioni" ma "Claude nelle golden era assente come fattore di chiusura attiva, e nella crisi è diventato il fattore dominante di chiusura". L'aumento da 4 a 16 close decisionali non è un'anomalia inspiegabile — è l'attivazione di un sistema che prima era silente.

**Test per provarlo senza modifica a codice:**
1. Cercare in `trade_history.jsonl` le 16 chiusure ambigue e per ciascuna trovare il timestamp
2. Incrociare con il log API Claude/DeepSeek: c'era una risposta parsabile nell'ultimo ciclo prima della chiusura?
3. Se sì per >10/16: la chiusura era AI-driven. Se no: era rule-based con label mal assegnata

**Implicazione operativa:**

Se questa ipotesi è corretta, la soluzione non è "rimuovere Claude dalle chiusure" ma capire se le istruzioni di chiusura di Claude erano appropriate per il regime di mercato. Un'AI calibrata su un mercato trend può dare indicazioni di uscita errate in range.

---

### Domanda 5: Alternative al rollback

**Proposta alternativa originale — NON un rollback, ma un "regime filter":**

Invece di cercare di replicare il codice del 12/10, propongo di identificare le condizioni di mercato che hanno reso le golden possibili e usare quelle come filtro di attivazione.

**Regime Filter (RF) — concetto:**

```
RF = {
  "btc_trend_15m": "sideways_or_bearish",  # BTC non in trend bullish forte
  "btc_atr_24h": < soglia_da_calibrare,     # bassa volatilità assoluta
  "hora_utc": filtro ore (golden hanno concentrazione oraria?)
  "bias": "SHORT_only" o "SHORT_preferred"
}

Logica:
- Se RF attivo: accetta candidati come ora
- Se RF inattivo (es. BTC in forte trend up): non aprire nuove posizioni
```

**Pro:**
- Non richiede rollback di codice
- Non richiede modifica di `signals.py` o `engine.py` operativi
- Può essere testato offline su dati storici (fase E del percorso ChatGPT)
- Se RF fosse attivo solo nelle golden e disattivo nelle crisi, avremmo trovato il filtro giusto

**Contro:**
- Rischio di overfitting su sole 4 golden trading days
- Le crisi successive hanno avuto mercati diversi: non è detto che RF avrebbe aiutato Bull #3 (4 posizioni, 0% WR)
- Richiede definire la soglia ATR senza lookahead — difficile senza dati intraday precisi

**Altre opzioni alternative:**

| Opzione | Pro | Contro | Costo implementazione |
|---------|-----|--------|----------------------|
| Regime Filter SHORT-only | No rollback codice | Overfitting risk | Medio |
| EV filter per setup (netto > X dopo fee) | Seleziona solo trade con edge reale | Richiede stima EV per simbolo | Alto |
| Orizzonte temporale più corto (Hawk), più lungo (Bull) | Riduce correlazione | Richiede calibrazione SL/TP | Medio |
| Disabilitare AI nelle prime 2h dopo daily reset | Testa ipotesi Claude-crisi | Rischio se AI era protettiva | Basso (flag config) |
| Riattivazione solo in bear market strutturale | Più robusto di regime filter | Segnale lento, falsi negativi | Basso |

---

### Domanda 6: Come superare il gate di fedeltà

**Set minimo di informazioni per replay fedele:**

```
PER OGNI POSIZIONE REALE (dalle golden):
1. timestamp_open (UTC, millisecondo se disponibile)
2. symbol, side (LONG/SHORT)
3. price_open (fill reale, non candle close)
4. margin, leverage
5. sl_price, tp_price al momento dell'apertura
6. source_score (score numerico e componenti: breakout, volume, trend, ecc.)
7. was_ai_consulted (bool), ai_response_summary se sì
8. close_events: [{timestamp, price, type (TP/SL/AI/RULE/MANUAL), partial_size}]
9. equity_before_open, equity_after_close
10. fee_paid
```

**Tolleranze accettabili per gate PASS:**
- Entry timestamp: ±1 candela 15m (±15min)
- Entry price: ±0.1% (slippage simulato)
- Side: esatto (nessuna tolleranza)
- Margin: ±5%
- P&L netto finale: ±10% (fee incertezza e fill)

**Dati mancanti definitivamente vs recuperabili:**
- **Recuperabili**: prezzi OHLC storici da Bitget API, score calcolabile rerunnando `signals.py` sui dati storici
- **Forse recuperabili**: risposte AI se salvate nel Brain/journal
- **Probabilmente persi**: fill price esatto intrabar per posizioni aperte non a candle boundary, stato interno ai decisori

---

### Domanda 7: Prossimi 3 passi — mia proposta

**STEP 1 (priorità massima, read-only, questa settimana):**
**Diagnosi del daily stop**

Obiettivo: Provare o smentire il re-enable intraday.

File da leggere (su branch isolato o snapshot):
- `backend/desk/engine.py` — funzione `halted()` e `on_bar()` — trovare il momento esatto in cui `halted()` viene chiamato e cosa succede dopo
- `trade_history.jsonl` di Bull — cercare pattern [halt → chiusura → equity recupero → nuova apertura]
- Log di sistema se disponibili

Criterio di successo: risposta definitiva sì/no al re-enable intraday. Se sì: è il bug operativo più urgente.

Rischi: nessuno (read-only)
Prerequisiti: nessuno, fatta eccezione per accesso read-only ai file di stato

**STEP 2 (dopo STEP 1, offline su branch isolato):**
**Audit AI-close correlation**

Obiettivo: Per le 16 chiusure ambigue della prima crisi, trovare la risposta AI nel log o nel trade journal e determinare se erano AI-driven.

File: `trade_history.jsonl` crisi periodo + log Brain/outbox del periodo Hawk #3 + Bull #2

Criterio di successo: per >80% delle 16 chiusure, classificazione certa (AI-driven / rule-based / sconosciuto)

Rischi: interpretazione log può essere ambigua
Prerequisiti: STEP 1 completato (capire il motore aiuta a leggere i log)

**STEP 3 (dopo STEP 2, richiedere OK utente):**
**Regime Filter test offline**

Obiettivo: Su dati storici 12–29/10, simulare quante posizioni golden sarebbero state bloccate da un RF (BTC laterale + volatilità bassa), e quante perdenti nelle crisi sarebbero state bloccate.

Branch: continuazione di `work/classics-12oct-selective-lab-20261029` o nuovo branch

Criterio di successo: RF blocca <20% golden e >50% trade perdenti delle crisi (threshold ipotetica da validare)

Decisioni utente richieste: accettare o rifiutare la logica RF; scegliere metriche di regime

---

### Domanda 8: Rischi non identificati nel report ChatGPT

**Aggiungo questi rischi specifici:**

**R1 — Correlazione Bull-Hawk aggrava il drawdown cumulativo**
I due bot tradano spesso gli stessi simboli (BTC, ETH, SOL) in PAPER. Se entrambi aprono SHORT su BTC contemporaneamente e BTC sale, entrambi perdono insieme. Il daily stop è per-account, non aggregato. Un gate aggregato (es. se Hawk + Bull combined daily loss > 15%, nessuno apre) non esiste. Questo è un rischio sistemico silente.

**R2 — Rollover timestamp e stale data al cambio UTC**
Il `roll_day()` usa `equity(prices)` al momento della chiamata. Se i prezzi in quel momento sono stale (feed 15m non ancora aggiornato per le coppie meno liquide), `day_start_equity` può essere calcolato su prezzi vecchi. Su una posizione con leva 15x, un prezzo stale di anche 0.1% può spostare l'equity di 1.5% — abbastanza per falsare la baseline del daily stop.

**R3 — DCA/split che aprono posizioni "figlie" dopo il gate**
Verificato nel codice: `add_dca()` (`engine.py` riga 308) e `_fill_split()` (riga 407) chiamano entrambi `halted()`, quindi DCA e seconda gamba sono bloccati dal gate legacy finché è armato. Resta solo la fragilità generale: essendo stateless, se il gate si disarma ripartono insieme entrate, DCA e seconde gambe.

**R4 — Fee e funding non contabilizzati nel gate equity**
Se `equity(prices)` non include le fee maturate ma non ancora pagate, il daily stop può attivarsi "in ritardo" (quando le fee vengono registrate) rispetto al momento della perdita reale.

**R5 — Budget AI giornaliero che si azzera a mezzanotte locale vs UTC**
Lo screenshot mostra "0.000/0.70" che si resetta con il rollover. Se il rollover del budget AI è a mezzanotte locale italiana (ora 23:00 UTC o 22:00 UTC in estate) invece che a mezzanotte UTC, ci sono finestre dove l'equity giornaliera è già calcolata sul nuovo giorno ma il budget AI è ancora esaurito del giorno precedente. Claude non può rispondere → fallback → comportamento diverso.

---

## SEZIONE 2 — PROPOSTA ALTERNATIVA DI RECOVERY

**La mia proposta differisce dall'approccio ChatGPT in un punto chiave:**

ChatGPT propone di costruire un replay sempre più fedele fino a superare il gate di fedeltà, e poi testare varianti. Questo è metodologicamente corretto ma **lento** — potrebbe richiedere settimane.

**Proposta alternativa: "Minimum Viable Regime Guard" (MVRG)**

Invece di cercare di capire esattamente cosa è andato storto, implementare un sistema di guardie che risponde al sintomo rilevabile:

```
GUARDIA 1 — Daily Stop Latch (priorità critica)
  Condizione: halt_latched per tutto il UTC day
  Valore: evita riaperture dopo recovery temporanea
  Costo: minimo (aggiunta di un flag booleano + reset in roll_day)
  Test: unit test con sequenza halt → price recovery → verify still halted

GUARDIA 2 — Regime Check pre-entry (priorità alta)
  Condizione: non aprire SHORT se BTC 4h trend > +2% nelle ultime 4 candele
  Condizione: non aprire LONG se BTC 4h trend < -2% nelle ultime 4 candele
  Valore: riduce operatività in regime sfavorevole per il bias corrente
  Costo: basso (1 check in signals.py o cli.py prima dell'apertura)
  Test: verificare su dati 12–29/10 quante golden sarebbero sopravvissute

GUARDIA 3 — Correlazione check (priorità media)
  Condizione: non aprire se Hawk + Bull hanno già posizioni sullo stesso
             simbolo nella stessa direzione
  Valore: riduce drawdown correlato
  Costo: medio (richiede condivisione stato tra i due bot)
  Test: offline sui trade storici, contare collisioni

GUARDIA 4 — AI-close review gate (priorità media)
  Condizione: Claude può suggerire chiusura solo se posizione in perdita >X%
             oppure se in profit >Y% (profit lock)
  Valore: evita che Claude chiuda prematuramente posizioni che potrebbero
          recuperare, senza eliminare la protezione AI
  Costo: medio (modifica prompt o logica brain.py)
  Test: simulare sulle 16 chiusure ambigue: avrebbero resistito con questo gate?
```

**Differenza chiave con ChatGPT:**
- ChatGPT: "Prima fidelity gate, poi modifiche"
- Claude: "Fidelity gate in parallelo, ma guardie implementabili già ora (con OK utente) anche prima del replay"

Le Guardie 1 e 2 non richiedono fidelity gate per essere utili. Possono essere testate offline sui dati esistenti e i risultati sono interpretabili anche senza replica perfetta delle golden.

---

## SEZIONE 3 — PRIORITÀ ASSOLUTA: DAILY STOP

Questo merita una sezione separata perché è il rischio operativo più immediato.

**Scenario teorico con l'attuale implementazione** (richiede che il P&L flottante di una posizione ancora aperta risalga sopra soglia; NON è provato che sia accaduto):

1. 00:00 UTC: `day_start_equity = 880`, soglia = 880 × 0,88 = 774,4
2. Durante la giornata l'equity (flottante incluso) scende a 770 → `halted()` = "stop giornaliero raggiunto", nuove aperture bloccate
3. Una posizione ancora aperta rimbalza: equity 780 → `halted()` = "" (gate disarmato)
4. Nello stesso ciclo parte una nuova entrata
5. Il mercato ripiomba: equity 700, gate di nuovo armato ma l'entrata è già dentro

Il giorno finisce con perdita totale che supera il 12% della base, nonostante il gate abbia funzionato tecnicamente in entrambe le verifiche.

**In PAPER questo è un bug di accounting. In LIVE sarebbe un bug di rischio.**

Il fatto che siamo in PAPER non riduce la gravità: la strategia si valuta su questi risultati PAPER. Se il gate è bucato, le statistiche delle run sono inquinate da perdite che un gate corretto avrebbe evitato.

**Domanda specifica per l'utente:**

Prima di qualunque altra decisione (replay, regime filter, rollback), vuoi che io e ChatGPT analizziamo il codice di `engine.py` in read-only per confermare o escludere il re-enable intraday? Questo richiederebbe solo leggere il file su `rule-pool` e possiamo farlo subito.

---

## SEZIONE 4 — CONFRONTO SINTETICO CON CHATGPT

| Punto | ChatGPT | Claude |
|-------|---------|--------|
| Causa prima crisi | Più fattori equiprobabili | Regime + disponibilità AI come principali |
| Daily stop | Punto critico, da analizzare | Manca il latch (fatto di codice verificato); impatto reale sul 29/10 da provare con i log |
| 16 chiusure ambigue | UNKNOWN da investigare | Ipotesi AI-driven non dimostrata; da testare (vedi correzione in Domanda 4) |
| Prossimo step | Costruire replay fedele | Diagnosi daily stop + regime filter in parallelo |
| Rollback | No rollback integrale | No rollback integrale (stessa conclusione) |
| Gate di fedeltà | Prerequisito per qualunque modifica | Utile ma non bloccante per Guardie 1-2 |
| Tempi | Settimane (replay è lungo) | Giorni (guardie + diagnosi in parallelo) |
| Rischio principale aggiuntivo | Non identificato | Correlazione Hawk-Bull, stale prices rollover, DCA bypass gate |

---

## SEZIONE 5 — RACCOMANDAZIONE FINALE ALL'UTENTE

**Cosa ti consiglio di approvare subito (READ-ONLY, nessun rischio):**

1. Lettura di `engine.py` su `rule-pool` da parte mia o ChatGPT per confermare il bug del daily stop (15 minuti di lavoro)
2. Lettura del `trade_history.jsonl` di Bull per ricostruire la sequenza del 29/10 (1-2 ore)

**Cosa ti consiglio di approvare come step successivo (offline, branch isolato):**

3. Implementazione test della Guardia 1 (daily stop latch) su branch di laboratorio
4. Regime filter test offline su dati storici 12–29/10

**Cosa non fare ora:**

- Non riattivare Hawk o Bull prima che la diagnosi del daily stop sia chiara
- Non resettare i conti PAPER a 1.000: perdere la traccia del deterioramento reale
- Non fare rollback al 12/10: non c'è evidenza che riporti ai risultati golden

**La posizione BTC SHORT ancora aperta su Bull:**

Lasciare alla gestione in pausa. SL è a 80.563,81 — se viene toccato, chiude automaticamente. Non intervenire manualmente.

---

**Pronto a continuare con qualunque analisi read-only tu autorizzi.**

AI: Claude Sonnet 4.6
