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
1. **Granularità Bitget da verificare** (la sandbox non raggiunge la Bitget): `4H` e `1Dutc` con `limit=1000` sull'endpoint
   `/api/v2/mix/market/candles`. Se `4H` fosse rifiutata, nessuna apertura (sicuro ma bloccante); verifica in sola lettura prima di
   qualunque rilascio.
2. Replay solo sintetico e solo regole: niente Claude, niente dati di mercato reali. Per dati reali serve una copia delle candele
   storiche (lo script accetta qualsiasi `desk`; il generatore di mercato va sostituito con un lettore di file, non fatto).
3. Classificazione `trend_state` non validata: resta consultiva.
4. 26 prove falliscono già in `ab7e0b7` (14 di `test_desk.py` scritte prima della politica RC84 che rifiuta i "medio" su Falco, le
   altre in moduli RC82/RC84): preesistenti, identiche nel candidato, non toccate.
5. Policy P-1…P-5 non applicate: decisione dell'utente.

## 9. Riproduzione
```sh
python3 deploy/scripts/replay_signals_rc84.py run --backend <checkout ab7e0b7>/backend --label rc84_ab7e0b7 --out rc84.json
python3 deploy/scripts/replay_signals_rc84.py run --backend backend --label candidato --out cand.json
python3 deploy/scripts/replay_signals_rc84.py run --backend backend --label candidato_1d15 --daily-points 15 --out cand15.json
python3 deploy/scripts/replay_signals_rc84.py compare rc84.json cand.json cand15.json
PYTHONPATH=.:backend python3 -m pytest -q backend/tests/test_desk_rc84_phase2.py backend/tests/test_long_s25.py backend/tests/test_desk.py
```
I risultati sono deterministici (semi fissi): rieseguendo si ottengono gli stessi numeri.
