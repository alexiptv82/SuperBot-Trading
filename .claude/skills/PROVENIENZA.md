# Provenienza delle skill

Fonte: https://github.com/agiprolabs/claude-trading-skills, commit `981e1d736cdc02bdc1c55c74ec9224e956414706` (licenza MIT, testo in `LICENSE-claude-trading-skills.md`).
Copiate il 20/11/2026 solo le 10 skill richieste, con `references/` e `scripts/`. Nessuno script è stato eseguito e nessuna dipendenza installata.

| Skill | Note di applicabilità a SuperBot (futures USDT-M Bitget) |
|---|---|
| risk-management | Metodologia generale; i limiti reali del progetto restano quelli di `backend/v3/risk.py` e delle decisioni del proprietario |
| position-sizing | Metodologia generale; margine e leva dei futures vanno verificati caso per caso |
| exit-strategies | Metodologia generale |
| trade-journal | Metodologia generale; una chiusura manuale è un intervento dell'operatore, non una strategia validata |
| regime-detection | `detect_regime.py` in modalità live usa Birdeye (Solana): **non usare**; `--demo` e `regime_backtest.py` sono locali |
| slippage-modeling | **Matematica per pool AMM/DEX**, non per l'order book Bitget; `execution_cost.py` e `slippage_curve.py` chiamano Jupiter (Solana). Riutilizzare solo l'impostazione del calcolo dei costi |
| portfolio-analytics | Metodologia generale (richiede pandas/numpy, quantstats opzionale) |
| walk-forward-validation | Metodologia generale; le soglie sui dati restano quelle del progetto (Issue #113) |
| signal-classification | Metodologia generale; nessun addestramento o promozione di modelli senza decisione del proprietario |
| strategy-framework | Metodologia generale |

## Modifiche rispetto agli originali
Solo la riga `description:` del frontmatter di ogni `SKILL.md`: aggiunta la frase originale + una clausola "Use when…" con parole chiave in inglese e in italiano e l'avviso di applicabilità. Nessun altro file è stato modificato.

## Riferimenti a skill NON installate
I testi citano `liquidity-analysis`, `pandas-ta`, `feature-engineering`, `volatility-modeling`, `kelly-criterion`, `trading-visualization` e altre: non fanno parte di questa installazione. Se servono vanno aggiunte con una nuova richiesta.

## Uso
Le skill sono **materiale metodologico**, non una prova della correttezza di alcun risultato. Gli script richiedono librerie (pandas, numpy, scipy, scikit-learn, quantstats) che non sono installate di default: non installarle senza necessità.
