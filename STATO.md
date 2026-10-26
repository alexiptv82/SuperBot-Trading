# STATO CORRENTE SuperBot-Trading — 26 ottobre 2026

Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore. Deploy P1+P2 completato il 25/10 ore 21:11 UTC (Actions 40234289443), versione dichiarata `886b30f0`. Backup pre-deploy: bots-20261025-211129-deploy (hawk 250 trade, bull 129 trade — intatti). Avvio sequenziale Hawk→Bull, PAPER_AND_RISK_ENVIRONMENT=PASS, PAPER_AND_CAPITAL_ENV_VERIFIED_AFTER_DEPLOY=PASS.
- Capital Management V1 installato sul VPS con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente.
- Nessuna chiave privata nei file del repository. Non toccare Strasburgo/HiTV.

## Fix in produzione (deployati il 25/10)
- **P1 — sbias LONG scoring** (merge `4ec05f43`, deploy `886b30f0`): signals.py — trend 4h ridotto 20→14pt, trend 1d ridotto 15→10pt, bonus rimbalzo RSI intraday (RSI<35 + mom1h>0.3% → +10pt LONG). Problema risolto: 18 SHORT perdenti su 19 aperture il 25/10 per bias strutturale HTF.
- **P2 — smart Claude fallback** (merge `017dd07d`, deploy `886b30f0`): cli.py + brain.py — flag `_claude_responded` distingue hold deliberato da Claude non disponibile. Se Claude risponde con lista vuota → regole solo gestione posizioni aperte (no nuove aperture). Se Claude unavailable → fallback completo alle regole.

## Fix in sviluppo (NON in produzione)
- **Fix B — AI Profit Guardian V1** (SOLO SHADOW): branch `work/fix-b-profit-guardian`, HEAD `f212d414`. Moduli indipendenti profit_guardian.py e portfolio_alert.py, 21 test CI SUCCESS. Vietati merge su rule-pool, deploy e riavvio Hawk/Bull finché non arriva OK esplicito utente. Specifica vincolante: FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md nel ramo diario.
- **Prossimo passo Fix B:** revisione incrociata Claude (revisore), poi OK utente per merge.

## Infrastruttura Claude autonoma
- Workflow `.github/workflows/claude-write.yml` su rule-pool (SHA `1dd90048`). Trigger: push a `claude/claude-write.trigger` su rule-pool. Operazioni: merge | push-diario | diario. Branch protetti: mai scrive su main, stable/*, v0.5.
- **CLAUDE_WRITE_TOKEN:** secret da verificare su GitHub Settings → Secrets. Deve avere scope Contents:write. Finché non verificato, il trigger va pushato da ChatGPT.

## Altre informazioni operative
- DeepSeek shadow: ~418 chiamate/giorno, applied=false, container superbot-ai, costo ~0,056$/giorno.
- Vincoli immutabili: PAPER sempre, nessun doppio processo, preservare cervello (trade_history, learning_log, lessons.md, errors.md), non esporre credenziali, backup verificato prima di ogni deploy.

## Prossimi passi (ordine priorità)
1. P5: revisione incrociata Fix B (Claude revisore) + OK utente per merge
2. Verifica CLAUDE_WRITE_TOKEN per abilitare autonomia Claude
3. P6: fix endpoint Bitget L/S ratio 404 in market_context.py
4. P7: fix Open Interest parser in market_context.py
5. F2: hook profit_manager_shadow.py nel ciclo principale

## Claude — collaboratore permanente
- Claude (Claude Code, Sonnet 4.6) attivo. Mandato: solo PAPER, nessun deploy/riavvio senza OK, correzioni su rami separati. Dettagli sessioni: diario/2026-10-25_claude.md, diario/2026-10-26_claude.md.

## Riferimenti
- LEGGIMI.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md.
- FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md, diario/2026-10-24_chatgpt.md, diario/2026-10-25_claude.md.
- ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md e cronologia Git del precedente STATO.
