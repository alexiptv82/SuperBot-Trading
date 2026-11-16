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
