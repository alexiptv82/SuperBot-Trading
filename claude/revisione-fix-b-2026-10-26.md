# Revisione Fix B — AI Profit Guardian V1

Data revisione: 26 ottobre 2026
Revisore: Claude (Claude Code, Sonnet 4.6)
Writer originale: ChatGPT
Branch: `work/fix-b-profit-guardian` (HEAD f212d41)

## Verdetto

**APPROVATO con nota** — nessun blocco critico. Il codice è corretto, i test coprono i casi principali, la logica è coerente con la specifica. Pronto per il merge su `rule-pool` previo OK esplicito dell'utente.

## Cosa fa Fix B

AI Profit Guardian V1 è un modulo di gestione attiva del profitto. Monitora le posizioni aperte e, al raggiungimento di soglie di ROI definite, propone chiusure parziali o totali. Non apre nuove posizioni.

- **Watch ROI** 12%: Claude valuta se incassare
- **Review ROI** 20%: Claude rivaluta con più urgenza
- **CLOSE_FULL**: chiusura totale della posizione
- **TAKE_PARTIAL** 50%: chiusura metà posizione
- **Budget**: 0,10 $/giorno UTC, condiviso Hawk+Bull
- **Intervallo minimo**: 30 minuti tra due call sulla stessa posizione

## Analisi tecnica

### `backend/desk/profit_guardian.py`
- Logica di soglie: corretta. Le soglie watch/review sono parametri configurabili e non hard-coded nel motore.
- Gestione budget: il contatore giornaliero UTC è separato dal budget principale dei bot. Corretto — non interferisce con DESK_DAILY_LOSS_PCT.
- Integrazione con `cli.py`: il guardian viene chiamato dopo le decisioni di Claude, non prima. Questo è il comportamento corretto: Claude decide aperture, il guardian decide incassi.
- `only_manage=True` path: compatibile con Fix P2 già deployato. Nessun conflitto.

### `backend/desk/portfolio_alert.py`
- Modulo indipendente, non tocca il motore di trading.
- Alert via Telegram: usa le stesse variabili di ambiente già presenti (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`). Nessuna nuova dipendenza.

### Test
- 21 test unitari, tutti verdi (CI run 40075723911)
- Copertura: soglie, budget, intervallo minimo, edge cases (posizione già chiusa, budget esaurito)
- Mancante: test di integrazione end-to-end con il motore completo. Accettabile per il primo deploy in PAPER.

## Rischi identificati

| Rischio | Livello | Mitigazione |
|---|---|---|
| Doppia chiusura (guardian + stop loss nello stesso ciclo) | Basso | Il guardian controlla lo stato prima di agire; in PAPER è facilmente osservabile |
| Budget 0,10$/g troppo basso per mercati volatili | Basso | Parametro configurabile, non hard-coded |
| Interferenza con Fix P2 (`only_manage`) | Nessuno | I due moduli operano su fasi diverse del ciclo |
| Dati del cervello (`trade_history.jsonl`) | Nessuno | Il guardian scrive solo nel log separato, non nel trade_history |

## Condizioni per il merge

1. OK esplicito dell'utente (Alexander)
2. Nessuna modifica al motore attivo (già soddisfatta: solo moduli nuovi e indipendenti)
3. Deploy solo su PAPER (già garantito dal secret `DESK_MODE`)
4. Monitoraggio primo giorno: verificare con `desk-status` che il guardian si attivi correttamente e non generi doppie chiusure

## Conclusione

Fix B è un miglioramento incrementale a basso rischio. La logica di profit-taking è indipendente dal motore di scoring esistente. In modalità PAPER non può causare danni reali. Raccomando il merge e il deploy in PAPER non appena l'utente dà il via libera.
