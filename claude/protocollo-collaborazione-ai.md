# Protocollo di collaborazione AI — SuperBot-Trading

Ultimo aggiornamento: 26 ottobre 2026

## Ruoli

| Ruolo | Chi | Responsabilità |
|---|---|---|
| Decisore finale | Alexander (utente) | Ogni deploy, merge, modifica a strategia o rischio richiede OK esplicito suo |
| Writer tecnico | ChatGPT (GPT-4o / o3) | Equivalente a Claude — scrive codice, fa push, merge, deploy su OK utente |
| Writer tecnico | Claude (Claude Code, Sonnet 4.6) | Equivalente a ChatGPT — scrive codice, fa push, merge, deploy su OK utente |
| Shadow indipendente | DeepSeek | Analisi parallela non vincolante, applied=false |

ChatGPT e Claude sono **equivalenti e paritetici**: nessuno ha autorità sull'altro. L'utente decide chi lavora su cosa e quando.

## Principio del singolo autore

Un solo AI è writer di un componente alla volta. Non si sovrascrive il lavoro dell'altro senza accordo esplicito con l'utente.

Esempio: ChatGPT è writer di Fix B (`work/fix-b-profit-guardian`); Claude è revisore. Prima del merge Claude consegna la revisione, poi l'utente decide.

## Memoria condivisa

Il branch `diario` del repository `alexiptv82/SuperBot-Trading` è la memoria condivisa tra le due AI.

Dopo ogni sessione di lavoro significativa, l'AI che ha lavorato aggiorna:
- `STATO.md` — fotografia corrente del sistema
- `diario/YYYY-MM-DD_{ai}.md` — voce di diario della sessione

Commit di sola documentazione: sempre con `[skip ci]` nel messaggio.

## Cosa può fare un'AI autonomamente

- Leggere qualsiasi file del repository
- Aprire branch `work/*` isolati
- Eseguire workflow di sola lettura (desk-mode-check, desk-status)
- Aggiornare il diario e STATO.md
- Preparare fix su branch separati
- Eseguire CI/test su branch non operativi

## Cosa richiede sempre OK esplicito dell'utente

- Deploy o riavvio dei bot Hawk e Bull
- Merge di qualsiasi branch su `rule-pool`
- Modifica a soglie, limiti di rischio, scoring, prompt Claude
- Abilitazione LIVE (`DESK_MODE=live`)
- Abilitazione Capital Management V1 (`DESK_CAPITAL_V1=on`)
- Qualsiasi operazione sui container del VPS (stop, rm, build)
- Push su `stable/*`, `v0.5`, o force-push su qualsiasi branch

## Regole inviolabili (da CLAUDE.md)

1. Nessun redeploy dei bot senza OK esplicito dell'utente
2. `DESK_MODE=paper` finché l'utente non autorizza esplicitamente il live
3. Nessuna modifica a strategia, soglie, limiti di rischio, prompt Claude senza decisione dell'utente
4. Il cervello dei bot (`trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl`) non si cancella, non si azzera, non si modifica: solo cresce
5. Le API key mai nel codice, solo nei GitHub Secrets
6. Mai toccare HI-TV / `hitvprime` (nginx, DNS, container su Strasburgo)
7. Repository pubblico: nessun segreto, nessun importo o saldo reale in codice, log, commit o diario
8. Mai `git push --force`; non unire `work/backend-singapore-audit`; nessun push su `stable/*` e `v0.5`
9. Un solo autore alla volta per componente

## Onboarding di una nuova sessione AI

Prima di lavorare, leggere in ordine:
1. `CLAUDE.md` nel branch `rule-pool`
2. `STATO.md` nel branch `diario`
3. `claude/protocollo-collaborazione-ai.md` (questo file)
4. `claude/stato-roadmap-completa.md`
5. Ultime 2-3 voci di `diario/`

Solo dopo confermare all'utente di essere pronto.
