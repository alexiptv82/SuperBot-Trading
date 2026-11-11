# 11 novembre 2026 — RC84 AI + Web: verifica VPS riuscita, key gap individuato

**Evidenza diretta:** [GitHub Actions run 42983972925](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42983972925), job 130400670427 SUCCESS; output letto. Script esclusivamente read-only `deploy/scripts/v3-rc84-credential-and-web-readonly.sh` sul ramo `work/paper-restart-prep-20261110`.

- Nuovi 3 bot e Brain EXIT attivi; pause presenti, Brain mandato approvato FALSE, exit heartbeat healthy.
- Vecchi Falco/Toro: `ANTHROPIC_API_KEY` presente nell'ambiente dei container fermi; vecchio Brain Free: `DEEPSEEK_API_KEY` presente. **Valori mai stampati, copiati o esposti.**
- Nuovi file Ambiente `/etc/superbot-v3-paper/falco-ai.env`, `toro-ai.env`, `brain-ai.env` non presenti in forma validamente protetta (risultato False). Non affermare che le credenziali AI siano state collegate alle nuove run.
- Preview RC84: GET overview senza login 401; POST Brain close 423; dashboard pubblica RC73 ancora sana su :8002.
- **Nessuna nuova chiamata AI, nessun ordine, nessuna modifica VPS** in questo controllo. Il credito effettivo dei provider non è provato.
- Una bozza di script locale di trasferimento chiavi è stata scritta sul ramo ma **mai eseguita**; la creazione di un workflow per eseguirla non è stata autorizzata dagli strumenti di sicurezza, e il file sorgente è stato eliminato dal ramo in commit `c20cd6cafa39ca391d09a62bebbeedca2f5dfddd`. Nessun trasferimento segreti da GitHub Actions.
- Plan di rilascio dettagliato [RC84-PUBLIC-DASHBOARD-AI-READINESS-20261111.md](https://github.com/alexiptv82/SuperBot-Trading/blob/work/paper-restart-prep-20261110/docs/v3/RC84-PUBLIC-DASHBOARD-AI-READINESS-20261111.md): nuova dashboard NON è una copia statica della preview. Preservare il DB login della vecchia app, montare run nuove, verificare chiusure per singola posizione su tutte e tre solo quando i writer sono sani, rollback RC73 e nessun toggle start/reset.
- **Gate bloccante al trading:** chiavi Claude/DeepSeek delle nuove run non ancora provisionate, validità/credito non verificati. Non rimuovere pause. Il web pubblico non è stato spostato.

**Prossimo passo:** amministrazione segreti *on VPS* protetta senza valori in chat, poi restart SOLO dei servizi nuovi ancora PAUSED e test heartbeat; infine cutover RC84 web con prova login e rollback, consenso distinto per sbloccare trade PAPER. Evitare altri workflow inutili. La suite RC84 offline PASS su SHA `0e29a73`, ma la sua versione pubblica resta RC73.
