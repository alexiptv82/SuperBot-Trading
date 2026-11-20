# Provenienza delle skill (prima selezione: 5)

Fonte: https://github.com/agiprolabs/claude-trading-skills @ `981e1d736cdc02bdc1c55c74ec9224e956414706` (MIT, `LICENSE-claude-trading-skills.md`).
Prima selezione decisa dal proprietario il 20/11/2026: `exit-strategies`, `risk-management`, `position-sizing`, `trade-journal`, `walk-forward-validation`.
Le altre cinque (regime-detection, slippage-modeling, portfolio-analytics, signal-classification, strategy-framework) restano sul branch `claude/skills-trading-20261120`.

Modifiche agli originali:
1. riga `description` del frontmatter: clausola "Use when…" (EN/IT) e avviso di applicabilita';
2. sezione iniziale "SuperBot: leggere prima": verifiche fatte sul codice del progetto (mercato futures USDT-M, regole che prevalgono, errori noti della skill).

Nessuno script e' stato eseguito, nessuna dipendenza installata. Esito dei confronti: `docs/v3/SKILL-CONFRONTO-20261120.md`.

## Attivazione verificata (20/11/2026)
Sessione Claude Code locale sulla VPS (non una sessione cloud di un Project). Secondo la documentazione ufficiale (https://code.claude.com/docs/en/skills) le skill personali in `~/.claude/skills/` vengono rilevate nella sessione in corso senza riavvio, mentre le skill di un repository valgono per le sessioni avviate in quel repository (e le sessioni cloud dentro un Project non le caricano).
Per questo le cinque skill sono installate anche come skill personali dell'utente della VPS (`~/.claude/skills/<nome>`, copie identiche a questi file). Prova: richiamate con lo strumento Skill, tutte e cinque caricate con la sezione "SuperBot: leggere prima".
Se questi file cambiano, la copia personale va riallineata (`cp -r .claude/skills/<nome> ~/.claude/skills/`).
