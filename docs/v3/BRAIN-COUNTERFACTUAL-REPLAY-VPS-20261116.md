# Brain — Primo replay VPS (16 novembre 2026, ore 06:00 circa Europe/Rome)

**Origine:** screenshot Termius forniti dall'operatore. Non e' stato condiviso il journal o il file `summary.json` completo; non inventare metriche non mostrate. Script `replay_vps.py` versione fissata al commit `56a11900254fca5abe42da50adf38fd0009fd1c8`.

## Esito verificato dallo screenshot

- `RESULT=COMPLETED_WITH_COVERAGE_LIMITS`
- `live_unchanged=YES`, `orders_sent=0`, `mode=PAPER_OFFLINE_READ_ONLY`
- `snapshot_decisions=430`
- Finestra: `2026-11-13T14:09Z` — `2026-11-16T05:00Z` (limite destro esclusivo)
- 8 simboli BTCUSDT/ETHUSDT/SOLUSDT/XRPUSDT/BNBUSDT/DOGEUSDT/ADAUSDT/LINKUSDT: **3771/3771 candele 1m ciascuno, coverage 100%, gap 0**.
- `approvals=61`, `verified_opens=38`, `unexecuted_unknown_cause=23`: il **37,7% delle approvazioni** manca di apertura verificata, ma non si conosce il motivo.
- `model_side_unknown=392`: non attribuire retroattivamente un lato alle 392 decisioni con side sconosciuto.
- `paired_lag_0m=n34 model_minus_always_short_R=-0.1781`
- `paired_lag_1m=n34 model_minus_always_short_R=-0.1781`
- `paired_lag_3m=n34 model_minus_always_short_R=-0.1781`
- File locali su VPS in `/tmp/superbot-brain-research-6ddocak3/summary.json` e `counterfactual.jsonl` (il nome della cartella e' inferito visivamente; preferire la ricerca sicura via glob anziche' affidarsi a questa trascrizione).

## Interpretazione

Questo e' un **replay completo del programma**, non una validazione della qualita' dell'AI. Il confronto `model_minus_always_short` misura il lato Brain rispetto a uno SHORT sullo **stesso** simbolo e orario: se Brain apre SHORT, la differenza e' zero per costruzione. Non misura se Brain sappia selezionare i migliori ingressi o battere aperture su orari casuali. I pochi LONG selezionati possono determinare quasi interamente il valore negativo; e' indispensabile la ripartizione per lato e le metriche `paired_hypotheses`.

I tre valori identici a distanza 0/1/3 minuti potrebbero dipendere da esiti stop/TP uguali nel periodo e da arrotondamento, ma necessitano di controllo per singola operazione: non affermare che il ritardo non conti.

Delle 38 aperture reali, 34 hanno entrambi gli scenari LONG/SHORT risolti; le altre quattro non entrano nel confronto, ad esempio per censura o dati insufficienti. Non assumere il motivo senza `summary.json` e la verifica per riga.

Per gli 23 `APPROVED_NOT_OPENED_CAUSE_UNKNOWN`, `post_ai_guard` *puo'* generare dinieghi, ma il journal non registra i motivi storici a livello di decisione: non attribuire automaticamente tutte le 23 a `risk_changed_after_ai`.

## Prossima verifica minima

Da Termius estrarre **soltanto** `decision_counts`, `post_ai_gap_audit.by_symbol` e le metriche `paired_hypotheses`, soprattutto `model_side_mean_hypothetical_r`, `same_timestamp_always_short_mean_r`, `same_timestamp_hash_coin_mean_r`, `scenario_by_decision_group`; nessun dump del database. Verificare quale motivo dei quattro esclusi e se il valore -0.1781R deriva dai LONG.

Solo in seguito, preparare osservabilita' prospettica **con autorizzazione distinta** per motivi di diniego post-AI e proposte scartate. Non disattivare controlli, non modificare leva/stop, nessun deploy/merge/riavvio.

**Fonti:** screenshot operatore e sorgenti nel ramo di ricerca; dati reali di `summary.json` non letti direttamente in questa chat.

## Secondo screenshot VPS — 16 novembre, ore 06:06 Europe/Rome

Istruzione di lettura Termius sul `summary.json` e sul `counterfactual.jsonl` della **stessa run**, con output limitato, nessuna modifica ai bot.

**Decisioni (430):**
- `NO_TRADE/DRAFT=120`
- `NO_TRADE/REJECTED=2`
- `NO_TRADE/RISK_REJECTED=247`
- `OPEN/APPROVED=61`

**Approvate/aperture verificate/rischio pre-approvazione/non eseguite, per asset:**

| Simbolo | Approved | Executed | Risk rejected | Approved senza apertura (motivo ignoto) |
| --- | ---: | ---: | ---: | ---: |
| ADAUSDT | 5 | 3 | 34 | 2 |
| BNBUSDT | 9 | 6 | 31 | 3 |
| BTCUSDT | 16 | 12 | 15 | 4 |
| DOGEUSDT | 5 | 1 | 39 | 4 |
| ETHUSDT | 8 | 6 | 31 | 2 |
| LINKUSDT | 6 | 4 | 27 | 2 |
| SOLUSDT | 6 | 3 | 33 | 3 |
| XRPUSDT | 6 | 3 | 37 | 3 |
| **Totale** | **61** | **38** | **247** | **23** |

**Ipotesi stessa ora/simbolo, 34 coppie risolte (R medi virtuali; non PnL reale):**

| Ritardo | Brain lato scelto | Sempre SHORT | Hash coin | Differenza Brain - SHORT |
| --- | ---: | ---: | ---: | ---: |
| 0 min | +0,4137 | +0,5918 | −0,3875 | −0,1781 |
| 1 min | +0,3246 | +0,5027 | −0,4765 | −0,1781 |
| 3 min | +0,4137 | +0,5918 | −0,3876 | −0,1781 |

**38 aperture collegate:** 36 SHORT (`side=-1`) e 2 LONG (`side=+1`). Simulazioni virtuali a 1 min: 34 righe con LONG e SHORT risolti, 2 con LONG censurato e SHORT risolto, 2 con LONG risolto e SHORT censurato. Le 34 coppie sono un sottoinsieme delle 38 aperture. Il costo del ritardo medio passa da 0 a 1 minuto, ma il delta fra i lati rimane costante fino alle 4 cifre stampate.

### Inferenze e nuove priorita'

- Il delta negativo Brain-vs-sempre-SHORT **non prova che 36 SHORT Brain siano scadenti**: per i 36 SHORT scelti, il confronto per lato e' identico per costruzione. Sono i soli LONG, se inclusi nelle 34 coppie, a spiegare il delta; occorre confrontare le singole righe LONG senza pubblicare informazioni sensibili.
- La media Brain +0,3246R a ritardo 1 min e' **simulata e condizionata** alle decisioni con side osservato; non dimostra vantaggio realizzato e non considera i vincoli dell'intero portafoglio.
- Il 37,7% di approvazioni senza fill e' una categoria investigativa: non attribuire i 23 alla logica post-AI senza eventi di rifiuto verificabili. DOGE e' il simbolo con la maggiore percentuale (4/5); BTC ha il maggiore numero assoluto (4). I 247 rifiuti risk sono **precedenti all'approvazione**, non sono i 23 gap.
- Controllo successivo: stampare aggregati per LONG e SHORT nelle coppie, i casi singoli LONG senza event-id completo, e i due gruppi di censura; confrontare i `NO_TRADE/DRAFT` con le ipotesi controfattuali **senza attribuire loro una direzione**.
- Test successivo ancora non fatto: misurare se Brain seleziona **tempi/simboli** migliori rispetto a ingressi di controllo, appaiando i limiti di capitale, le posizioni contemporanee e il regime. I confronti `sempre SHORT nello stesso timestamp` non testano tale capacita'.

L'esito resta **esplorativo, PAPER, offline, nessuna modifica operativa**.

## Terzo screenshot VPS — 16 novembre, ore 07:20 Europe/Rome: LONG spiegano il delta

**Evidenza nuova, verificata visivamente in Termius**, sui medesimi file `summary.json` e `counterfactual.jsonl` e non su una nuova run.

### Due LONG reali, due SHORT solo virtuali

- LINKUSDT, decisione 13/11 15:00 UTC: LONG simulato `-1.1884 R` (stop dopo 14 minuti), SHORT ipotetico `+1.8390 R` (TP dopo 25 minuti). PnL realizzato PAPER LONG **−83,49090849 USDT**.
- BTCUSDT, decisione 13/11 22:00 UTC: LONG simulato `-1.1884 R` (stop dopo 65 minuti), SHORT ipotetico `+1.8390 R` (TP dopo 266 minuti). PnL realizzato PAPER LONG **−53,92702358 USDT**.
- PnL reale dei due LONG: **−137,41793207 USDT**, pari a −137,42 USDT arrotondati.
- Con ritardo virtuale di 1 minuto, dei **34 confronti completi**: 32 SHORT reali `Brain_R=0.4192` e `Sempre_SHORT_R=0.4192`; 2 LONG reali `Brain_R=-1.1884` e `Sempre_SHORT_R=1.8390`. Da questi soltanto deriva `model_minus_always_short_R = 2*(-1.1884 - 1.8390)/34 = -0.17808 ` (~−0,1781 R).
- Ritardo 3 minuti: SHORT n=32 `Brain_R=0.5138`, LONG n=2 `Brain_R=-1.1884`, SHORT virtuale per i due LONG `+1.8390`. Uguale decomposizione del delta. Ritardo 0 minuti: LONG n=2 stessi valori; la parte SHORT non e' completamente visibile nello screenshot.
- Il `R` e' su **stop virtuale fisso 0,74%, TP 2R e costi prefissati**. Non e' il rischio reale per trade ne' prova di eseguibilita' dell'alternativa SHORT.

### Controfattuali per classe di decisione (ritardo 1 minuto, entrambi i lati risolti)

| Tipo di decisione | n | LONG virtuale, R medio | SHORT virtuale, R medio |
| --- | ---: | ---: | ---: |
| `NO_TRADE/DRAFT` | 101 | −0,8589 | +0,8193 |
| `NO_TRADE/REJECTED` | 2 | −1,1884 | +0,3245 |
| `NO_TRADE/RISK_REJECTED` | 237 | −0,4736 | +0,3692 |
| `OPEN/APPROVED` | 56 | −0,9723 | +0,7572 |

**Importante:** per NO_TRADE il simulatore produce *entrambe* le direzioni, ma non registra quale avrebbe scelto DeepSeek. Non chiamare questi R profitti persi o guadagni reali; simulazioni sovrapposte, senza slot, limiti risk/guard o esecuzione reale.

### Nota critica su confronto Opus originale

Il file `research/brain_audit_opus/geometry.py` definisce `PAUSE` artificiale **13/11 21:30—14/11 00:10 UTC** e scarta campioni in quella fascia. Tuttavia il journal del replay collega un `paper_open` LONG BTC alla decisione del **13/11 22:00 UTC**, dentro quella fascia. Non e' prova che lo script Opus abbia un bug, ma **la finestra esclusa non rappresenta fedelmente ogni opportunita' della run reale**: il confronto casuale original va ripensato usando stati e tempi effettivi della run anziche' pause assunte a priori. Per i timestamp il replay riporta il tempo della decisione, mentre quello esatto di apertura potrebbe essere successivo.

### Raccomandazioni conseguenti

1. **Indagare i due LONG con dati causali**, perche' la AI li riteneva validi nonostante un regime ribassista piu' ampio: contesto 1h/4h, settore/strategia proposta, asset e ATR al momento decisione. Non trarre conclusioni di efficacia generale da soli due casi.
2. **Lasciare gli SHORT operativi invariati**: i 32 SHORT allineati sono identici al benchmark sempre-short per costruzione; quel benchmark non valuta *selezione di orario e simbolo*. Il confronto su opportunita' NO_TRADE puo' aiutare un test, ma va corretto per esposizione e covariate.
3. **Non convertire automaticamente LONG in SHORT.** Il controfattuale e' post-hoc su mercato ribassista e manca un gate di rischio indipendente. Studiare in shadow l'alternativa LONG vs NO_TRADE e LONG vs SHORT condizionata al contesto.
4. **Investigare i 23 APPROVED senza apertura** con osservabilita' persistente autorizzata separatamente; non confonderli con i 247 rifiuti pre-approvazione.
5. Conservare FREEZE operativo fino a validazione fuori campione; nessun filtro FRRD, blacklist ETH, leva/stop ATR, merge o deploy.

**Stato:** questo documento riporta output Termius e analisi aritmetica; nessun cambiamento ai servizi PAPER.
