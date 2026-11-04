# 2026-11-04 (pomeriggio) — P5 FATTO: etichettatura delle opportunità (Opportunity Cost Engine, nucleo) — PR #45 DRAFT

**Claude Sonnet 5.5 — coordinatore tecnico** · modulo: codice di Grok (Modalità B: consegna come testo, nessun push)

## Cosa è stato fatto
`backend/v3/learning/opportunity.py`: `label_candidates(candidates, candles, *, candle_ms, horizons_ms, cost_bp, ambiguous_policy)` etichetta a posteriori i **candidati non eseguiti** (long e short): per ogni orizzonte (es. 15 min, 1 h, 4 h) dice se è stato toccato prima lo stop o l'obiettivo (o nessuno: timeout), con `gross_bp`/`net_bp` a 4 decimali. Serve a far crescere il campione utile per `cell_stats` (#44) oltre i soli trade eseguiti. **Etichetta soltanto: non decide, non apre, non chiude nulla.** Nessuna scelta di modello nel codice: `candle_ms`, `horizons_ms`, `cost_bp`, `ambiguous_policy` sono argomenti obbligatori.

PR **#45** (DRAFT, base `main`, impilata su #44), ramo `work/v3-p5-opportunity-grok-20261104`, 5 commit separati:
`0889106` consegna di Grok **invariata** · `330ca96` correzioni al modulo · `fc72786` test con oracolo indipendente · `4b8d13e` test più stretti dopo la mutazione · `8fc808b` i 3 test sbagliati di Grok marcati `xfail(strict)` con la ragione.

## Cosa ho trovato nella consegna di Grok
- Il suo rapporto: "14 passed, 3 failed", "MUTANTI: NON ESEGUITO", blocco REGOLE → CODICE troncato. Misurato: 15 passed + 2 failed dalla radice (14/3 da un'altra cartella: `test_purity` dipende dalla cwd).
- **Generatore come `candidates` consumato dalla validazione → risultato `()` in silenzio**; idem una serie di candele (orizzonti `incomplete` come se mancassero i dati) e gli insiemi accettati.
- Id `"c1\n"` accettato (`re.match`); `_CTX` dichiarato ma **mai usato** (con un contesto globale a bassa precisione il risultato cambia o solleva `InvalidOperation`); overflow numerico grezzo; indice tempo→candela ricostruito per candidato; `-0.0000` possibile.
- 3 dei suoi 17 test sono sbagliati (attesa errata; generatore di dati con candele non valide e "oracolo" che ricopia il modulo; purezza dipendente dalla cartella corrente con whitelist senza `collections.abc`).
- La sua suite uccide 35 dei 101 mutanti.

## Verifica (riproducibile)
- Suite V3 (`test_brain_*` + `test_v3_*`): **923 → 1215 passed** (+14 test di Grok invariati +278 miei), 3 xfailed. 3 failed identici su #44 e non toccati (manca `fastapi` in questo ambiente).
- Oracolo indipendente `Fraction` (algoritmo diverso dal modulo) su 80 dataset di candele valide, ogni campo di ogni etichetta, con guardie sui casi difficili; valori a mano (anche pareggi half-even); confini della finestra; coerenza fra orizzonti; codici d'errore esatti e 15 coppie nell'ordine; purezza AST.
- Contro il modulo originale di Grok la mia suite fallisce in 14 casi su 278.
- **Mutazione 99/101** (cache bytecode bypassata, ripristino verificato per hash); i 2 sopravvissuti sono equivalenti. La prima passata ne lasciò 7: erano buchi dei **miei** test (candele cattive con lo stesso `open_time` delle buone → la serie falliva per l'ordine, non per il controllo specifico). Corretti.

## Limiti dichiarati
Nessun gap né slippage (l'uscita a stop/obiettivo è al livello dichiarato); ordine dei tocchi dentro una candela sconosciuto (campo `ambiguous`, la policy è una scelta dell'utente); costo uguale per ogni barriera; manca il **produttore dei candidati**; nessun dato reale usato (import dei 534 trade legacy ancora bloccato: F0).

## Prossimo
**P6 — walk-forward** (`backend/v3/learning/walkforward.py`, a Grok): scegliere le celle positive solo con il passato e misurarle sul periodo dopo, riportando il decadimento. È la risposta ai confronti multipli di `cell_stats`. Prompt nel Project: `claude/prompt-grok-p6-walkforward-2026-11-04.md`. Avanzamento: `claude/f7-avanzamento.md`.

## Decisioni per l'utente (non bloccano il lavoro offline)
Policy per i tocchi ambigui stop/target nella stessa candela (`stop_first` prudente o `target_first`; per ora argomento obbligatorio); simulazione della liquidazione nel PAPER; soglie statistiche dei moduli F7; certificazione backup F0 e importazione dei trade legacy (OK utente e accesso VPS).

⛔ Nessun merge/deploy · `DESK_MODE=paper` · Hawk/Bull non toccati · cervello intatto · nessuna modifica a strategia, soglie, limiti di rischio o prompt.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_012yPu2eVVWT2jkKwTyuh3So
