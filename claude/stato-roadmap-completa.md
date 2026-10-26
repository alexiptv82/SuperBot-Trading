# Stato e roadmap completa — SuperBot-Trading

Ultimo aggiornamento: 26 ottobre 2026

## Stato runtime attuale

| Componente | Stato |
|---|---|
| Hawk | PAPER, versione `886b30f`, Up 8h+ (healthy) |
| Bull | PAPER, versione `886b30f`, Up 8h+ (healthy) |
| DESK_MODE | `paper` (secret) |
| DESK_CAPITAL_V1 | `off` |
| VPS Singapore | 51.79.205.82, tutti i container operativi |

## Cosa è già in produzione

### Capital Management V1
- Moduli installati, feature gate `DESK_CAPITAL_V1=off`
- Non attivo finché l'utente non abilita esplicitamente
- Specifica: `CAPITAL-MANAGEMENT-V1-SPECIFICA.md` (branch diario)

### Fix P1 — sbias LONG (deployato 25/10/2026)
- File: `backend/desk/signals.py`
- Ridotto peso trend HTF; aggiunto segnale rimbalzo RSI 1h < 35 + mom > 0.003 → +10 punti LONG
- Commit: 635b964 (merge 4ec05f4), deployato con `886b30f`

### Fix P2 — smart Claude fallback (deployato 25/10/2026)
- File: `backend/desk/cli.py`, `backend/desk/brain.py`
- Flag `_claude_responded`: distingue "Claude sceglie 0 aperture" da "Claude non disponibile"
- Se Claude risponde: regole solo `only_manage=True` (no nuove aperture)
- Se Claude non disponibile: fallback completo alle regole
- Commit: 5e1ee2a + 017dd07, deployato con `886b30f`

## In lavorazione / in attesa di OK

### Fix B — AI Profit Guardian V1
- Branch: `work/fix-b-profit-guardian`
- Writer: ChatGPT; Revisore: Claude
- Moduli: `backend/desk/profit_guardian.py`, `backend/desk/portfolio_alert.py`
- 21 test unitari: CI SUCCESS (run 40075723911)
- Parametri approvati:
  - Watch ROI netto: 12%, review: 20%
  - CLOSE_FULL; TAKE_PARTIAL 50%
  - Budget: 0,10 $/giorno UTC condiviso Hawk+Bull
  - Intervallo minimo: 30 min per posizione
- Stato: revisione Claude completata (26/10), in attesa di OK utente per merge su `rule-pool` e deploy
- Specifica vincolante: `FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md` (branch diario)
- Verdetto revisione: `claude/revisione-fix-b-2026-10-26.md`

### Workflow claude-write.yml
- Aggiunto su `rule-pool` (commit 1dd9004)
- Consente operazioni Git autonome di Claude via trigger
- Richiede secret `CLAUDE_WRITE_TOKEN` — da verificare

## Roadmap prossimi passi

| Priorità | Passo | Dipendenze |
|---|---|---|
| 1 | Verifica `CLAUDE_WRITE_TOKEN` secret | Nessuna |
| 2 | OK utente per merge Fix B su `rule-pool` | Revisione Claude consegnata |
| 3 | Deploy Fix B su VPS | OK utente al passo 2 |
| 4 | Revisione incrociata risultati P1+P2 in produzione | 1-2 settimane di dati |
| 5 | Valutazione Capital Management V1 (attivazione) | Decisione utente |

## Vincoli permanenti

- Nessuna istanza LIVE finché l'utente non autorizza
- Nessun doppio processo per portafoglio
- Cervello dei bot intoccabile
- Repository pubblico: mai saldi reali, mai chiavi
- Mai toccare HI-TV / Strasburgo
