# Brain Scalp dual PAPER — Gruppo 1 completato offline (ChatGPT)
Data: 29 ottobre 2026. Prompt Claude: `claude/prompt-chatgpt-brain-scalp-completo-2026-10-29.md` sul ramo `diario`.

## Ambito e autorizzazione
L'utente aveva chiesto di partire dal Gruppo 1 dopo pubblicazione del prompt. Modificato solo il motore Brain Scalp, branch **`work/brain-scalp-dual-20261028`**, partito da `d96d171`. Niente modifica a `backend/director/brain_free/**`, `backend/desk/**`, app `main` / `work/brain-scalp-dual-app-20261028`, `rule-pool`, dati VPS, posizioni/portafogli o credenziali. Nessun merge o deploy. Solo test unitari e runner GitHub Actions offline.

## Correzioni effettuate
1. **B3a — quota invalida e valutazione:** localmente in `brain_scalp/engine.py` `_safe_equity` esclude prezzi assenti/non finiti/non positivi, marca l'equity incompleta, produce `equity_unavailable` e blocca nuove entrate; `last_prices` non memorizza NaN. Le protezioni su barre chiuse e quote valide si eseguono **prima** della valutazione. Commit `3eb9d03`. Nessuna modifica al modulo condiviso Brain Free.
2. **B3b — clock retrocesso:** il tick usa un tempo monotono non inferiore al `last_ms`, registra `clock_adjusted` e continua a eseguire le protezioni. Ritorno superiore a 500ms impedisce nuove aperture in quel tick. Commit `225f16f`.
3. **B3c — isolamento dei due portafogli:** `BrainPair.tick` gestisce ogni wallet dentro un proprio try/except; fallimento Hawk non interrompe Bull, né viceversa; log di tipo errore e evento persistente `wallet_tick_error` best effort, senza messaggi potenzialmente sensibili nel DB. Commit `29bf7a6`.
4. **I4 — freshness distinta:** `brain_scalp/config.py` impone `ENTRY_PRICE_AGE_MS=3000`, `PROTECT_PRICE_AGE_MS=10000` **solo** per Brain Scalp; `plans.triggered` usa 3s; `engine.submit` usa 3s e motivo `quote_too_stale_for_entry`; `engine.tick` usa `entry_cfg` per fill e `protect_cfg` per protezione. Evento `entry_fill` registra trigger, prezzo osservato, fill reale simulato, scostamento e età quota. Commit `ab19b536`, `f9dc536`, `f1be807`.
5. **Test:** nuovo `backend/tests/test_brain_scalp_group1.py` con 9 casi mirati: `None`, NaN, clock indietro 1ms e 1s, crash Hawk e doppio crash, quote 5s rigettate e 2s accettate, fill event. Aggiornato test preesistente per evento `entry_fill`, e workflow per includere suite Gruppo1. Commit `031ad50`, `bb0919e`, `d440ead`.

## CI e controlli indipendenti
**GitHub Actions run 40836245846 = SUCCESS su Python 3.10 e 3.11**. **28/28 test per interprete**, 56 esecuzioni totali; il workflow verifica che `backend/desk`, `backend/director/brain_free`, deploy originale siano immutati rispetto alla base `e0021488`. Esito precedente intermedio `f1be807` falliva perché il vecchio test assumeva che l'ultimo evento fosse `open`; aggiornato per controllare sia `open` sia `entry_fill` e final run verde. Gli errori intenzionalmente iniettati nel test B3c producono log di eccezione, ma **il test PASS**.

## Limiti e controlli per la fase successiva
- Il motore rimane offline; non è un sistema operativo per trading, non ha feed Bitget / chiamate LLM in produzione né backtest reddituale certificato.
- La regola di freschezza di 3 secondi esige un flusso quote affidabile e veloce nella futura integrazione; **non** riallargare a 30 secondi senza decisione utente.
- `_safe_equity` non attribuisce artificialmente P&L zero alle posizioni senza prezzo: restituisce `complete=False`, quindi nessuna nuova apertura quando manca la marcatura. Le protezioni che dipendono da quote invalide non possono inventare un fill.
- B3c salva in modo *best effort* l'evento di errore: un DB guasto potrebbe impedire il log persistente, ma non il tick dell'altro wallet.
- **Gruppo 2 (I2/I3/B2) non ancora iniziato**, in attesa di OK esplicito dell'utente dopo questo report. Gruppo 6 opzione A/B/C resta una decisione successiva. Il report di Claude sui classici rimane indipendente.

## Riferimenti
- Prompt: https://github.com/alexiptv82/SuperBot-Trading/blob/diario/claude/prompt-chatgpt-brain-scalp-completo-2026-10-29.md
- CI: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/40836245846
- Branch: https://github.com/alexiptv82/SuperBot-Trading/tree/work/brain-scalp-dual-20261028

AI: ChatGPT (chat normale)

## Nota critica sulla break-even math del documento Claude (NON cambia i parametri)
La tabella del prompt Claude indica BE WR 38,7% / 28,6% / 20,0% con target 0,32%/0,48%/0,80%, stop 0,16% e costi roundtrip 0,16%. **Questi valori non sono coerenti con la definizione di target/stop come escursione lorda di prezzo**. Per un esito binario ideale senza funding, con stop e target su prezzi lordi e costo roundtrip fisso `c`, la condizione di profitto è:
`p * (target - c) - (1-p) * (stop + c) = 0` → `p_BE=(stop+c)/(target+stop)`.
Se `c=0,16%`, i valori diventano rispettivamente **66,67%**, **50,00%**, **33,33%**. Con fee/slippage dipendenti dal prezzo di uscita i risultati cambiano leggermente. Se Claude intendeva distanze *già nette dei costi*, occorre esplicitarlo e ricavare la formula corrispondente. **Non utilizzare i tassi BE del prompt per scegliere parametri o dichiarare edge prima di questa riconciliazione**. Il Gruppo 1 non modifica la strategia, quindi non richiede correzione del codice su questa base.

