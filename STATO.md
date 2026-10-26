# STATO CORRENTE SuperBot-Trading — 26 ottobre 2026
Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore, codice **63641f70** (deploy 26/10/2026 — trigger 6f73e800, DEPLOY OK).
- Fix B AI Profit Guardian V1 attivo: `profit_guardian.py` + `portfolio_alert.py` in produzione.
- Capital Management V1 integrato ma con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente.
- Vincolo immutabile: nessun reset di trade_history, learning_log, lessons.md, errors.md.
- rule-pool HEAD: `502107209` (AI ombra report 26/10).

## AI IN OMBRA (DeepSeek) — ATTIVO DAL 21/10/2026
- Container `superbot-ai` su VPS Singapore, **Up 5 days (healthy)**, riavvii: 0.
- Commit installato: `53111b30b633add0869c5eea031d72739f438261` (21/10/2026 08:13 Roma, OK utente).
- Modalità: **ombra pura** (`applied: False`, nessun ordine reale né virtuale verso exchange).
- Conto virtuale separato (`PaperAccount`): equity di partenza 1000 $.
- Report 26/10 ore 12:01 UTC (workflow run #5, SUCCESS):
  - **Cicli completati:** 504 (ogni 15 min, ~5 gg)
  - **Chiamate DeepSeek:** 504 ok / 0 fallite
  - **Spesa modello:** 0.0808 $/0.50 oggi | 0.5931 $/12.00 mese
  - **Equity virtuale:** 724.78 $ (partenza 1000 $, -275.22 $ = -27.5%)
  - **Trade chiusi:** 97 (+ 7 parziali) | vincenti: 30/97 (31%) | netto: -274.97 $
  - **Long:** 18 vinte / 65 totali (-203.5 $) | **Short:** 12 vinte / 32 totali (-86.3 $)
  - **Uscite:** stop loss 64, AI chiusura 26, take profit 7
  - **Proposte scartate:** rr_basso 112, stop_non_stringe 49, livelli_sbagliati 2, già_aperta 1, stop_mancante 1
  - **Posizioni aperte:** 1
  - **Lettura mercato 11:45:** "Alts bouncing on 15m but 1d/4h still bearish; most stalling at resistance. XAU grinding near 24h high, hold long. Only RUNE shows real volume breakout."
- Nota analisi: win rate 31%, bias LONG forte (65 long vs 32 short), R/R filtering attivo (112 rifiutati per R/R basso). Da monitorare se il modello impara a ridurre stop troppo larghi.

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

## Director V1 — COMPLETATO (26/10/2026)
- Branch unificato: **`work/director-v1-unified`**, commit `d2b351e0`.
- Struttura completa:
  - `backend/director/contracts/` — v1.py + v1_1.py + outcomes.py + outcomes_v1_1.py + CONVENTIONS_V1.md + CONVENTIONS_V1_1.md + fixtures/ (3 JSON)
  - `backend/director/ai_shadow/` — 13 file (DeepSeek pilot, decisions.py con size_position)
  - `backend/director/arbitro.py` — bridge DirectorAdvice → ordini eseguibili
  - `backend/tests/test_director_arbitro.py` — 10 unit test
  - `backend/tests/test_director_contracts_v1_1.py` — 8 unit test
- Tutti gli import risolvono localmente (no dipendenze cross-branch).
- Regole C1-C5 da CONVENTIONS_V1_1.md integrate; Rule C2: l'Arbitro decide la size, non l'AI.
- DESK_MODE=paper immutabile, DESK_CAPITAL_V1=off.

## Storico deploy
| Data | Versione | Contenuto |
|---|---|---|
| 25/10/2026 | 886b30f | Fix P1 (sbias LONG) + Fix P2 (smart Claude fallback) |
| 26/10/2026 | **63641f70** | Fix B (AI Profit Guardian V1) |

## Task aperti (in ordine di priorità)
1. **Osservazione Fix B**: finestra 24-48h in paper (sola lettura, desk-status)
2. **Punto 4 — AI shadow**: in osservazione, già attivo. Analisi dati disponibile (504 cicli, 5 gg). Decidere se aggiungere integrazione Arbitro dopo altro periodo di osservazione.
3. **Punto 5** — Capital Dashboard V1 (`work/capital-dashboard-v1`)
4. **Punto 6** — Profit audit read-only (`work/profit-audit-readonly`) — pronto, serve review + OK utente
5. **Punto 7** — A/B proposals (`work/profit-correctness-proposals`)
6. **Punto 8** — Capital Management V1 activation (decisione utente)
7. **Director V1 review**: run test su `work/director-v1-unified`, decidere integrazione Pilot↔Arbitro

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

## Brain Pilot V1 — PRONTO PER REVIEW CLAUDE
- Branch `work/brain-pilot-v1`, base `502107209f9e42d38e4421ac70df188c823dc315`, codice `a5d8b79783982b5642210ffe026c0a9150176d0f`.
- PR draft #6: https://github.com/alexiptv82/SuperBot-Trading/pull/6. Handoff: `docs/brain-pilot-v1-review.md` sul branch.
- Sei comportamenti, prompt strutturale macro/fib/BTC, nuovo conto PAPER1000 isolato, rischio allo stop cap1% proporzionale, persistenza SQLite+outbox JSONL.
- 37/37 test locali PASS; Actions40328264317 SUCCESS su Python3.10/3.11. Installer con Docker simulato; build/install/replay reali non verificati.
- Diario consegna: `7003086a69cbb901f312247c876f50087ea310ee`.
- Prossimo: Claude review PR, verifica Docker e interpretazioni del brief; deploy solo Claude Code dopo nuovo OK utente. Nessun merge/deploy o modifica del vecchio pilot/Hawk/Bull eseguiti. Proprietà ceduta a review Claude.

### Follow-up installer — pronto per nuova review Claude
- Installer ora incluso: .github/workflows/brain-pilot-install.yml + deploy/scripts/brain_pilot_install.py; trigger INERTE action=none/approved=no.
- SHA approvato, volume esclusivo brain, backup hash verificato, lock, health/heartbeat nuovo, nessuna sostituzione container. Nessuna esecuzione sul VPS.
- Cadenza15m invariata dal brief; next_check_minutes=15, pausa15–120 sono distinti. Non applicata la modifica parser proposta nella review.
- Handoff/PR#6 aggiornati, diario `12faf1a0c9247abe739b68599268500fc622be64`. Prossimo: Claude review installer; merge e deploy solo con autorizzazione pertinente.
