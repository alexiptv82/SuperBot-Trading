# RC84 — Audit SHORT vs LONG e affidabilità Brain (12 novembre 2026)

**Versione esaminata:** `ab7e0b7d991b8f4bd714fccfec23b09a936e6717` (quella distribuita). Solo lettura del codice e prove sintetiche offline sul codice vero di `signals.py`; **nessun accesso alla VPS**, nessun ordine, nessuna modifica a configurazioni, servizi o registri. I registri PAPER reali non sono raggiungibili da questa sessione (repository pubblico, dati solo sulla VPS): la parte quantitativa va eseguita con lo strumento consegnato (`deploy/scripts/audit_long_short.py`, §6).

Le sei chiusure del 12/11 (+234,64 USDT, tutte TP) **non hanno direzione registrata nel riepilogo**: non vanno attribuite agli SHORT finché `audit_long_short.py` non lo mostra. L'osservazione "SHORT meglio dei LONG" è plausibile e coerente con i difetti sotto, ma resta da misurare.

## 1. Errori tecnici dimostrati (riferimenti al codice di `ab7e0b7`)

**E1 (=P1) — L'"EMA200 4h" è in realtà una EMA61.** `fetch_candles` scarica 1.000 candele 15m (`backend/desk/cli.py:269`); 1.000/16 ≈ 62 barre 4h complete; `signals.py:110` fa `ema(c4, min(200, len(c4)-1))` → EMA61. Il blocco "trend 4h" da **20 punti** (`signals.py:147`) confronta quindi EMA50 con EMA61: due medie quasi uguali, il cui incrocio scatta nei **rimbalzi** molto prima di una vera EMA200. *Dimostrazione:* in 40 scenari sintetici di ribasso di 40 giorni con rimbalzo di 4 giorni, valutati ogni 30 minuti come fa il desk, in **23/40 scenari** il punteggio LONG supera 60 durante il rimbalzo, e nel **100% di quei cicli la vera EMA200 4h è ancora ribassista**. Lo stesso dato distorto arriva a Claude nel prompt come `trend4h su/giu` (`brain.py:350`).

**E2 (=P2) — Il trend giornaliero non esiste mai.** Il blocco 1d da 15 punti richiede ≥30 barre giornaliere (`signals.py:120`); 1.000 candele 15m ≈ 10 giorni → **con la storia standard il filtro 1d non si attiva mai** e Claude riceve `daily_trend` vuoto. **Bug latente:** con 30–49 barre giornaliere `e200d = e50d` (`signals.py:123`) e `1 if e50d > e200d else -1` dà **sempre −1**: dimostrato che 35 giorni di forte rialzo producono `"trend 1d bear, RSI1d 100"`. Chi estenderà la storia senza correggere questa riga introdurrà un falso bias SHORT da ±30 punti (15 tolti a LONG e 15 dati a SHORT).

**E3 (=P3) — La conferma del cambio di trend non vincola e il bias 4h è sempre sconosciuto.** `trend_change.advisory` è dichiaratamente consultivo; `h4_bias` richiede 200 barre 4h chiuse (`trend_change.py:70`) = ~34 giorni di 15m → con la storia standard è **sempre UNKNOWN**, e il prompt lo mostra a Claude solo quando è noto (`brain.py:353-354`): quindi **mai**. Non esiste alcun punto, né nelle regole né nel prompt, in cui un LONG di inversione debba aspettare una conferma.

**E4 (=P4) — Candele in formazione negli indicatori.** `read_symbol` riceve l'array grezzo con l'ultima candela 15m in corso; `resample` (`signals.py:25`) accetta un gruppo se ha il numero giusto di righe, quindi **nell'ultimo quarto di ogni ora** la barra 1h "corrente" contiene una candela non chiusa (idem 4h nell'ultimo quarto d'ora, 1d a fine giornata). *Dimostrazione:* una candela aperta da 5 minuti con uno spike sopra i massimi porta il punteggio da 52 (medio, nessuna rottura) a **64 (scalp, "rottura massimi 20h" +10)**; lo spike può rientrare prima della chiusura, ma il trade è già aperto a leva scalp. Il modulo advisory, al contrario, esclude correttamente le candele aperte (`trend_change.py:22`) — la stessa cura non è stata portata nel calcolo dei punteggi. Nota: `operational_prices` (`cli.py:822`) verifica la **freschezza del prezzo esecutivo**, che è un'altra cosa e funziona.

**E5 (=P5) — S25.** In `ab7e0b7` i nuovi ingressi S25 sono spenti di default: l'intero modulo gira solo con `DESK_LONG_S25=1` (`cli.py:1355`) e i **nuovi** ingressi richiedono in più portafoglio `bull` + `DESK_S25_TORO_ENTRY_APPROVED=1` + nessun NO_TRADE esplicito di Claude (`cli.py:1374-1376`); le uscite a tempo delle posizioni S25 esistenti restano gestite. I record S25 sono riconoscibili da `source="rules_long_s25"` (`long_s25.py:38`). **Da verificare sull'host** (qui impossibile): che `DESK_S25_TORO_ENTRY_APPROVED` non sia impostata nell'ambiente dei servizi. Le aperture BCH/BNB identiche dell'11/11 sono precedenti alla correzione delle 21:36 dell'11/11 e vanno conteggiate a parte nello strumento di §6.

**E6 (=P6) — Il motore applica molto meno di ciò che i prompt promettono.**
- Prompt: «Non aprire MAI un trade con R:R < 1:2» (`brain.py:62`). Motore: soglia **1,5** (`cli.py:1235`) e **solo se SL e TP sono entrambi > 0**: una decisione senza `take_profit_pct` **salta del tutto il filtro** e apre senza target (`cli.py:1233-1246`).
- Prompt Toro: confidenza ≥75 altcoin / ≥65 tier A e «TP minimo 5%» (`brain.py:135,143`). Motore: soglie 70/60 per tutti (`tier_entry_score`, `cli.py:155-157`) e **nessun controllo del TP minimo 5%**: un TP Toro al 2% passa.
- Il guardrail aumenta, mai riduce: se Claude propone margine o leva **sotto** i minimi, vengono **forzati in su** (Falco → 60$ 15x scalp; Toro → 200$ 15x; `cli.py:1252-1262`): una proposta prudente dell'AI diventa più aggressiva.
- Le regole di fallback generano sempre TP = 1,8×SL (`signals.py:218`): sotto il 2:1 chiesto ai prompt, sopra l'1,5 del codice.

**E7 (nuovo) — Funding addebitato solo ai LONG.** `engine.py:352,397`: `funding = … if pos.side == 1 else 0.0`, costante 1 bp/8h sul nozionale (`funding_bp_8h_long=1.0`, `engine.py:41`). Con leva 15–45x il nozionale è grande rispetto al margine (es. 350$×15x ≈ 5.250$ → ~1,6$/giorno). È un'asimmetria contabile sistematica anti-LONG nel PAPER, col segno fisso anche quando il funding reale in regime ribassista sarebbe a carico degli SHORT. Da sola non spiega le perdite, ma sposta ogni confronto LONG/SHORT e va ricordata leggendo i numeri di §6.

## 2. Risposte alle sei domande

1. **I LONG aprono su semplici rimbalzi?** Sì, strutturalmente possono: durante un rimbalzo in trend ribassista il punteggio LONG somma trend 1h (+15), prezzo>EMA50 (+8), momento 24h (fino a +12), rottura massimi 20h (+10), RSI 50–70 (+8), pattern (+8), e il blocco "trend 4h" (+20) scatta presto perché è EMA50 vs EMA61 (E1); il 1d che dovrebbe frenare non esiste (E2) e la conferma non vincola (E3). Dimostrato in sintetico: 23/40 rimbalzi armano un LONG ≥60 con la vera EMA200 4h ancora bear.
2. **Il rilevamento delle inversioni usa dati incompleti o mal calcolati?** Sì: E1 (EMA200 accorciata), E2 (1d assente + bug latente), E3 (bias 4h sempre UNKNOWN), E4 (candele in formazione). Claude riceve gli stessi valori distorti, quindi anche le decisioni AI ereditano il difetto.
3. **S25 è responsabile di parte delle perdite?** Possibile per le operazioni aperte **fino all'11/11 sera** (BCH/BNB duplicate su entrambi i portafogli, R:R≈1:1): si distinguono con `source="rules_long_s25"` nello strumento di §6. In `ab7e0b7` i nuovi ingressi sono spenti salvo doppio opt-in Toro (E5).
4. **LONG e SHORT hanno selettività diverse?** Le **regole scritte sono simmetriche** (stessi punti, stesse soglie, stesse penalità RSI). Le asimmetrie reali sono: (a) il regime ribassista rende i segnali SHORT "di continuazione" e i LONG "di inversione", e i difetti E1–E4 colpiscono quasi solo il secondo caso; (b) il funding è solo a carico dei LONG (E7); (c) i prompt chiedono più selettività di quella applicata (E6), e il divario danneggia di più il lato che opera controtendenza.
5. **Come trasferire ai LONG i punti di forza degli SHORT senza bias opposto?** §5.
6. **Brain può produrre decisioni valide dopo RC84?** Le correzioni sono nel commit distribuito e sono fatte bene (§7), ma **non esiste ancora un ciclo completo osservato**: la risposta onesta è "le precondizioni note sono state rimosse; la prova sarà il primo ciclo reale", con la lista di controllo di §7.

## 3. Cause probabili delle perdite LONG, in ordine di importanza

1. **Trend 4h/1d invisibile (E1+E2):** il sistema non può distinguere un'inversione da un rimbalzo, perché non ha mai abbastanza storia; il blocco da 20 punti "trend 4h" conferma il rimbalzo invece di smentirlo. Colpisce regole **e** Claude.
2. **Nessuna conferma vincolante per i LONG di inversione (E3):** l'unico modulo pensato per questo è consultivo e per metà cieco.
3. **Regime di mercato ribassista:** anche con indicatori perfetti, i LONG controtendenza hanno attese peggiori; i difetti sopra trasformano questa difficoltà in perdite sistematiche perché tolgono il freno.
4. **S25 fino all'11/11 (E5):** ingressi LONG duplicati con R:R≈1:1, già disattivati; pesano sulla finestra osservata dall'operatore.
5. **Candele in formazione (E4):** scalp a leva alta aperti su rotture intrabar che possono rientrare; aggrava i punti 1–2 nelle ore di volatilità.
6. **Divario prompt/motore (E6):** R:R 1,5 invece di 2, filtro saltato senza TP, soglie Toro più basse, TP 5% non applicato, guardrail che alza taglia e leva: ogni LONG marginale costa più del previsto.
7. **Funding solo sui LONG (E7):** erosione contabile piccola ma costante, che peggiora leggermente ogni statistica LONG.

La conferma empirica dell'ordine 1–4 richiede i registri (§6): per ogni LONG perdente lo strumento stampa le feature registrate all'apertura (`ema50_200_4h`, `rsi1h`, `daily_trend`, `trend_change*`, `vol_ratio`) proprio per distinguere "segnale sbagliato" da "conferma anticipata" da "mercato cambiato dopo".

## 4. Perché gli SHORT funzionano (analisi, da confermare coi numeri)

Gli SHORT ereditano gli stessi difetti, ma in regime ribassista i difetti **lavorano a favore**: l'EMA61 "4h" resta sotto quasi sempre, quindi i +20 vanno al lato giusto; momentum, rotture dei minimi e RSI 30–50 si allineano alla direzione dominante; un ingresso "in ritardo o anticipato" in continuazione viene spesso salvato dal trend. In più non pagano funding nel PAPER (E7). Attenzione a due cose prima di dichiarare "gli SHORT vanno bene": (a) il campione è piccolo e il riepilogo non separa le direzioni; (b) il giorno in cui il regime girasse al rialzo, **gli stessi difetti produrrebbero SHORT perdenti sui rimbalzi ribassisti del nuovo trend** — il problema è la cecità al quadro lungo, non il lato LONG in sé.

## 5. Strategia di miglioramento (valutazione richiesta, nessuna modifica applicata)

La separazione proposta (LONG di **continuazione** vs LONG di **inversione**) è la direzione giusta e si innesta bene sui difetti dimostrati:
- prerequisito di entrambe: **storia sufficiente** (≥3.400 candele 15m con paginazione come già fatto per Brain in `4f8776b`, o fetch 4h/1d nativi) così che EMA200 4h ed EMA50/200 1d siano vere; correggere il bug 30–49 barre (E2) nello stesso cambio;
- **continuazione:** consentita solo con EMA50>EMA200 4h vere e 1d non ribassista; ingresso su rottura confermata a candela chiusa (E4) o retest;
- **inversione:** oltre al resto, richiedere l'evidenza strutturale che oggi è solo consultiva (es. `UP_CROSS` su candela chiusa + bias 4h non più DOWN), con taglia ridotta finché il 1d resta contrario — riduzione del rischio, non divieto permanente, in linea col vincolo "niente blocchi rigidi";
- allineare il motore ai prompt (E6) invece di abbassare i prompt al motore: R:R≥2 applicato sempre (e TP obbligatorio o filtro comunque attivo), soglie Toro 75/65, TP minimo 5% Toro, guardrail che non aumenti mai leva/margine di una proposta prudente;
- qualunque parametro va scelto su dati storici **separati** da quelli di valutazione, con commissioni e slippage (il banco di prova storico con motore e regole veri è già in lavorazione come attività separata) e confrontato contro la versione attuale prima di toccare la produzione. Nessuna di queste modifiche è stata applicata: richiedono l'approvazione dell'utente.

## 6. Analisi quantitativa: strumento consegnato

I registri PAPER (`/opt/superbot-desk-data/{hawk,bull}/trade_history.jsonl`) non sono leggibili da questa sessione. È consegnato **`deploy/scripts/audit_long_short.py`** (solo lettura, niente rete, provato su registri sintetici nello schema esatto del motore): separa LONG/SHORT × origine (`claude` / `rules` / `rules_long_s25`) × orizzonte (scalp/medio), prima/dopo il rilascio RC84 delle 12:37 del 12/11 (`--cutoff`), aggrega i parziali per trade (i `net_r` sono additivi), e calcola numero, win rate, profit factor, P&L netto, media R, MAE/MFE in R, durata, leva e motivi di chiusura; elenca ogni LONG perdente con le feature registrate all'apertura e, con `--open-state`, le posizioni ancora aperte. Da eseguire **su una copia** dei dati (o sul ripristino di un backup), un portafoglio alla volta:
`python3 -I audit_long_short.py --history COPIA/hawk/trade_history.jsonl --label Falco --since 2026-11-11T00:00:00Z`.
Leggendo i risultati, ricordare E7: i `net` dei LONG includono un funding che gli SHORT non pagano (il campo `funding` del record permette di ricalcolare al lordo).

## 7. Verifica Brain (RC84)

Verificato che il commit distribuito **contiene** le quattro correzioni (tutte antenate di `ab7e0b7`): `4f8776b` (paginazione Bitget con pagine allineate e sovrapposizione verificata, 3.000+ barre fresche provate su SOL), `c2ee21c` (ultima candela **chiusa** con confini allineati, mai dati fabbricati), `ac44978` (parser `maxLever` fino a 200 con `symbolStatus=="normal"`, fail-closed su valori non interi o fuori 1–200, `backend/v3/runner/contracts.py:48-56`, **senza** alzare il tetto di rischio), `d8130a9` (esito dell'ultimo ciclo e codici motivo persistiti nel heartbeat come `health["last_cycle"]`). La vista di mercato è dichiaratamente a candele chiuse (`brain_market/view.py`), il ciclo è fail-closed su dati mancanti o vecchi (`runner/cycle.py:10`), il prompt DeepSeek tratta NO_TRADE come risposta valida e il motore impone `minimum_equity ≥ 450` (`runner/config.py:149`).

**Non dimostrato e non dimostrabile da qui:** un ciclo analitico completo dopo il rilascio (Brain è in pausa, giustamente non forzato). Alla futura attivazione, la prova si legge **senza aprire posizioni**: nel heartbeat `health.last_cycle` devono comparire, in ordine, (1) regole contrattuali caricate (nessun `no_market_rules`), (2) viste di mercato con `status: ok` sui timeframe (nessun `data_unavailable`), (3) chiamata all'analista riuscita con spesa registrata, (4) una decisione registrata nel journal **anche se è NO_TRADE** — che è un esito corretto, non un fallimento, (5) mandato e limiti invariati. Se il primo ciclo produce NO_TRADE con dati validi, Brain sta funzionando.

## 8. Vincoli rispettati

Nessun accesso alla VPS, nessun ordine PAPER o LIVE, nessun merge/deploy, nessun reset, nessuna modifica a configurazioni, chiavi, servizi di uscita, pause o protezione equity. Consegnati solo questo documento e lo script di analisi in sola lettura, sul ramo di lavoro della sessione. Le correzioni di E1–E7 **non** sono state applicate: sono proposte da approvare.
