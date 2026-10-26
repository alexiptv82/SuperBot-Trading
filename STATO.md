# STATO CORRENTE SuperBot-Trading — 26 ottobre 2026
Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore. Deploy Fix B avviato il 26/10/2026 (trigger 6f73e800).
- APPROVED_SHA deploy Fix B: `63641f7059a977368f8bb8aecc517f7a7c74cbce` (merge commit Fix B su rule-pool).
- Deploy P1+P2 precedente (25/10): Actions 40234289443, versione 886b30f, DEPLOY OK.
- Capital Management V1 integrato ma con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente.
- Vincolo immutabile: nessun reset di trade_history, learning_log, lessons.md, errors.md.
- rule-pool è un ramo operativo. Non toccare Strasburgo/HiTV.

## Fix P1 e P2 — DEPLOYATI (25/10/2026, versione 886b30f)
- **P1 sbias LONG** (commit 635b964, merge 4ec05f4): `backend/desk/signals.py` — rimbalzo RSI 1h.
- **P2 smart fallback** (commit 5e1ee2a + 017dd07): `backend/desk/cli.py` + `brain.py` — flag `_claude_responded`.

## Fix B AI PROFIT GUARDIAN V1 — DEPLOY IN CORSO (26/10/2026)
- Branch `work/fix-b-profit-guardian` mergiato su `rule-pool` il 26/10 (PR #5, merge 63641f70).
- Deploy avviato: trigger `6f73e800`, APPROVED_SHA=`63641f70`, Actions in esecuzione.
- Baseline workflow aggiornato da 297b126 a 886b30f (commit 280f9c58) prima del trigger.
- Moduli: `backend/desk/profit_guardian.py`, `backend/desk/portfolio_alert.py`.
- Parametri: watch 12% TAKE_PARTIAL, review 20% CLOSE_FULL, budget 0,10$/g UTC, intervallo 30 min.
- Da aggiornare quando Actions completa: versione attiva e stato deploy.

## Altre informazioni operative
- DeepSeek shadow indipendente: applied=false.
- Capital Management V1: DESK_CAPITAL_V1=off, non attivo.
- Vincoli immutabili: nessuna istanza LIVE, nessun doppio processo, preservare cervello bot.

## Claude — collaboratore permanente (25/10)
- Claude (Claude Code, Sonnet 4.6) attivo come collaboratore permanente.
- Deploy P1+P2: 25/10 OK utente; Deploy Fix B: 26/10 OK utente, trigger avviato.
- Dettagli sessioni: diario/2026-10-25_claude.md.

## Documenti di riferimento AI
- `claude/protocollo-collaborazione-ai.md` — regole collaborazione ChatGPT+Claude
- `claude/stato-roadmap-completa.md` — roadmap al 26/10 (da aggiornare post-deploy Fix B)
- `claude/revisione-fix-b-2026-10-26.md` — verdetto revisione Fix B

## Riferimenti
- LEGGIMI.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md.
- FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md, diario/2026-10-24_chatgpt.md, diario/2026-10-25_claude.md.
- ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md e cronologia Git del precedente STATO.
