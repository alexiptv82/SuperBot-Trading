# STATO CORRENTE SuperBot-Trading — 26 ottobre 2026
Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore, codice **63641f70** (deploy 26/10/2026 — trigger 6f73e800, DEPLOY OK).
- Fix B AI Profit Guardian V1 attivo: `profit_guardian.py` + `portfolio_alert.py` in produzione.
- Capital Management V1 integrato ma con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente.
- Vincolo immutabile: nessun reset di trade_history, learning_log, lessons.md, errors.md.
- rule-pool HEAD: `dbddc240` (AI Write unificato + chatgpt/README.md).

## Fix P1 e P2 — DEPLOYATI (25/10/2026, inclusi in 63641f70)
- **P1 sbias LONG**: `backend/desk/signals.py` — rimbalzo RSI 1h.
- **P2 smart fallback**: `backend/desk/cli.py` + `brain.py` — flag `_claude_responded`.

## Fix B AI PROFIT GUARDIAN V1 — DEPLOYATO (26/10/2026)
- Deploy: trigger `6f73e800`, APPROVED_SHA=`63641f7059a977368f8bb8aecc517f7a7c74cbce`, Actions SUCCESS.
- Moduli attivi: `backend/desk/profit_guardian.py`, `backend/desk/portfolio_alert.py`.

## AI Write unificato — 26/10/2026
- `claude-write.yml` rinominato "AI Write": supporta `claude/claude-write.trigger` e `chatgpt/chatgpt-write.trigger`.
- Autore git automatico: Claude = noreply@anthropic.com, ChatGPT = noreply@openai.com.
- `chatgpt/README.md` creato: guida onboarding ChatGPT.
- MANUALE-OPERATIVO.md aggiornato con sezione 3 (AI Write) e sezione 8 (passaggio di turno).

## Director V1 — IN CORSO (26/10/2026)
- Contratti v1 + v1.1: `work/director-chatgpt` (ChatGPT) — pronti.
- AI Shadow (pilot DeepSeek): `work/director-claude` (Claude) — pronti.
- **Arbitro V1 scritto**: `backend/director/arbitro.py` su `work/director-claude` (commit `ea60acc`).
  - Riceve `DirectorAdvice` (v1.1) + `PortfolioSnapshot` + candidati → valida legality → chiama `size_position`.
  - 10 test in `backend/tests/test_director_arbitro.py` (commit `f06e8e3`).
- **Prossimo passo**: creare `work/director-v1-unified` con:
  - `contracts/` (da director-chatgpt) + `ai_shadow/` (da director-claude) + `arbitro.py`
  - Verificare che i test del contratto v1_1 + i test dell'arbitro girino tutti insieme
  - Decidere con utente: il Pilot usa l'Arbitro o l'Arbitro è solo per il Director esterno?

## Storico deploy
| Data | Versione | Contenuto |
|---|---|---|
| 25/10/2026 | 886b30f | Fix P1 (sbias LONG) + Fix P2 (smart Claude fallback) |
| 26/10/2026 | **63641f70** | Fix B (AI Profit Guardian V1) |

## Task aperti (in ordine di priorità)
1. **Director V1 — unificazione**: creare `work/director-v1-unified`, integrare contratti+shadow+arbitro, run test completo
2. **Osservazione Fix B**: finestra 24-48h in paper (sola lettura, desk-status)
3. **Punto 4** — DeepSeek shadow design (`work/deepseek-bot-shadow-design`)
4. **Punto 5** — Capital Dashboard V1 (`work/capital-dashboard-v1`)
5. **Punto 6** — Profit audit read-only (`work/profit-audit-readonly`) — pronto, serve review + OK utente
6. **Punto 7** — A/B proposals (`work/profit-correctness-proposals`)
7. **Punto 8** — Capital Management V1 activation (decisione utente)

## Claude — collaboratore permanente (25/10)
- Claude (Claude Code, Sonnet 4.6) attivo come collaboratore permanente.

## Documenti di riferimento AI
- `claude/protocollo-collaborazione-ai.md` — regole collaborazione ChatGPT+Claude, onboarding
- `claude/revisione-fix-b-2026-10-26.md` — verdetto revisione Fix B
- MANUALE-OPERATIVO.md (sezione 8: passaggio di turno tra AI)

## Riferimenti
- LEGGIMI.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md.

## Market Regime + Episode Memory — PRONTO PER REVIEW CLAUDE
- Branch `work/market-regime-episode-memory`, commit `79add5c0b4d4433342fddec1e83c48abf0ef19f4`; base `dbddc2403bfd5fd9c7444b97185ae60071f81ee5`.
- Due moduli isolati + sole aggiunte brain.py in `docs/brain_regime_additions.py`; 22/22 test locali PASS, sintassi Python 3.10 verificata. Nessuna CI/replay storico.
- Review: `docs/market-regime-review.md`; diario commit `d184085a867f1a53d47242803228df953133438d`.
- Implementazione dalla specifica: sorgente completo DeepSeek non fornito. Soglie proposte documentate; non certificato pronto alla produzione.
- Prossimo: review Claude, cablaggio cli.py per candele e contesto, copertura aperture AI/split/DCA, replay PAPER. Patch attuale protegge ingressi a regole quando collegata; gestione posizioni preservata.
- Nessun merge/deploy/riavvio o modifica dati. Proprietà sviluppo ceduta a review Claude.
