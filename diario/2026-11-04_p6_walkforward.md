# 2026-11-04 (sera) — P6: walk-forward delle celle di expectancy (PR #50, bozza)

**Claude Sonnet 5.5 — coordinatore tecnico** · modulo: codice di Grok (Modalità B: consegna come testo, applicata invariata, poi corretta in un commit a parte) · funzioni pure, nessun collegamento col Brain, col journal, coi prompt, con soglie o limiti

`backend/v3/learning/walkforward.py`: `make_folds` (finestre rolling/expanding con embargo, a giorni interi) e `walk_forward` (per ogni fold sceglie le celle `positive` con `cell_stats` **solo sul train**, le misura sul test che segue; riporta medie in-sample / out-of-sample / resto e `decay_bp = is − oos`). **Nessuna soglia nel codice**: `min_trades`, `min_days`, `confidence`, `n_boot`, `seed` sono argomenti obbligatori.

## Cosa ho trovato nel modulo di Grok
1. **`decay_bp` con doppio arrotondamento**: differenza di due medie già arrotondate a 4 decimali invece dei valori esatti (il contratto dice «arrotondato una volta sola»). 14 confronti su 72 con l'oracolo `Fraction` differivano, solo su `decay_bp`. Corretto: `(S_is·n_oos − S_oos·n_is) / (n_is·n_oos)` in contesto locale a 60 cifre, arrotondato una volta.
2. **Costo O(N·S)**: `key()` rivalutata più volte per trade e finestre trovate con scansione completa. Test «molte celle» 37,6 s → 0,9 s; 60 000 trade × 20 celle × 40 fold in 1,9 s. Ora `key()` una volta per trade, trade ordinati per chiusura una volta, finestre con ricerca binaria manuale (niente `bisect`: il test di purezza di Grok ammette solo `{__future__, collections, dataclasses, decimal, typing, backend}`).
3. Minori: `folds` solo `list`/`tuple` invece di `Sequence`; import non usati e `_check_int_day` morto; docstring con le regole esatte.
Consegna ancora debole: 6 test; mutazione, velocità e stub di `cell_stats` richiesti dal prompt e non fatti; numeri di riga del rapporto sbagliati. **I soli 6 test di Grok uccidono 14 mutanti su 90.**

## Verifica
- Commit: `ce61a4e` Grok invariato · `6304a95` miei test (rossi sul modulo di Grok solo per i difetti veri) · `581047f` altri test · `0717b35` correzione (contratto e `make_folds` invariati) · `be7053f` test dalla mutazione.
- **394 test** nei due file (388 miei + 6 di Grok); suite V3 2785 → **3179 passed**, 3 xfailed; 3 failed per `fastapi` mancante, invariati. Passa dalla radice e da `cd /tmp`.
- Oracolo `Fraction` indipendente (72 confronti con guardie, vettore a mano `is 80.0000 / oos 42.5000 / rest −7.2000 / decay 37.5000`); `cell_stats` sostituita con stub e spia (1 + F chiamate, stesso seed, selezione = solo `positive`); nessuna fuga con meta-test; validazione esaustiva con ordine per ogni coppia; scale estreme (overflow del decadimento → errore tipizzato); purezza AST sui nomi.
- **Mutazione 89/90** su una copia del repo. L'unico sopravvissuto è equivalente (`step_ms <= 0` → `step_ms < 0`: con `step_ms = 0` lo rifiuta comunque `step_ms < test_ms`). Un secondo sopravvissuto era un buco nei miei test (sottoclasse di `Fold` accettata da `isinstance`); fissato e ucciso.

## Limiti
La selezione resta su molte celle (confronti multipli): il decadimento misura l'effetto, non lo rimuove; i fold scorrevoli non sono indipendenti quando `train_ms > step_ms`; un trade del test in una cella selezionata può essere stato aperto durante il train (non è fuga, l'embargo serve ai trade lunghi); le celle mai viste nel train finiscono in `rest`; nessun dato reale usato. **Le soglie statistiche le deve scegliere l'utente.**

## Prossimo
- **P9**: rilevatori delle 12 schede a sole candele → `Candidate` per P5 (Grok; prompt in preparazione, contratto comune prima; si può dividere fra due AI su file diversi).
- Poi: laboratorio su storico BTC/ETH in CI (il caricatore deve spezzare ai buchi), poi produttore di candidati per P5.
- Decisioni dell'utente aperte (non bloccano): le 4 soglie di `RegimeParams`; le soglie statistiche di P6 (`min_trades`, `min_days`, `confidence`, `n_boot`, `seed`); politica di esplorazione del Brain in PAPER; tocchi ambigui stop/target (`stop_first` consigliato); L1 (`strategy_id` nel journal) e L4 (shortlist nel prompt del Brain) richiedono OK esplicito; certificazione backup F0 e import dei 534 trade legacy (richiedono OK e VPS).

⛔ Nessun merge/deploy · `DESK_MODE=paper` invariato · Hawk/Bull non toccati · cervello intatto.
