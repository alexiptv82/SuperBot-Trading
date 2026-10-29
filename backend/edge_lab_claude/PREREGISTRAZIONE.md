# Pre-registrazione — Laboratorio Edge (Claude) — 29/10/2026

**Scritto PRIMA di vedere qualsiasi risultato. Ogni modifica dopo la prima esecuzione deve essere dichiarata come errata/aggiunta.**

---

## Domande del laboratorio

Questo laboratorio testa tre ipotesi indipendenti su dove potrebbe esistere un vantaggio reale nel sistema attuale.

### Blocco A — Impatto dei costi (ordini maker vs taker)

**Domanda**: con commissioni ridotte (ordini maker ≈ 4 bp/lato invece di 6 bp taker), il sistema diventa redditizio?

- Varianti: `cost_mult` = 1.0 (base), 0.67 (≈4 bp/lato), 0.5 (3 bp), 0.0 (senza costi)
- Il sistema base ha R ≈ −0.004 lordo (i costi decidono il segno)
- Criterio minimo: netto > 0 con cost_mult ≤ 0.67

### Blocco B — Concentrazione posizioni (cap stesso lato)

**Domanda**: un limite al numero massimo di posizioni aperte contemporaneamente sullo stesso lato riduce le perdite da movimenti avversi grandi senza distruggere i ritorni?

- Motivazione: oggi (29/10) tutti short aperti; BTC è salito da 79k a 81k → perdita concentrata
- Varianti: `max_same_side` = None (base), 5, 3, 1
- Metrica primaria: riduzione del drawdown massimo vs base; metrica secondaria: Δ netto vs base

### Blocco C — Strategia trend 4h (solo BTC + ETH)

**Domanda**: una strategia di breakout su barre 4h (BTC e ETH) ha un vantaggio lordo? I movimenti 4h sono abbastanza grandi da giustificare i costi?

- Solo BTC e ETH (i simboli con maggiore range)
- Segnale: breakout del massimo/minimo delle ultime 20 barre 4h; SL = 2×ATR(14)/close; TP = 4×ATR(14)/close
- Variante: cost_mult = 0.0 (verifica vantaggio lordo), 1.0 (verifica netto), 0.67
- Criterio minimo: R medio > 0 con cost_mult = 0.0 (deve esistere un vantaggio lordo prima dei costi)

---

## Criteri di successo (scritti prima dei risultati)

### Criteri comuni a tutti i blocchi

**G1** — Il Δ netto vs base è ≥ 0 (la variante non peggiora)
**G2** — Il numero di trade è ≥ 50% di quello base (abbastanza dati)
**G3** — Bootstrap (blocchi da 7 giorni, n=5000): P(Δ < 0) ≤ 30%

### Blocco A — Criteri specifici

**GA1** — Con cost_mult = 0.67 (≈ ordini maker): netto > 0 nel periodo completo (540 giorni)
**GA2** — Con cost_mult = 0.67: R_medio > 0 (ogni trade in media guadagna al netto)

### Blocco B — Criteri specifici

**GB1** — Il drawdown massimo si riduce di almeno il 10% vs base
**GB2** — Il netto non peggiora di più del 20% vs base (Δ ≥ −0.20 × |netto_base|)
**GB3** — I trade bloccati (per il cap) sono < 30% del totale (il filtro non è troppo aggressivo)

### Blocco C — Criteri specifici

**GC1** — R medio > 0 con cost_mult = 0.0 (vantaggio lordo confermato)
**GC2** — Con cost_mult = 0.67: Profitto fattore > 1.0
**GC3** — Nell'ultimo terzo del periodo (giorni 361–540, out-of-sample): R medio > 0 con cost_mult = 0.0

---

## Placebo

### Blocco B — 8 placebo con cap casuali

Cap random generati con seed fisso (1..8): `np.random.RandomState(seed).randint(2, 8)`. Se nessuna variante reale batte la mediana dei placebo sullo stesso Δ, il risultato è spurio.

### Blocco C — 1 placebo: segnale invertito

Entrare SHORT quando il segnale è LONG e viceversa. Se il placebo invertito ha R simile al segnale reale, la strategia non ha potere predittivo.

---

## Suddivisione temporale

- **In-sample** (training): giorni 1–360 (circa maggio 2025 – settembre 2026)
- **Out-of-sample** (validazione): giorni 361–540 (circa ottobre 2026)
- La validazione fuori campione si usa SOLO dopo che la selezione della variante è avvenuta sull'in-sample

---

## Cosa NON si tocca

- Nessun file di produzione, nessun bot, nessun deploy
- `desk.brain`, `desk.engine`, `desk.signals` usati in sola lettura
- Il ramo `work/edge-lab-claude-20261029` non viene mai unito a `rule-pool` senza OK esplicito dell'utente
- Il sistema rimane in paper trading (`DESK_MODE=paper`)
