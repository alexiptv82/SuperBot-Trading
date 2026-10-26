# Cartella trigger ChatGPT

Questa cartella contiene il file trigger per le operazioni Git autonome di ChatGPT.

## Come si usa

Per fare un merge, aggiornare il diario o fare push-diario **senza intervento dell'utente**,
ChatGPT crea o aggiorna `chatgpt/chatgpt-write.trigger` con il formato:

```
op=<operazione>
src=<branch sorgente>     # per merge e push-diario
dst=<branch destinazione>
msg=<messaggio di commit>
skip_ci=yes               # opzionale, default yes
```

Operazioni disponibili:
- `op=merge` — unisce `work/*` o `fix-*` in `rule-pool`
- `op=push-diario` — copia STATO.md e file `diario/` dal src branch al branch diario
- `op=diario` — aggiorna il diario da rule-pool (cerca STATO.md e ultima voce `diario/YYYY-MM-DD_chatgpt.md`)

Il workflow `claude-write.yml` (nome: "AI Write") si attiva automaticamente sul push
e imposta l'autore git come "ChatGPT <noreply@openai.com>".

## Equivalente Claude

Claude usa `claude/claude-write.trigger` con lo stesso formato.
Stesso workflow, stesso token (`CLAUDE_WRITE_TOKEN`), stesse guardie di sicurezza.

Documentazione completa: branch `diario`, file `MANUALE-OPERATIVO.md`, sezione 3 e 8.
