# STATO CORRENTE SuperBot-Trading — 26 ottobre 2026
Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore, codice **63641f70** (deploy 26/10/2026 — trigger 6f73e800, DEPLOY OK).
- Fix B AI Profit Guardian V1 attivo: `profit_guardian.py` + `portfolio_alert.py` in produzione.
- Capital Management V1 integrato ma con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente.
- Vincolo immutabile: nessun reset di trade_history, learning_log, lessons.md, errors.md.
- rule-pool HEAD: `6f73e800` (trigger deploy Fix B). Non toccare Strasburgo/HiTV.

## Fix P1 e P2 — DEPLOYATI (25/10/2026, inclusi in 63641f70)
- **P1 sbias LONG** (commit 635b964, merge 4ec05f4): `backend/desk/signals.py` — rimbalzo RSI 1h (RSI<35 + mom>0.003 → +10 punti LONG).
- **P2 smart fallback** (commit 5e1ee2a + 017dd07): `backend/desk/cli.py` + `brain.py` — flag `_claude_responded`; 0 aperture → only_manage; unavailable → fallback completo.

## Fix B AI PROFIT GUARDIAN V1 — DEPLOYATO (26/10/2026)
- Branch `work/fix-b-profit-guardian` mergiato su `rule-pool` il 26/10 (PR #5, merge 63641f70).
- Deploy: trigger `6f73e800`, APPROVED_SHA=`63641f7059a977368f8bb8aecc517f7a7c74cbce`, Actions SUCCESS.
- Moduli attivi: `backend/desk/profit_guardian.py`, `backend/desk/portfolio_alert.py`.
- Parametri: watch ROI netto 12% → TAKE_PARTIAL 50%; review 20% → CLOSE_FULL; budget 0,10$/g UTC condiviso Hawk+Bull; intervallo minimo 30 min per posizione.
- ChatGPT writer, Claude revisore (verdetto: APPROVATO). Specifica: FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md.

## Storico deploy
| Data | Versione | Contenuto |
|---|---|---|
| 25/10/2026 | 886b30f | Fix P1 (sbias LONG) + Fix P2 (smart Claude fallback) |
| 26/10/2026 | **63641f70** | Fix B (AI Profit Guardian V1) |

## Altre informazioni operative
- DeepSeek shadow indipendente: applied=false.
- Capital Management V1: DESK_CAPITAL_V1=off, moduli presenti ma non attivi.
- Vincoli immutabili: nessuna istanza LIVE, nessun doppio processo, preservare cervello bot.

## Claude — collaboratore permanente (25/10)
- Claude (Claude Code, Sonnet 4.6) attivo come collaboratore permanente.
- Deploy P1+P2: 25/10 OK utente — Deploy Fix B: 26/10 OK utente, SUCCESS.
- Dettagli sessioni: diario/2026-10-25_claude.md.

## Documenti di riferimento AI
- `claude/protocollo-collaborazione-ai.md` — regole collaborazione ChatGPT+Claude, onboarding
- `claude/stato-roadmap-completa.md` — roadmap (da aggiornare: Fix B ora deployato)
- `claude/revisione-fix-b-2026-10-26.md` — verdetto revisione Fix B

## Riferimenti
- LEGGIMI.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md.
- FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md, diario/2026-10-24_chatgpt.md, diario/2026-10-25_claude.md.
- ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md e cronologia Git del precedente STATO.
