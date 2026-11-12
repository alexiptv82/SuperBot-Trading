# RC84 — Fase 2: correzione del motore dei segnali (ramo candidato, NON rilasciato)

**Ramo:** `work/rc84-signals-mtf-closed-20261112`, nato da `ab7e0b7` (versione operativa, intatta). Nessun merge, nessun deploy,
nessuna modifica alla VPS, alle pause, alle posizioni o ai valori di rischio. **Non è una release:** serve il riesame del comportamento
delle strategie e dell'impatto sul rischio.

## 1. Che cosa cambia (per file)
| File | Modifica | Effetto sulle decisioni |
|---|---|---|
| `backend/desk/signals.py` | (a) tutti gli indicatori sulle sole candele **chiuse** (la 15m in formazione è esclusa; "prezzo vs EMA50" usa la chiusura dell'ultima ora chiusa); (b) tendenze 4h e 1d = EMA50 contro **EMA200 vera** su barre **chiuse** native, o ricavate dalle 15m solo se ce ne sono ≥200: **mai una media più corta al posto della EMA200**; barre vecchie, mancanti o di altra granularità → `UNKNOWN`; (c) `UNKNOWN` = nessun punto a nessun lato e `side=0` (nessuna apertura dalle regole), punteggi conservati per gestire le posizioni aperte; (d) bug del trend 1d con 30–49 barre (sempre "bear") eliminato; (e) classificazione **consultiva** `trend_state` (§4); (f) `DAILY_TREND_POINTS = 0`: il 1d è contesto, non punteggio (§5) | sì: è il cuore della correzione |
| `backend/desk/cli.py` | `fetch_htf`: barre native `4H` e `1Dutc` dalla Bitget, con cache (si riscarica un timeframe solo quando ne è terminata una barra più recente: al massimo 1 richiesta ogni 4 h e 1 al giorno per simbolo); politica prudente: **nessuna nuova apertura** (regole o Claude) su un simbolo con tendenza 4h non verificabile, registrata come candidato `trend_sconosciuto`; `policy_shadow_violations`: confronto **in ombra** fra contratto del prompt e controlli del motore, solo registrato (`[POLICY_SHADOW]`, feature `policy_shadow`, heartbeat) | il gate `UNKNOWN` sì; l'ombra **no** |
| `backend/desk/brain.py` | il prompt riceve `stato_trend` (consultivo) | solo informazione a Claude |
| `backend/desk/learning.py` | feature `trend4h_state`, `trend1d_state`, `trend_state` registrate a ogni apertura/candidato | nessuno |
| `backend/tests/test_desk_rc84_phase2.py` | 23 prove nuove (§7) | — |
| `backend/tests/test_desk.py`, `test_long_s25.py` | contratto "storia corta" aggiornato; impronte di `signals.py`/`brain.py` aggiornate con motivazione; il test d'indipendenza Falco/Toro riceve barre 4h valide | — |
| `deploy/scripts/replay_signals_rc84.py` | banco di replay vecchio vs candidato (§6) | — |
Invariati: `engine.py` (formule economiche, stop/TP/liquidazione, DCA), `long_s25.py`, chiusure, storico, learning append-only,
riconciliazione contabile, politica RC84 Falco/Toro, gate S25.

## 2. P0 — Candele chiuse e tendenze multi-timeframe
* **Prima (`ab7e0b7`):** 1.000 candele 15m → ~62 barre 4h → "EMA200" = EMA61; 1d mai disponibile (e con 30–49 barre etichettato "bear");
  l'ultima 15m in formazione entrava nella barra 1h corrente nell'ultimo quarto d'ora.
* **Ora:** EMA200 solo con ≥200 barre chiuse; la serie nativa 4H (1.000 barre = 166 giorni) e 1Dutc (fino a 1.000 giorni) basta in
  esercizio. In mancanza, `UNKNOWN` dichiarato con il motivo (`storia insufficiente`, `dati vecchi`, `barre non coerenti con il
  timeframe`) e nessuna conferma inventata.
* **Politica prudente scelta per `UNKNOWN` 4h:** niente nuove aperture su quel simbolo; uscite, chiusure, stop, TP e DCA invariati
  (prova `test_exits_and_closes_are_not_gated_by_the_trend_state`). Conseguenza da sapere: **se la Bitget non restituisse le barre `4H`,
  non si aprirebbe nulla** (fallisce in sicurezza). Un 1d `UNKNOWN` non blocca (il 1d non dà punti).

## 3. P0 — Contratto del rischio: prompt contro motore (NESSUN valore cambiato)
| Requisito nei prompt | Controllo reale nel motore (`ab7e0b7`, invariato) | Registrato in ombra come |
|---|---|---|
| R:R ≥ 1:2 sempre | R:R ≥ 1,5, e **solo se** SL e TP sono entrambi presenti | `rr_X_sotto_2.0_del_prompt` |
| TP sempre definito | TP assente ammesso: il filtro R:R non si applica e si apre senza target | `tp_assente` |
| Toro: confidenza ≥75 (altcoin) / ≥65 (tier A) | 70 / 60 per tutti | `confidenza_X_sotto_Y_del_prompt_toro` |
| Toro: TP minimo 5% | nessun controllo | `tp_X%_sotto_5%_del_prompt_toro` |
| (implicito) l'AI decide la taglia | il guardrail **alza** margine e leva sotto i minimi (Falco 60$/15x, Toro 200$/15x) | `guardrail_alza_margine_leva` |
| SL sempre definito | SL assente → si usa quello del segnale | `sl_assente` |
**Modifiche di policy proposte, da approvare separatamente (non applicate):** P-1 R:R minimo 2,0 applicato sempre e TP obbligatorio
(o rifiuto); P-2 soglie Toro 75/65 e TP Toro ≥ 5% nel motore; P-3 guardrail che **rifiuta** invece di aumentare margine/leva; P-4 funding
PAPER simmetrico (oggi solo LONG, `engine.py`); P-5 trend 1d nel punteggio (vedi §5: il replay lo sconsiglia). I log `[POLICY_SHADOW]`
misurano, prima di decidere, quante aperture reali ognuna avrebbe cambiato.

## 4. P1 — Continuazione, inversione confermata, rimbalzo non confermato (consultivo)
`signals.classify_trend` (regola verificabile, su barre chiuse): `UNKNOWN` (4h sconosciuta); `RANGE` (|EMA50−EMA200| 4h < 0,3%);
`CONTINUATION_<dir>` (1h nella direzione del 4h); `REVERSAL_CONFIRMED_<dir>` (1h contro il 4h **e** ≥2 chiusure 4h consecutive oltre
la EMA50 4h, EMA50 4h già girata, 1d non contrario); `BOUNCE_UNCONFIRMED_<dir>` (1h contro il 4h senza quella conferma).
**Non è un filtro:** non cambia punteggi né lato (prova dedicata); va al prompt e al learning. Diventerà un vincolo solo se i dati reali
(ora registrati a ogni apertura) e il replay su dati reali lo giustificano.

## 5. P1 — Indipendenza strategica
* Politica RC84 invariata (Falco: scalp da regole/Claude; Toro: medio solo da Claude); gate S25 invariato: nuovi ingressi solo con
  `DESK_LONG_S25=1` **e** Toro **e** `DESK_S25_TORO_ENTRY_APPROVED=1` **e** nessun NO_TRADE esplicito (prova statica + prove esistenti).
* Duplicati: uno stesso segnale delle regole apre solo su Falco (prova esistente, adeguata); i duplicati dell'11/11 erano S25, oggi spento.
* Esposizione correlata residua: Claude può scegliere lo stesso simbolo/lato su Toro (medio) e Falco (scalp). **Nessun divieto
  introdotto**; proposta: misurarla con l'analizzatore della fase 1 (stesso simbolo/lato aperto su entrambi) prima di decidere un limite.

## 6. Replay vecchio contro candidato (stessi dati, stessa metodologia)
`deploy/scripts/replay_signals_rc84.py`: 7 regimi sintetici (ribassista, rialzista, laterale, ribasso con rimbalzi, rialzo con correzioni,
inversione rialzista, inversione ribassista) × 6 semi = 42 percorsi di 240 giorni, 30 giorni valutati ciascuno; ciclo ogni 15 min a 5/10
min dall'apertura della candela (candela in formazione costruita dalle 5m già chiuse); percorso **regole di Falco** con `rules_decisions`,
politica RC84, cooldown, soglie, filtro R:R e `PaperAccount` veri (commissioni, slippage, funding, stop giornaliero). Nessun dato futuro.
Risultati (`rp/confronto.txt` riprodotto con i comandi di §9):

| Versione | Trade | LONG netto | SHORT netto | Totale netto | Drawdown |
|---|---:|---:|---:|---:|---:|
| RC84 `ab7e0b7` | 1.629 | −1.615,54 $ | −3.130,07 $ | −4.745,61 $ | 4.826,21 $ |
| **Candidato** | **1.517** | **−1.245,16 $** | **−2.513,47 $** | **−3.758,63 $** | **3.818,98 $** |
| Candidato + 1d a 15 punti | 2.309 | −3.194,97 $ | −4.136,96 $ | −7.331,93 $ | 7.375,19 $ |

Confronto **appaiato** per percorso (candidato − RC84): LONG +8,82 $/percorso (migliorati 26/42, t=+1,00), SHORT +14,68 $ (27/42,
t=+1,54), totale +23,50 $ (27/42, t=+1,99). Con il 1d a 15 punti: totale −61,58 $/percorso (14/42, t=−3,25).
**Tabella dei regressi del candidato** (peggio di max(20 $, 5%) per regime e lato): rialzista LONG −91,79 $ (72→96 trade); laterale
SHORT −47,14 $ (128→134); rialzo con correzioni LONG −31,03 $ (79→75). Tutti dentro il rumore del campione (~±150 $ per cella).
Con il 1d a 15 punti i regressi sono 11 su 14 celle e i trade +42%.

**Come leggerli.** I mercati sintetici sono passeggiate casuali con deriva: nessuna regola tecnica ha un vantaggio reale, quindi i
netti negativi in tutte le versioni misurano i **costi** (commissioni, slippage, funding) e la frequenza, non la redditività futura.
Il replay serve a confrontare il **comportamento**: il candidato apre il 7% di trade in meno, con drawdown più basso, e non peggiora gli
SHORT (anzi migliorano, t=+1,54); il miglioramento dei LONG è nella direzione attesa ma **non significativo** (t=+1,00). Il 1d nel
punteggio aumenta molto le aperture e peggiora in modo significativo: **resta a 0** (P-5 sconsigliata). La classificazione consultiva
non può essere valutata seriamente su dati senza struttura: in questo replay le aperture delle regole cadono quasi tutte in
`CONTINUATION_*` (il punteggio include già il 4h). La sua validazione richiede dati reali.

## 7. Test eseguiti (locali, nessuna Actions)
* `test_desk_rc84_phase2.py` (nuovo): 23/23 — EMA200 mai accorciata; barre native chiuse, barra in formazione ignorata; punti 4h al
  lato giusto; dati vecchi e granularità sbagliata → UNKNOWN; 1d vero o UNKNOWN (mai "bear" falso), 0 punti; spike nella 15m in
  formazione senza effetto; classificazione (9 casi) e sua neutralità sui punteggi; cache 4h/1d (una richiesta per barra chiusa, errori
  → None); ombra del rischio (TP assente, R:R, soglie Toro, TP 5%, guardrail) che non blocca; gate S25 invariato; ciclo vero: 4h
  sconosciuta → nessuna apertura e candidato `trend_sconosciuto`; 4h nota → apertura con stato e ombra registrati; chiusure non bloccate.
* Suite completa `backend/tests` (Python 3.13, esclusi 2 moduli che non si importano con la SQLAlchemy di questa macchina:
  `test_auth_flow.py`, `test_profiles_engine.py`, estranei al desk): **`ab7e0b7` 6.952 superati, 26 falliti, 9 saltati, 3 xfail;
  candidato 6.975 superati, 26 falliti, 9 saltati, 3 xfail.** I 26 falliti sono **gli stessi** nelle due versioni (preesistenti:
  14 `test_desk.py`, 6 `test_v3_rc84_same_cycle_exposure.py`, 2 `test_v3_runner_daily_loss.py`, 1 ciascuno in `rc82_active_paper_stops`,
  `rc84_claim_integration`, `rc84_claim_visibility`, `rc84_import_paths`): nessun fallimento nuovo, +23 superati (le prove nuove).
* Replay rieseguito: risultati identici bit per bit (semi fissi).

## 8. Problemi residui
1. **Granularità Bitget:** lo storico `1Dutc` da `history-candles` è verificato sulla VPS (§8B). Resta da verificare `4H` con
   `limit=1000` su `/market/candles`: se fosse rifiutata, nessuna apertura (sicuro ma bloccante).
2. Replay solo sintetico e solo regole: niente Claude, niente dati di mercato reali. Per dati reali serve una copia delle candele
   storiche (lo script accetta qualsiasi `desk`; il generatore di mercato va sostituito con un lettore di file, non fatto).
3. Classificazione `trend_state` non validata: resta consultiva.
4. 26 prove falliscono già in `ab7e0b7` (14 di `test_desk.py` scritte prima della politica RC84 che rifiuta i "medio" su Falco, le
   altre in moduli RC82/RC84): preesistenti, identiche nel candidato, non toccate.
5. Policy P-1…P-5 non applicate: decisione dell'utente.

## 8B. Fase 2B — storico giornaliero Bitget paginato (aggiunta al candidato)
**Fatto verificato dall'utente sulla VPS (12/11/2026):** `/api/v2/mix/market/history-candles`, granularità `1Dutc`, 3 richieste da 89
giorni per simbolo → 267 candele chiuse per BTCUSDT ed ETHUSDT, nessuna interruzione (18/02–11/11/2026); `/market/candles` ne dava 89.
| Requisito | Come è fatto (`backend/desk/cli.py`, `signals.py`) |
|---|---|
| ≥ 250 barre giornaliere quando esistono | `fetch_daily_history`: pagine da 89 giorni all'indietro da oggi 00:00 UTC, fino a 260 barre chiuse o 4 pagine (356 giorni); 3 pagine bastano per 267 |
| paginazione, ordine, sovrapposizioni, duplicati | `merge_bars`: un timestamp per barra (vince la riga scaricata per ultima; i conflitti si contano), ordine crescente, bordi delle pagine deduplicati |
| candele in formazione | escluse in `merge_bars` (apertura + durata > ora) e di nuovo in `signals.closed_bars` |
| cache e limiti | prima ricostruzione una volta; poi **una** pagina al giorno (incrementale, le barre vecchie restano); 4H una richiesta per barra 4h chiusa; dopo un errore niente nuovi tentativi per 30 minuti; tetto di **12 pagine storiche per ciclo** per tutti i simboli (gli altri si completano ai cicli successivi; intanto il loro 1d è `UNKNOWN`, che non blocca) |
| coerenza 4H e 1Dutc | una risposta con anche un solo timestamp non allineato al periodo è **rifiutata in blocco** (non sono barre di quella granularità) e non entra in cache; righe non finite o con prezzi ≤ 0 scartate |
| interruzioni | `signals.htf_trend` usa solo la coda più recente senza buchi oltre 3 giorni (un fine settimana dei metalli è tollerato); prima del buco la serie non si incolla |
| storia insufficiente | `UNKNOWN` con il motivo (`storia insufficiente: N barre chiuse < 200`, `dati vecchi`), nessun dato inventato, EMA200 mai accorciata; un simbolo con storia finita non viene ricostruito ogni giorno da capo |
| il 1d non diventa un filtro | invariato: `DAILY_TREND_POINTS = 0`, il gate resta solo sulla tendenza 4h; prova con 4h rialzista e 1d ribassista: il LONG si apre |
| stop, TP, chiusure, registri | non toccati; prova della catena completa (finto Bitget → `fetch_htf` → `read_symbol` → ciclo vero) |
Il heartbeat riporta per simbolo lo stato dei dati (`HB["htf"]`: `ok`, `cache`, `errore_api`, `attesa_dopo_errore`, `storia_finita`,
`budget_esaurito`, `incompleto`) e le tendenze lette. Prove: `backend/tests/test_desk_rc84_phase2b.py` (13): paginazione a 3 pagine e 267
barre, simbolo recente (pagina vuota → stop, `UNKNOWN`, poi una sola pagina al giorno), cache stesso giorno/giorno dopo, errore a metà
paginazione e attesa di 30 minuti, cache scaduta con errore → serie vecchia dichiarata "dati vecchi", buchi lunghi e corti, tetto di
richieste per ciclo, righe non valide e conflitti, granularità sbagliata per 4H e 1Dutc, URL ed errori HTTP/JSON, 1d non bloccante,
catena completa nel ciclo vero. Replay: invariato (identico alla fase 2: i percorsi sintetici non hanno buchi).

**Ancora da verificare con una lettura sulla VPS prima di qualunque rilascio:** `/market/candles` con `granularity=4H&limit=1000`
(numero di barre e allineamento) e il parametro `limit=200` di `history-candles` usato qui (la pagina da 89 giorni ne contiene 90 al massimo).

## 8C. Fase 2C — continuità esatta delle serie e calendari di mercato
**Problema corretto:** in 2B `signals.py` tollerava buchi fino a 3 giorni in qualunque serie 4h/1d, quindi EMA50/EMA200 potevano
essere calcolate su serie crypto incomplete. `MAX_GAP_MS` è stato **eliminato**.
* **Crypto (24/7, predefinito):** ogni barra deve seguire la precedente di **esattamente** 4h o 1 giorno. Una barra mancante è
  un'interruzione: si usa solo la coda continua più recente; se è più corta di 200 barre la tendenza è `UNKNOWN` con un motivo
  verificabile, per esempio `storia insufficiente: 49 barre chiuse < 200; serie interrotta: 1 barre mancanti dopo 2026-11-03T08:00Z`.
* **Metalli (`XAU`, `XAG`, calendario `chiusura_weekend`):** sono ammesse **solo** le barre mancanti che aprono di sabato o domenica UTC;
  una barra mancante in un giorno feriale è un'interruzione. Il calendario esatto della Bitget per i metalli **non è verificato**
  (§8C-residui): festività o orari diversi diventano interruzioni, cioè `UNKNOWN` nel dubbio, mai una tendenza su dati incompleti.
  Con il mercato chiuso nel fine settimana l'ultima barra è vecchia, quindi la tendenza è `UNKNOWN` fino alla riapertura.
* **Duplicati:** identici → uniti; **stesso timestamp con valori diversi → serie rifiutata** (`duplicati in conflitto: N`).
  (Il livello di rete `merge_bars` tiene invece la riga scaricata per ultima e conta i conflitti, prima che la serie arrivi qui.)
* **Intervalli irregolari:** un'apertura fuori dalla griglia del periodo → serie rifiutata (`aperture non allineate`); righe in ordine
  sparso → ordinate; candele future o in formazione → escluse. Nessuna barra inventata o interpolata: si scarta, non si ripara.
* Nei fatti della lettura: `market_calendar`, `trend4h_gaps`, `trend1d_gaps`; in `htf_trend`: `last_gap`.
* Invariati: recupero paginato, cache, budget di richieste (2B), politica della fase 2 (gate solo sul 4h, 1d a 0 punti), motore PAPER,
  rischio, strategie. Prove: `backend/tests/test_desk_rc84_phase2c.py` (13); la prova 2B che tollerava buchi di 2 giorni per tutti
  è stata ristretta al taglio della serie (il contratto è cambiato di proposito in 2C).

### 8C-1. Classificazione dei 26 fallimenti preesistenti (identici in `ab7e0b7` e nel candidato; nessun contratto di test modificato)
| Prove | Causa verificata | Classe |
|---|---|---|
| `test_desk.py` (14: ciclo completo, DCA, pausa/svuotamento, ripresa, entrata diversificata, registro chiusure, calendario Claude) | le prove propongono aperture `medio` su Falco; la politica RC84 (`_rc84_paper_classic_entry_policy`, 12/11) le rifiuta (`[RC84_POLICY:HAWK] ... tipo=medio`) | **test obsoleti** (contratto cambiato da RC84) **con perdita di copertura**: DCA, entrata diversificata, svuotamento in pausa e ripresa non sono più provati nel ciclo vero |
| `test_v3_rc82_active_paper_stops.py::test_recent_quote_still_opens_and_still_adds_dca` | stessa causa (regole `medio` su Falco) | test obsoleto, **perdita di copertura** dell'apertura + DCA con quotazione recente |
| `test_v3_rc84_claim_integration.py::test_open_is_blocked_while_a_claim_is_unresolved_and_allowed_after_reconciliation` | stessa causa: l'apertura "dopo la riconciliazione" non avviene per la politica, non per il claim | test obsoleto; **attenzione:** la parte "bloccato con claim irrisolto" passa per il motivo sbagliato, quindi **la protezione dei claim non è più dimostrata** da questa prova |
| `test_v3_rc84_same_cycle_exposure.py` (3 `close_then_open...`) | stessa causa (regole `medio` su Falco) | come sopra: **protezione "nessuna nuova esposizione nello stesso ciclo con claim irrisolto" non più dimostrata** per le aperture delle regole |
| `test_v3_rc84_same_cycle_exposure.py` (3 `s25_entry_after_a_time_close...`) | i nuovi ingressi S25 sono spenti di default (5d21d14: servono Toro + `DESK_S25_TORO_ENTRY_APPROVED=1`); la prova usa Falco con solo `DESK_LONG_S25=1` | test obsoleto (comportamento voluto: S25 spento) |
| `test_v3_runner_daily_loss.py` (2) | il heartbeat del runner Brain contiene `last_cycle`, aggiunto da `d8130a9` (11/11); le prove confrontano il heartbeat "esatto" di prima | test obsoleto (contratto cambiato da `d8130a9`) |
| `test_v3_rc84_claim_visibility.py::test_unauthenticated_overview_is_refused_and_no_write_routes_were_added` | la rotta `GET /api/v3/brain/config` (aggiunta da `e87e913`, 11/11, sola lettura) non è nell'elenco atteso; la parte "solo GET oltre a brain/close" passa | test obsoleto (rotta in sola lettura legittima); nessuna rotta di scrittura nuova |
| `test_v3_rc84_import_paths.py::test_auth_and_profiles_before_the_subprocess_lock_tests_in_both_orders` | `SQLAlchemy 2.0.28` non si importa con Python 3.13 (`TypingOnly ... __static_attributes__`) | **ambiente** (lo stesso per cui `test_auth_flow.py`/`test_profiles_engine.py` sono esclusi); va rieseguita con Python 3.11 o SQLAlchemy ≥ 2.0.31 |
**Possibili difetti operativi:** nessun difetto del prodotto dimostrato. Il rischio vero è la **copertura persa**: 20 prove su 26
falliscono prima di arrivare a ciò che dovevano dimostrare (DCA, pausa, entrata diversificata, blocco con claim irrisolto). Proposta
(non applicata, da approvare): riscriverle con aperture `scalp` su Falco (o `medio` da Claude su Toro), così da provare di nuovo quelle
protezioni nel ciclo vero, senza cambiare il loro scopo.

### 8C-residui
1. Calendario Bitget dei metalli (orari di chiusura e festività) non verificato: nel dubbio `UNKNOWN`. Una lettura in sola lettura sulla
   VPS delle barre 4H/1Dutc di XAUUSDT/XAGUSDT direbbe quali barre mancano davvero.
2. Le verifiche già fatte sulla VPS (ETH 4H 539 barre, BTC/ETH 1Dutc 267 barre, nessuna interruzione, `limit=200`) restano valide: con
   serie continue la 2C non cambia nulla, come conferma il replay identico.

## 8D. Hardening finale (candidato congelato per la revisione indipendente)
### Duplicati lungo tutta la catena
Prima: `merge_bars` (cli.py) **sovrascriveva** una candela con lo stesso timestamp e valori diversi (vinceva l'ultima scaricata), quindi
`signals.series_check` non poteva più vedere il conflitto. Ora:
* duplicati **identici** (bordi delle pagine, righe ripetute) → uniti;
* stesso timestamp con valori **diversi** — nella stessa risposta 4H, fra due pagine dello storico 1Dutc, o fra la cache e un download
  successivo — **non viene risolto**: entrambe le versioni arrivano a `signals`, che rifiuta la serie (`duplicati in conflitto`), il
  trend è `UNKNOWN`, la cache di quel simbolo/timeframe si svuota, si attende 30 minuti e si ricostruisce da capo. Stato nel heartbeat:
  `conflitto_dati`;
* effetto sulle decisioni: un conflitto nel 4H → nessuna nuova apertura su quel simbolo (`[TREND_UNKNOWN] … duplicati in conflitto`,
  candidato `trend_sconosciuto`); un conflitto nel 1Dutc → trend 1d `UNKNOWN`, che come sempre non autorizza nulla (0 punti, nessun gate).
Prove end-to-end in `backend/tests/test_desk_rc84_hardening.py`: pagine diverse con duplicati identici; conflitto fra due pagine;
conflitto fra cache e download successivo; conflitto dentro una risposta 4H (con attesa senza nuove richieste); duplicati identici
innocui; ciclo vero con conflitto 4H (nessuna apertura, motivo registrato); ciclo vero con duplicati identici (apertura normale); ciclo
vero con conflitto 1Dutc (politica fase 2 invariata).

### Le prove preesistenti recuperate (stesse verifiche, contratti attuali)
| Prove | Adattamento (nessun comportamento operativo cambiato) | Ora verificano di nuovo |
|---|---|---|
| `test_desk.py` (14) | il finto exchange serve anche le barre 4H, ricavate dalla **stessa** serie 15m (solo gruppi completi e chiusi); le proposte di Claude su Falco sono `scalp` | ciclo completo, DCA, svuotamento in pausa, ripresa, entrata diversificata, registro delle chiusure, calendario di Claude |
| `test_v3_rc82_active_paper_stops.py` (1) + `test_v3_rc84_claim_integration.py` (1) + `test_v3_rc84_same_cycle_exposure.py` (3) | `_entry` delle regole `scalp` (Falco); lettura con tendenza 4h nota (`rc84_test_support.known_4h_trend`) e, solo per ingressi/DCA, storia piatta più vecchia dell'apertura (`with_history`) per superare la soglia di 80 candele | apertura + DCA con quotazione recente; **blocco delle aperture con claim irrisolto e sblocco dopo la riconciliazione** (prima passava per il motivo sbagliato); nessuna nuova esposizione nello stesso ciclo con claim irrisolto |
| `test_v3_rc84_same_cycle_exposure.py` (3 S25) | eseguite su **Toro con l'autorizzazione** `DESK_S25_TORO_ENTRY_APPROVED=1`; **aggiunta** la prova che senza autorizzazione (Falco o Toro) S25 non apre nulla e chiude comunque a tempo | blocco di S25 con claim irrisolto; percorso sano; nessun ingresso S25 senza opt-in |
| `test_v3_runner_daily_loss.py` (2) | heartbeat Brain atteso con `last_cycle` (contratto di `d8130a9`) | campi della perdita giornaliera e assenza dei campi daily_loss senza il gancio |
| `test_v3_rc84_claim_visibility.py` (1) | elenco rotte con `GET /api/v3/brain/config` (`e87e913`), verificata in sola lettura | nessuna rotta di scrittura nuova |
| `test_v3_rc84_import_paths.py` (1) + `test_auth_flow.py` + `test_profiles_engine.py` | **non modificate**: problema d'ambiente (SQLAlchemy 2.0.28 non si importa con Python 3.13) | eseguite con Python 3.11 + `requirements.txt`: **49/49** sia su `ab7e0b7` sia sul candidato |
Una barriera comune (`backend/tests/conftest.py`) svuota la cache delle barre 4h/1d fra una prova e l'altra e impedisce alle prove di
chiamare la Bitget per lo storico.

### Validazione finale
* EMA50/EMA200 4H e 1D confrontate con un calcolo indipendente (`pandas ewm(adjust=False)`): identiche.
* Candele 4H e 15m in formazione con movimenti estremi: lettura identica a quella senza di loro.
* Serie mancanti/interrotte/in conflitto → `UNKNOWN` (prove 2C e hardening).
* Chiusure PAPER, stop, TP, DCA, storico e riconciliazione: suite RC82/RC84 integralmente verdi.
* Nessuna esposizione duplicata: lo stesso segnale in due cicli apre una sola posizione; sullo stesso segnale delle regole Toro non apre.

### Risultati della validazione finale (candidato congelato)
| Esecuzione | `ab7e0b7` | Candidato 2C | **Candidato hardening** |
|---|---|---|---|
| Suite `backend/tests`, Python 3.13 (esclusi `test_auth_flow.py`, `test_profiles_engine.py`) | 6.952 ok, 26 falliti | 7.001 ok, 26 falliti | **7.039 ok, 1 fallito** (`test_v3_rc84_import_paths`, ambiente SQLAlchemy) |
| Moduli SQLAlchemy con Python 3.11 + `requirements.txt` | 49/49 | — | **49/49** |
| Replay 42 percorsi | base | identico a 2/2B | **identico** (bit per bit) |
**Candidato congelato** per la revisione indipendente (Grok): lo SHA è quello del commit che contiene questa sezione; nessun tag
creato (un tag potrebbe avviare workflow). Non è una release.

## 9. Riproduzione
```sh
python3 deploy/scripts/replay_signals_rc84.py run --backend <checkout ab7e0b7>/backend --label rc84_ab7e0b7 --out rc84.json
python3 deploy/scripts/replay_signals_rc84.py run --backend backend --label candidato --out cand.json
python3 deploy/scripts/replay_signals_rc84.py run --backend backend --label candidato_1d15 --daily-points 15 --out cand15.json
python3 deploy/scripts/replay_signals_rc84.py compare rc84.json cand.json cand15.json
# moduli SQLAlchemy: python3.11 -m venv v && v/bin/pip install -r backend/requirements.txt && PYTHONPATH=.:backend v/bin/python -m pytest -q backend/tests/test_auth_flow.py backend/tests/test_profiles_engine.py backend/tests/test_v3_rc84_import_paths.py
PYTHONPATH=.:backend python3 -m pytest -q backend/tests/test_desk_rc84_phase2.py backend/tests/test_desk_rc84_phase2b.py backend/tests/test_desk_rc84_phase2c.py backend/tests/test_desk_rc84_hardening.py backend/tests/test_long_s25.py backend/tests/test_desk.py
```
I risultati sono deterministici (semi fissi): rieseguendo si ottengono gli stessi numeri.
