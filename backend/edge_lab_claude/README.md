# Laboratorio Edge — 29/10/2026

**Ramo isolato**: `work/edge-lab-claude-20261029`  
**Mai unire a** `rule-pool` senza OK esplicito dell'utente.

## Scopo

Testa tre ipotesi su dove potrebbe esistere un vantaggio reale nel sistema di trading:

| Blocco | Ipotesi | Variabili |
|--------|---------|-----------|
| A | Costi ridotti (ordini maker ≈ 4 bp/lato) → sistema profittevole? | `cost_mult` 1.0 / 0.67 / 0.5 / 0.0 |
| B | Cap posizioni stesso lato → meno perdite concentrate? | `max_same_side` None / 5 / 3 / 1 |
| C | Strategia breakout 4h su BTC+ETH → vantaggio lordo? | BTC+ETH, ATR SL/TP |

Pre-registrazione completa in `PREREGISTRAZIONE.md`.

## File

```
backend/edge_lab_claude/
  PREREGISTRAZIONE.md  ← criteri scritti PRIMA dei risultati
  README.md
  edge_run.py          ← orchestratore (Blocchi A, B, C)
  edge_strategies.py   ← Blocco C: trend 4h
  tests/test_edge.py   ← test unitari funzioni matematiche
  results/             ← creato dal workflow GitHub Actions
```

## Esecuzione locale

```bash
# Test unitari (nessuna dipendenza esterna, solo numpy)
cd backend/edge_lab_claude
python -m unittest -v tests.test_edge

# Prova su dati sintetici (30 giorni, rapido)
python edge_run.py --synthetic --days 30 --out /tmp/edge-synth

# Laboratorio completo (540 giorni, candele reali Bitget)
python edge_run.py --days 540 --cache /tmp/edge-cache --out results
```

## Garanzie di sicurezza

- Nessun bot toccato, nessun deploy, nessun file di produzione modificato
- Solo endpoint pubblici Bitget (candele, sola lettura)
- `DESK_MODE` non viene mai letto né modificato
- Il ramo non viene mai unito a `rule-pool` senza OK esplicito
- Candele condivise dalla cache del laboratorio P1 (`long-lab-candles-20261029-540-v1`)
