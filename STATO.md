# STATO CORRENTE SuperBot-Trading — 26 ottobre 2026
Fotografia sintetica per ChatGPT Work, chat normale e Claude. Per lo storico precedente consultare i commit di questo file e ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md. Protocollo: SINCRONIZZAZIONE-WORK-CHAT.md.

## Runtime PAPER (NON toccare senza nuova autorizzazione)
- Hawk + Bull in PAPER sul VPS Singapore, codice **886b30f** (deploy 25/10/2026 21:13 UTC — Actions 40234289443, SUCCESS).
- Deploy P1+P2 eseguito con OK esplicito dell'utente: Fix P1 (sbias LONG, signals.py) e Fix P2 (smart Claude fallback, cli.py+brain.py) attivi sui bot.
- Backup cervello pre-deploy verificato: `bots-20261025-211129-deploy` — hawk 250 trade, bull 129 trade, intatti.
- Capital Management V1 integrato ma con DESK_CAPITAL_V1=off, non abilitare senza OK dell'utente.
- Vincolo immutabile: nessun reset di trade_history, learning_log, lessons.md, errors.md.
- rule-pool è un ramo operativo: il suo HEAD può cambiare per audit/fix senza cambiare l'immagine deployata 886b30f. Non toccare Strasburgo/HiTV.

## Fix P1 e P2 — DEPLOYATI (25/10/2026)
- **P1 sbias LONG** (commit 635b964, merge 4ec05f4): `backend/desk/signals.py` — ridotto peso trend HTF, aggiunto rimbalzo RSI 1h (RSI<35 + mom>0.003 → +10 punti LONG). Revisione Claude: basso rischio, monitorare ingressi LONG.
- **P2 smart fallback** (commit 5e1ee2a + 017dd07): `backend/desk/cli.py` + `brain.py` — flag `_claude_responded`; se Claude risponde con 0: regole solo `only_manage=True`; se Claude non disponibile: fallback completo. Revisione Claude: correzione importante, risolve SHORT spurii.
- **Versione attiva: 886b30f** (trigger deploy). Actions run 40234289443, log: PAPER_AND_RISK_ENVIRONMENT=PASS, RUNTIME_BASELINE_SOURCE=PASS, PAPER_AND_CAPITAL_ENV_VERIFIED_AFTER_DEPLOY=PASS, DEPLOY OK.

## PROGETTO — FIX B AI PROFIT GUARDIAN V1 (SOLO SHADOW)
- Utente ha autorizzato il 24/10 branch isolato, moduli e test, e pubblicazione di una SPECIFICA sul diario. Esplicitamente **vietati merge su rule-pool, deploy e riavvio Hawk/Bull** finché non arriva un ulteriore OK.
- Branch di lavoro: work/fix-b-profit-guardian; base di partenza rule-pool 91132ec; HEAD finale f212d41.
- Implementati SOLO moduli indipendenti backend/desk/profit_guardian.py e backend/desk/portfolio_alert.py, tre file test e workflow CI no-deploy. CI run 40075723911 SUCCESS: 21 test unitari. Nessuna modifica motore attivo.
- Parametri approvati: watch ROI netto 12%, review 20%; CLOSE_FULL, TAKE_PARTIAL 50%; budget separato 0,10 $/giorno UTC condiviso Hawk+Bull, intervallo minimo 30 minuti per posizione.
- ChatGPT è writer dei componenti Fix B; Claude è revisore incrociato paritario.
- **Specifica vincolante:** FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md nel ramo diario. Report: diario/2026-10-24_chatgpt.md.
- **Prossimo passo Fix B:** revisione incrociata con Claude, replay offline, test di convalida, poi OK utente per merge e deploy.

## Altre informazioni operative
- DeepSeek è shadow indipendente: 96 chiamate valide/222 decisioni applied=false (storico 23/10, Action 40072633461).
- Capital Management V1: specifica CAPITAL-MANAGEMENT-V1-SPECIFICA.md; backup/restore V2 certificato; merge e deploy già conclusi. Non confondere con Fix B.
- Vincoli immutabili: nessuna istanza LIVE, nessun doppio processo, preservare DB, trade_history, learning_log, AI memory, vault e journal, non esporre credenziali.

## Claude — collaboratore permanente (25/10)
- Claude (Claude Code, Sonnet 4.6) attivo come collaboratore permanente. Mandato: solo PAPER, controllo VPS via workflow, correzioni su rami separati, nessun deploy/riavvio senza OK.
- Deploy P1+P2 eseguito il 25/10 con OK utente (Actions 40234289443). Versione attiva: 886b30f.
- Dettagli sessione: diario/2026-10-25_claude.md.

## Riferimenti
- LEGGIMI.md, MANUALE-OPERATIVO.md, SINCRONIZZAZIONE-WORK-CHAT.md.
- FIX-B-PROFIT-GUARDIAN-V1-SPECIFICA.md, diario/2026-10-24_chatgpt.md, diario/2026-10-25_claude.md.
- ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md e cronologia Git del precedente STATO.
