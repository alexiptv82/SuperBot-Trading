# Edge Lab — 29/10/2026 (Claude)

**Ramo:** `work/edge-lab-claude-20261029`  
**Nessun bot toccato. Nessun deploy. Solo candele pubbliche Bitget.**

## Cosa è stato fatto

Laboratorio offline pre-registrato su 540 giorni di candele reali Bitget 15m (fine 29/10/2026).
Tre ipotesi testate in modo indipendente; criteri scritti prima di vedere i risultati (`PREREGISTRAZIONE.md`).

## Risultati

**Blocco A — ordini maker:**  
Ridurre i costi da 6 bp/lato a 4 bp/lato taglia le perdite del 28% (da −21.786$ a −15.855$) ma non basta.
Anche con costi zero il sistema perde −4.092$ (R=−0,004). **Il vantaggio lordo non esiste.**

**Blocco B — cap posizioni stesso lato:**  
Il cap blocca il 69–95% delle aperture senza migliorare il R unitario (rimane ≈ −0,160).
Il drawdown scende solo perché si fa meno trading, non perché migliori la qualità. **Nessun beneficio selettivo.**

**Blocco C — breakout 4h BTC+ETH:**  
251 trade in 540 giorni. Anche a zero costi: R=−0,003, PF=0,954. Il segnale non funziona.
Il segnale invertito perde ancora di più (R=−0,169): non c'è direzione sfruttabile. **Nessuna edge lorda.**

## Conclusione

base13 non ha un vantaggio lordo sufficiente. I costi aggravano una situazione già negativa, ma non la causano.
Servono decisioni dell'utente prima di procedere con nuove ipotesi.

## Gate superate / non superate

| Blocco | Gate | Esito |
|--------|------|-------|
| A | G1 (ΔR≥0) | ✅ tutte e 3 |
| A | GA1 (netto>0) | ❌ nessuna |
| A | GA2 (R>0) | ❌ nessuna |
| B | G1 (ΔR≥0) | ❌ cap_3 e cap_1 |
| B | GB1 (dd<90%) | ✅ tutte e 3 |
| B | GB3 (blk≤50%) | ❌ tutte e 3 (69–95%) |
| C | GC1 (R>0) | ❌ nessuna |
| C | GC2 (PF>1) | ❌ nessuna |
| C | GC3 (Roos>0) | ❌ nessuna |

## Commit rilevanti

- `105848f` — codice iniziale e pre-registrazione
- `87431d5` — fix API (labrun, labfeat, labdata) + long_lab_claude incluso
- `da4d68e` — risultati committati da GitHub Actions
- `c919ed2` — rapporto finale `RAPPORTO.md`

Rapporto completo: `backend/edge_lab_claude/RAPPORTO.md`

AI: claude
