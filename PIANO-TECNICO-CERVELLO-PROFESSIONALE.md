# Piano tecnico — Evoluzione del Cervello Professionale

**Autore:** Claude, 19/10/2026 (~14:30 ora di Roma). **Stato: PROPOSTA da discutere con l'utente e con ChatGPT.**
Risponde ai 12 punti richiesti in `SPECIFICA-EVOLUZIONE-CERVELLO.md`. **Nessuna modifica fatta**: niente deploy, niente cambi a strategia, rischio, prompt, slot o cervello. Il primo intervento concreto lo autorizza l'utente dopo il confronto.

Base di lettura: `rule-pool` a `7447056` (codice dei bot in `backend/desk/`), prototipi di ChatGPT del 17/10 (`backend/desk/profit_manager_*.py`), dati reali del backup esterno delle 11:57 UTC (Hawk run 3, Bull run 2).

---

## 0. Cosa ho trovato leggendo il codice (punto 4 dell'ordine: "correggere cronologia, timestamp e protezioni")

Quattro difetti concreti, coerenti con le categorie dell'audit del weekend. **Vanno confermati con prove di replay prima di correggerli** (e la correzione cambia il comportamento del bot: serve l'OK dell'utente).

| # | Dove | Difetto | Effetto probabile |
|---|------|---------|-------------------|
| A | `cli.py` (ciclo, "processa barre") + `engine.on_bar` | A ogni ciclo si ripassano **tutte** le barre dall'apertura con i livelli **attuali** di stop/TP/liquidazione. Se un DCA o una chiusura parziale cambia TP o stop, le barre **passate** vengono giudicate con i livelli **nuovi**. | Chiusure "retroattive": per esempio un TP abbassato scatta su una barra di ore prima, con orario di chiusura precedente alla decisione che l'ha impostato. È la "cronologia delle protezioni". |
| B | `fetch_candles` → `read_symbol` / `on_bar` | L'ultima candela da 15m è **in formazione**: il suo massimo/minimo è parziale. Viene usata come se fosse chiusa, sia per gli indicatori (anche le barre 1h e 4h ricampionate, ultime incomplete) sia per gli stop. | Indicatori che cambiano dentro la stessa barra; nessun look-ahead, ma decisioni su dati non definitivi ("timestamp delle barre"). |
| C | `run_cycle`: `acc.roll_day(day, {})` | Al cambio di giorno l'equity di riferimento si calcola **senza prezzi**, quindi ai prezzi d'ingresso (P&L aperto ignorato). | Lo stop giornaliero del 12% parte da una base sbagliata quando ci sono posizioni aperte a mezzanotte UTC ("gestione del blocco giornaliero"). |
| D | `engine.add_dca` | Il DCA imposta un nuovo stop calcolato dal prezzo del DCA: per definizione il prezzo è andato contro, quindi lo stop può **allargarsi**. | Contraddice la regola 7 della specifica ("uno stop stretto non si allarga"). È anche una scelta di strategia, quindi decide l'utente. Nella stessa barra la liquidazione viene controllata prima dello stop (ipotesi pessimistica, da misurare). |

**Il difetto A è dimostrato con l'engine vero** (prova isolata, senza toccare i bot):
- un long aperto a 100 con TP 110 sale fino a 106 e torna a 102;
- alla barra 4 una chiusura parziale abbassa il TP a 104;
- ripassando le barre come fa `cli.py`, l'engine chiude in "take profit" a 103,98 con orario di chiusura alla **barra 2**, cioè prima della decisione.

I difetti B, C e D si vedono leggendo il codice: `acc.roll_day(day, {})` è l'unico cambio di giorno; nessuna memoria delle barre già elaborate.

Il replay (punto 8) misura quante operazioni di Hawk run 3 e Bull run 2 sarebbero cambiate con ciascuna correzione, una alla volta.

---

## 1. Mappa dei moduli esistenti riutilizzabili

| Modulo | Cosa fa oggi | Uso nel progetto |
|--------|--------------|------------------|
| `engine.py` (`PaperAccount`, `Position`) | Contabilità paper: margine, leva per tier, DCA, seconda gamba, chiusura parziale, liquidazione, `px_hi/px_lo` (MAE/MFE), `fee_open`, `risk_plan_usd`, `r_dist` | **Unica verità contabile**. Il Profit Manager la legge, non la duplica. Da correggere i difetti A e D. |
| `signals.py` (`resample`, `ema`, `rsi`, `atr`, `read_symbol`) | Indicatori 15m→1h/4h/1d | Base delle feature di momentum, struttura e volatilità, **solo su barre chiuse** (difetto B). |
| `learning.py` | Registro append-only, versione dello schema, `run_no`, tetti di dimensione, errori assorbiti | Modello del nuovo registro delle decisioni (stesse regole). Il registro esistente non si tocca. |
| `analyst.py` (`label_candidate`, `wilson`, `fetch_range`) | Etichetta a posteriori i candidati scartati con i prezzi successivi | **Opportunità scartate** e calibrazione: riuso diretto per l'etichettatura offline. |
| `profit_manager_shadow.py`, `_replay.py`, `_state_adapter.py`, `_monitor.py`, `_report.py`, `_collect_offline.py` (ChatGPT, 17/10) | PM v0 puro: ROI netto su margine, attivazione 20%, blocco 5%, trailing 10 punti; replay che rifiuta DCA, gambe multiple e chiusure parziali | Diventa la **baseline PM-A** e il banco di prova. Limiti noti: soglie fisse, nessun ATR o regime, esclude DCA e parziali, usa l'ultimo prezzo e non un'uscita eseguibile. |
| `market_context.py` | Funding (ok), open interest (parser incompatibile), long/short (endpoint 404) | Funding subito; OI e L/S solo dopo la riparazione (decisione dell'utente). |
| `macro_calendar.py`, `trading_hours.py`, `schedule.py` | Regime macro, orari, finestre di Claude | Feature di regime e contesto; nessuna modifica. |
| `brain.py` | Prompt, decisioni di Claude, lezioni | Il Cervello resta **consigliere**: le sue valutazioni si registrano, non comandano (fase 4). |
| `backup_brain.py`, `external_backup.py`, `restore_external_backup.py` | Backup coerente a fine ciclo, esterno cifrato, ripristino con controlli semantici | Prerequisito di ogni deploy (già fatto il 19/10). |
| `backend/tests/test_desk*.py`, `backend/desk/test_profit_manager_*.py` | Prove esistenti | Restano verdi a ogni passo: nessuna regressione. |

---

## 2. Architettura proposta del Profit Manager

Un pacchetto nuovo e **puro**: niente rete, niente file, niente ordini, solo calcolo. Funziona allo stesso modo in replay, in ombra e (un giorno) in attivo.

```
backend/desk/profit/
  liquidable.py   profitto netto LIQUIDABILE: prezzo d'uscita realistico (mark -/+ mezzo spread + slippage),
                  commissione di chiusura, funding maturato, gambe e DCA, parte già chiusa
  features.py     solo barre CHIUSE: ATR e sua variazione, pendenza EMA, RSI, struttura (massimi/minimi),
                  tempo dall'ultimo nuovo massimo di profitto, durata, regime
  reversal.py     punteggio d'inversione da più segnali (nessuno decide da solo), con le prove usate
  machine.py      macchina a stati della protezione (punto 4), con isteresi e pavimento monotono
  slot_value.py   valore residuo atteso della posizione e confronto con una nuova opportunità
  policy_hawk.py  parametri di Hawk (versionati, hash della configurazione)
  policy_bull.py  parametri di Bull, separati e più conservativi (nessuna eredità da Hawk)
  ledger.py       scrittura del registro delle decisioni (append-only, punto 3)
```

**Ingresso:** una vista immutabile della posizione (dall'engine), le barre chiuse, il contesto (funding, regime), i costi.
**Uscita:** `Decisione{azione, nuovo_pavimento, frazione, motivi[], prove{}, versione_algoritmo, hash_config}`.
Le azioni possibili sono: `HOLD`, `ARMA`, `STRINGI(pavimento)`, `PARZIALE(frazione)`, `ESCI`, `PROPONI_SOSTITUZIONE`.

**Modalità per portafoglio**, in un file di controllo nella cartella del bot (come `trading_enabled.json`), letto a ogni ciclo e quindi cambiabile senza redeploy:
- `off`
- `ombra` (default iniziale): registra e basta;
- `consiglio`: la valutazione entra anche nel prompt di Claude;
- `attivo`: l'engine applica **solo** "stringi lo stop" ed "esci". Va promosso dall'utente, una modifica alla volta.

**Dove gira nel ciclo:** dopo l'elaborazione delle barre (le protezioni esistenti vengono prima), su barre chiuse, per ogni posizione aperta. In ombra non cambia nulla dello stato del conto.

**Regole fisse dentro l'engine** (non dentro il PM):
- il pavimento di protezione è **monotono**: non si allarga mai;
- con dati vecchi o mancanti il PM si congela: niente nuove strette basate su dati inaffidabili, ma le protezioni già in essere restano.

**Pressione sugli slot:** si libera uno slot solo se `EV netto nuova > valore residuo atteso + costi di sostituzione + margine di sicurezza`, con tutti i termini registrati. Un nuovo segnale da solo non basta. Hawk resta a 10 slot e Bull a 3.

---

## 3. Formato degli eventi append-only

File nuovo per portafoglio: `decision_log.jsonl`. Il `learning_log.jsonl` esistente non cambia. Il file entra nei backup coerenti: si aggiunge ai file centrali di `backup_brain.py`.

```json
{"schema": 1, "ev": "pm_eval", "event_id": "hawk:3:41:1792390000000:pm:000123",
 "ts_ms": 1792391800000, "bar_close_ms": 1792391700000,
 "portfolio": "hawk", "run_no": 3, "position_key": "hawk:3:41:1792390000000:BTC",
 "code_version": "<sha>", "algo": {"name": "pm-hawk", "version": "1.0.0", "config_hash": "<sha256>"},
 "mode": "ombra", "applied": false,
 "inputs": {"mark": 0, "entry": 0, "qty": 0, "legs": 1, "dca_count": 0, "funding_paid": 0,
            "atr_pct": 0, "regime": {"label": "trend_rialzista", "conf": 0.0, "prove": []}},
 "derived": {"net_liquidable_usd": 0, "net_roi_pct": 0, "peak_net_usd": 0, "giveback_usd": 0,
             "costs": {"fee_close": 0, "slippage": 0, "spread": 0, "funding": 0},
             "reversal": {"score": 0, "prove": []}, "since_new_peak_min": 0},
 "state": {"from": "ARMATO", "to": "PROTETTO"},
 "decision": {"action": "STRINGI", "floor_usd": 0, "reasons": ["profitto_oltre_costi_e_rumore"]},
 "alternatives": [{"action": "HOLD", "ev_usd": 0}], "p_win": null, "ev_net_usd": null}
```

**Regole:**
- Una riga per evento, mai riscritta.
- Gli esiti arrivano **dopo**, come eventi separati che rimandano all'`event_id` (`pm_outcome`: massimo profitto successivo, drawdown, give-back, cosa sarebbe successo alla baseline).
- Le feature usano solo dati con orario ≤ `bar_close_ms`: un test lo verifica (punto 8).
- Tetti di dimensione ed errori assorbiti come in `learning.py`.
- Stesso schema anche per gli eventi `regime`, `swap_eval` (sostituzione di uno slot) e `candidate_outcome` (opportunità scartate etichettate offline da `analyst.py`).

---

## 4. Macchina a stati della protezione del profitto

| Stato | Si entra quando | Cosa fa |
|-------|-----------------|---------|
| `OSSERVA` | apertura | Nessun anticipo dell'uscita: il profitto netto liquidabile non copre ancora costi + rumore (k × ATR). |
| `ARMATO` | netto liquidabile ≥ costi di uscita + k₁ × ATR, confermato da N barre chiuse | Registra il massimo di profitto netto e prepara il pavimento. |
| `PROTETTO` | dopo `ARMATO` | Pavimento = massimo netto − give-back consentito. Il give-back dipende da ATR e regime (più largo in trend forte, più stretto in range e alta volatilità). Se il trend continua il massimo sale e la posizione corre. |
| `STRETTO` | deterioramento: momentum in calo, struttura rotta, nessun nuovo massimo da T minuti | Give-back ridotto (pavimento più alto, mai più basso). |
| `USCITA` | netto ≤ pavimento, oppure inversione credibile (punteggio ≥ soglia, almeno 2 famiglie di segnali concordi) | In ombra registra l'uscita ipotetica; in attivo chiude con la modalità validata. |
| `CONGELATO` | dati vecchi o incompleti, barre mancanti | Nessuna nuova stretta o uscita da dati inaffidabili; le protezioni esistenti restano. Torna allo stato precedente quando i dati tornano buoni. |

Vale sempre:
- il pavimento non scende mai, perché lo stato non torna indietro verso livelli più permissivi;
- c'è isteresi (N barre di conferma) per non oscillare;
- per Bull, al passaggio a `PROTETTO` è possibile una `PARZIALE` (da simulare prima), poi la parte residua segue la macchina.

---

## 5. Snapshot coerente a fine ciclo

**Già fatto il 19/10:**
- copia del cervello solo tra due cicli, verificati dal battito del bot;
- file irrinunciabili presenti e JSONL completi;
- modalità "bot fermo" con la prova sul container;
- backup esterno cifrato con ripristino provato;
- controlli semantici nel ripristino (stato = storico della run, id, contabilità).

**Da fare:**
1. Aggiungere `decision_log.jsonl` ai file centrali.
2. Eseguire gli stessi controlli semantici **anche al momento del backup**, non solo al ripristino.
3. Facoltativo, perché richiede un redeploy: il bot scrive a fine ciclo un `cycle_done.json` con le impronte dei file centrali, così il confine non si deduce più dal battito.

---

## 6. Separare merge e deploy

**Già fatto per l'app:** un merge su `main` non rilascia; il rilascio usa uno SHA approvato, risolto una volta sola, con manifesto e ritorno indietro automatico.

**Da fare per bot e pool** (ChatGPT è favorevole):
- stesso schema: SHA nel file trigger e immagine etichettata con lo SHA;
- `DESK_CODE_VERSION` uguale allo SHA, così il battito dichiara il commit vero. Oggi la cartella è a `a47ea40` mentre i bot dichiarano `b4709d1`;
- controllo che ci sia una sola istanza per bot;
- manifesto del rilascio.

**Rami.** La specifica chiede un ramo `work/<tema>` da `main`, integrando selettivamente i motori di `rule-pool`. Una precisazione onesta: **i bot oggi si costruiscono da `rule-pool`**, l'app da `main`, e i due rami hanno storie molto diverse. Propongo:
- (a) lo sviluppo del PM in `work/profit-manager`, partendo da `rule-pool`, dove vivono i bot;
- (b) le sole parti di app (visualizzazione delle valutazioni in ombra) in un ramo da `main`;
- (c) la riconciliazione dei due rami come progetto a parte, dopo la correzione del `Request` mancante in `backend/server.py` di `rule-pool`, senza merge ciechi.

Se l'utente preferisce un ramo unico da `main`, prima va fatta la riconciliazione.

---

## 7. File che verrebbero modificati

**Fase 1 — osservabilità, nessun cambio di comportamento:**
- nuovi: `backend/desk/profit/*` (puri), `backend/desk/test_profit_*.py`;
- `cli.py`: una chiamata in ombra dopo l'elaborazione delle barre, protetta da `try` (un errore non ferma mai il bot), e lettura del file di modalità;
- `backup_brain.py`: `decision_log.jsonl` tra i file centrali;
- `restore_external_backup.py`: lettura del nuovo registro.

**Fase 2 — correzioni A-D, cambiano il comportamento, OK dell'utente una per una:**
- `engine.py`: barre già elaborate per posizione (`last_bar_ms`) e orario dell'ultimo cambio di protezione, così un livello nuovo vale solo dalle barre successive; guardia di monotonia dello stop;
- `cli.py`: esclusione della barra in formazione; `roll_day` con i prezzi veri.

**Fase 3 — deploy su SHA:** `desk-deploy.yml`, `pool-deploy.yml`, test del workflow.

**Fase 4 — attivazione su Hawk**, solo dopo la promozione: `engine.py` applica `STRINGI`/`ESCI` quando la modalità è `attivo`.

**App (più avanti):** `desk_view` mostra le valutazioni in ombra e il confronto con la baseline.

---

## 8. Prove previste

**Unitarie** (pure, veloci):
- profitto liquidabile: costi, funding, parziali, DCA, gambe;
- proprietà: il pavimento non scende mai, qualunque sequenza di prezzi (test con sequenze casuali);
- transizioni della macchina a stati, una tabella di casi;
- isteresi;
- congelamento con dati vecchi.

**Anti look-ahead:** troncare il futuro non cambia nessuna decisione passata, con un test che dimostra di catturare un look-ahead messo apposta (come nel laboratorio del 9/10). La barra in formazione non entra mai nelle feature.

**Regressione dei difetti A-D:**
- un TP cambiato non scatta su barre precedenti al cambio;
- il cambio di giorno con posizioni aperte usa i prezzi veri;
- un DCA non allarga lo stop, se l'utente approva la regola.

**Baseline invariata:** con la modalità `ombra` lo stato del conto dopo N cicli registrati è identico byte per byte a quello senza PM.

**Replay su dati veri:** candele 15m storiche + `trade_history` e `learning_log` di Hawk run 3 e Bull run 2 (e run precedenti). Per ogni trade si calcolano baseline, PM-A (prototipo di ChatGPT) e PM nuovo sugli stessi ingressi. Si calcolano le metriche della specifica e il numero di trade che cambierebbero con le correzioni A-D.

**Ombra in produzione:** solo registro, con un rapporto quotidiano (ChatGPT ha già `profit_manager_report.py`).

---

## 9. Criteri di promozione (proposta da discutere: i numeri sono punti di partenza)

Il PM non si promuove solo perché riduce il give-back. Servono tutte queste condizioni:
1. **campione:** almeno 4 settimane di ombra e almeno 40 posizioni di Hawk in cui il PM avrebbe agito (per Bull, con 3 slot, il campione va integrato col replay storico);
2. **risultato netto:** differenza PM − baseline ≥ 0 con intervallo di confidenza (bootstrap) che non includa un peggioramento rilevante. Il replay e l'ombra devono essere concordi nel segno;
3. **uscite premature:** al massimo il 25% delle uscite del PM seguite da un ulteriore +1R nel verso della posizione entro l'orizzonte del trade;
4. **costi e rischio:** commissioni, slippage e funding non aumentano più del 10%; drawdown massimo non peggiore; nessun aumento dell'esposizione correlata;
5. **regimi:** nessun regime con un peggioramento significativo;
6. **inversioni:** il Brier score del punteggio d'inversione è migliore del tasso di base, con curva di affidabilità e numerosità dichiarate;
7. **una modifica alla volta**, prima Hawk e poi Bull, con decisione esplicita dell'utente.

---

## 10. Rollback

- **Modalità:** il file di controllo torna a `ombra` o `off`, senza redeploy, al ciclo successivo. Si può cambiare da un workflow.
- **Codice:** l'immagine precedente resta come `superbot-desk:rollback-<data>`; con il deploy su SHA si torna al commit precedente noto.
- **Dati:**
  - backup coerente verificato prima di ogni deploy;
  - backup esterno cifrato quotidiano;
  - ripristino provato in una cartella isolata con controlli semantici;
  - run, posizioni e cervello conservati (la baseline Hawk run 3 / Bull run 2 non si azzera mai).
- **Verifiche dopo ogni intervento:** una sola istanza per bot, modalità paper, versione dichiarata = SHA approvato, posizioni intatte.

---

## 11. Rischi residui

- **Campioni piccoli** (36 trade nella run 3 di Hawk, 17 nella run 2 di Bull): rischio di adattare i parametri al passato. Contromisure: parametri pochi e fissati prima, replay su storia più lunga, split temporali.
- **Barre da 15 minuti:** dentro la barra l'ordine dei prezzi è ignoto. Valutare il PM su barre chiuse ritarda le uscite fino a 15 minuti; un'uscita "al tocco" sarebbe ottimistica.
- **Paper ≠ live:** fill, spread e slippage reali sono diversi (le chiavi Bitget sono in stand-by).
- **Interazione con Claude:** anche Claude chiude e riduce le posizioni, quindi il confronto PM/baseline è confuso. Bisogna registrare chi ha deciso cosa.
- **Dati mancanti:** OI e long/short non funzionano finché non vengono riparati, quindi il modello d'inversione parte senza.
- **Risorse del server** (2 vCPU, 3,8 GB): il PM deve restare leggero.
- **Le correzioni A-D cambiano la baseline:** vanno misurate e approvate prima del confronto, altrimenti si confrontano due cose diverse.
- **Due AI sugli stessi file:** serve un solo autore per componente alla volta (punto 12).

---

## 12. Divisione del lavoro proposta tra Claude e ChatGPT

| Componente | Autore | Revisore |
|------------|--------|----------|
| Matematica del PM: `liquidable`, `machine`, `policy_*` (evoluzione del suo prototipo) | ChatGPT | Claude |
| Modello d'inversione e calibrazione (`reversal`, Brier, affidabilità) | ChatGPT | Claude |
| Correzioni A-D nell'engine con test di regressione e replay che ne misura l'effetto | Claude | ChatGPT |
| Aggancio nel ciclo in ombra, registro `decision_log`, backup, file di modalità | Claude | ChatGPT |
| Deploy di bot e pool su SHA, verifica sul server, rapporti dell'ombra | Claude | ChatGPT |
| Replay su dati veri e confronto baseline/PM con le metriche della specifica | insieme: Claude prepara i dati, ChatGPT l'analisi | l'altro |
| Decisioni (attivazione, rischio, slot, DCA, riparazione di OI/LS) | **l'utente** | — |

Regole:
- ogni lavoro su un ramo `work/<tema>`, annotato nel diario ("In corso: …");
- l'altra AI rivede sui file reali prima di qualunque deploy;
- niente deploy senza l'OK dell'utente.

---

## Primo intervento che proporrei all'utente (quando vorrà)

**Solo osservabilità, rischio minimo:**
1. replay offline delle correzioni A-D, senza toccare i bot, per sapere quanto contano;
2. pacchetto `profit/` puro con le prove;
3. aggancio in ombra.

I punti 1 e 2 non richiedono nessun deploy. Il punto 3 richiede un redeploy dei bot, quindi serve il suo OK esplicito.
