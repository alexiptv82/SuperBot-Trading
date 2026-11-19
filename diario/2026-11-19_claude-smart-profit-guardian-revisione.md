# 19/11/2026 — Claude: revisione indipendente Smart Profit Guardian

**Branch:** `claude/brain-unico-profit-guardian-20261119` @ `cec2b872e3f546b3e03a2323d29c7b855c5f3237` (base `main` `a1e9722`), 2 file nuovi:
- `docs/v3/BRAIN-UNICO-SMART-PROFIT-GUARDIAN-PROPOSTA-20261119.md` (critica, architettura, politiche B/D/V, macchina a stati e gate, anti-reingresso, reset, piano E0–E5, ipotesi da approvare)
- `ops/brain-unico/guardian/sim_policies.py` (simulazione SINTETICA stdlib, nessun dato reale)

Workflow verificati: tutti filtrati per path/branch, nessuno corrisponde. Nota: un primo push (commit fallito per identita' git) ha creato il branch su `a1e9722` = main, poi fast-forward a `cec2b87`; nessun force.

## Conclusioni principali (da rivedere)
1. Nessuna regola di arresto aumenta il valore atteso con trade indipendenti; il Guardian rende solo se l'EV dopo un guadagno / ai reingressi e' peggiore → **E0: misurarlo sulle copie certificate prima di implementare**.
2. I profit lock non migliorano il p5 di sessione; lo migliora solo il limite di perdita di sessione (sintetico: −429 → −257). Il rischio 4,29 %/trade e il blocco giornaliero al 50 % ereditati dall'Arena sono il rischio principale.
3. A rischio fisso (85,71) con margine 400: 50× ⇒ stop ≤ 0,25 %, costi ≈ 42 % di R, pareggio al 57,5 % con TP 2× (ipotesi costi 0,06 %+0,03 %/lato, da verificare). Leva = output, minima ammissibile.
4. Raccomandata come primo test la politica D (floor mobile sul picco MTM, budget di rischio unico) con limite di sessione; B (400/500) resta braccio di confronto; nessuna eccezione nella v1.
5. Sessione: PnL = equity_MTM(t) − equity_MTM(reset); 08:00 Europe/Rome per ragione di sicurezza (blocco notturno), redditivita' non dimostrata.

## Non fatto
Nessuna implementazione nel runtime, nessun dato reale, nessun root/snapshot/stop/merge/deploy/API. Restano aperti i **due fix residui PR #118** chiesti da ChatGPT (link con simboli esplicitamente diversi a parita' di cycle_id; attestazione non auto-dichiarabile senza ancora a manifest/audit/checkpoint): non toccati in questo giro.
