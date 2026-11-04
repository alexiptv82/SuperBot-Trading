# 04/11 (pomeriggio) — P4 modulo 1: expectancy per cella, consegna di Grok verificata e corretta, PR #44 DRAFT

**AI:** Claude Sonnet 5.5 (coordinatore) · modulo: codice di Grok 4.7 (Modalità B, consegna come testo) · **Branch:** `work/v3-p4-expectancy-grok-20261104` (testa `2726c01`, impilato su P3/#43) · **PR:** #44 DRAFT

---

## Cosa è stato fatto

`backend/v3/learning/expectancy.py`: `cell_stats(...)` calcola per ogni cella (default: simbolo, lato, regime della decisione, manuale/Brain) l'**expectancy netta dei costi in bp**, mediana, costi, R medio, win rate (solo informativo) e un **intervallo di confidenza a blocchi di giorni** (bootstrap percentile, seme stringa deterministico). `status` ∈ positive / negative / inconclusive / insufficient. Nessuna soglia nel codice: `min_trades`, `min_days`, `confidence`, `n_boot`, `seed` sono argomenti obbligatori.

Tre commit tenuti separati: `b24944c` la consegna di Grok **invariata**; `4eb5e47` correzioni + suite indipendente di Claude (243 test); `2726c01` un test in più.

## Cosa non tornava nella consegna di Grok

- Il rapporto diceva "539 passed" e "DUBBI: nessuno". Rilanciato: **544 passed** (525 + 19). Test d'integrazione con i produttori veri non consegnato.
- **Indici percentile ≠ contratto** (half-even invece di floor/ceil−1): coincidono solo con `confidence=0.9, n_boot=200`, l'unico valore dei suoi test. Con `0.95/300` o `0.95/220` l'intervallo era sbagliato in silenzio.
- `confidence` NaN → eccezione non tipizzata; `key` validata solo sul primo trade; `None`/generatore come input → errore fuorviante; `TradeOutcome` a mano con NaN/float → numeri falsi; chiavi `(1,)`/`(True,)` che si fondevano rendendo il risultato dipendente dall'ordine; `format_cells` senza intervallo.
- Dimostrato con una sonda ostile e un **oracolo** (`Fraction`, scritto dal testo del contratto) prima di correggere.

## Verifica

- Suite V3 **788 passed**. Contro il modulo originale di Grok la mia suite fallisce in 67 test su 243 (file ripristinato dopo la prova).
- Catena con i produttori veri: `BrainEngine → execute_paper → close_paper → extract_outcomes → cell_stats` su 11 posizioni, numeri attesi in forma chiusa.
- **Mutazione 82/84** (cache bytecode bypassata); i 2 sopravvissuti sono equivalenti (`True`/`False` valgono 1/0 e la soglia li rifiuta comunque). **La sola suite di Grok ne uccide 26/84.**

## Limiti dichiarati

- **Confronti multipli non corretti:** con molte celle, qualcuna risulterà `positive` per caso. È un filtro, non una prova: serve conferma fuori campione (walk-forward).
- Blocchi = giorni UTC singoli: non catturano regimi di più giorni.
- Chiavi personalizzate: `repr` deterministico. `invalid_outcome` ora copre anche i `TradeOutcome` inutilizzabili.
- Nessun dato reale usato (import dei 534 trade legacy bloccato su F0, OK utente e VPS). I valori statistici li sceglie l'utente.

## Prossimo

Prompt a Grok per il secondo modulo (P5): **Opportunity Cost Engine, nucleo di etichettatura** `backend/v3/learning/opportunity.py` — etichetta a posteriori candidati long/short non eseguiti con candele (tocco stop/obiettivo, esito a +15 min/+1 h/+4 h) per superare il limite del campione. Nel Project: `claude/prompt-grok-p5-opportunity-2026-11-04.md`. Il prompt incorpora le lezioni di questo modulo (valori di parametro dove le alternative divergono, ogni elemento validato, tabella regola → riga di codice). Argomento da decidere per l'utente: policy sui tocchi ambigui (stop e obiettivo nella stessa candela) — obbligatoria, nessun default.

⛔ Nessun merge/deploy · DESK_MODE=paper invariato · Hawk/Bull non toccati · cervello intatto · nessuna modifica a strategia, soglie, limiti di rischio o prompt.
