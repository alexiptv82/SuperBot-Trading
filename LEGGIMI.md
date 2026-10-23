# SuperBot Trading — Diario di continuità (LEGGIMI)

Questo ramo (`diario`) è la **memoria condivisa** del progetto. Non contiene codice e non è collegato a nessun workflow: scriverci non fa partire deploy, riavvii o altro.

Serve a una cosa sola: **se una delle due AI che lavorano sul progetto (ChatGPT o Claude) non è più disponibile** (crediti finiti, problema tecnico, chat persa), l'altra legge qui, capisce a che punto siamo e prosegue da sola, con la stessa autonomia. Funziona come il diario di una persona che scrive tutto per non dimenticare niente e ripartire il giorno dopo da dove ha lasciato.

L'utente è Alessandro (account GitHub `alexiptv82`). Parla italiano e vuole il minimo lavoro manuale: chi lavora fa il più possibile da solo e gli chiede un solo gesto quando è inevitabile.

## Che cosa c'è qui

| File | Che cos'è | Quando si aggiorna |
|------|-----------|--------------------|
| `STATO.md` | Fotografia di oggi: cosa gira, cosa è stato deciso, cosa è aperto, prossimo passo | A fine di ogni sessione di lavoro (si riscrive, resta corta) |
| `SINCRONIZZAZIONE-WORK-CHAT.md` | Regole obbligatorie per tenere coerenti Work, chat normale e Claude (checkpoint GitHub, un solo autore per componente) | Si legge a inizio sessione, si cambia se cambia il protocollo |
| `CAPITAL-MANAGEMENT-V1-HANDOFF.md` | Decisioni utente e design tecnico per capitale, vault, margini percentuali e dashboard | Si aggiorna dopo nuove decisioni/verifiche e a ogni passaggio di mano |
| `ARCHIVIO-STATO-PRE-SYNC-2026-10-23.md` | Copia immutata del vecchio stato lungo, prima della nuova fotografia breve | Solo archivio |
| `MANUALE-OPERATIVO.md` | Come si lavora sul progetto: rami, workflow, trigger, deploy, controlli, cose da non fare | Quando cambia il modo di lavorare |
| `diario/AAAA-MM-GG_<chi>.md` | Cronologia: cosa è stato fatto, perché, con quale esito (una voce per giorno e per autore) | Durante e a fine sessione (si aggiunge, non si cancella) |
| `STORIA-FINO-AL-19-OTTOBRE.md` | Riassunto di come si è arrivati qui (9–19 ottobre 2026) | Non si tocca |
| `SPECIFICA-EVOLUZIONE-CERVELLO.md` e la risposta di Claude `PIANO-TECNICO-CERVELLO-PROFESSIONALE.md` | Il progetto dell'utente per la prossima fase (Profit Manager, cervello professionale, Turbo Scalp), da valutare insieme | Solo se l'utente la modifica |

## Regole inviolabili (valgono per tutte le AI, sempre)

Sono decisioni dell'utente. Nessuna AI le cambia da sola.

1. **Nessun redeploy dei bot (Hawk, Bull) senza OK esplicito dell'utente.**
2. **Niente live trading.** Il Secret `DESK_MODE` resta `paper` finché l'utente non dice esplicitamente di passare a live.
3. **Niente modifiche a strategia, soglie, limiti di rischio, prompt di Claude (quello che i bot mandano all'API) senza una decisione dell'utente.**
4. **Il "cervello" non si tocca.** I file `trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl` in `/opt/superbot-desk-data/{hawk,bull}/` non si cancellano, non si azzerano, non si modificano: solo crescono.
5. **Le API key di trading non vanno mai nel codice**, solo nei GitHub Secrets.
6. **HI-TV / `hitvprime`** (nginx, DNS, container sul server di Strasburgo) **non si tocca mai.**
7. **Nessun segreto in log, report, commit, diario o chat.** Il repository è **pubblico**: niente password, token, chiavi, chiavi API; niente importi o saldi reali del conto Bitget. Se una credenziale compare in chat, va ruotata.
8. **Mai `git push --force`**, mai riscrivere la storia dei rami. Non si unisce `work/backend-singapore-audit`. Non si fa push sui rami `stable/*` né su `v0.5`.
9. **Un solo autore alla volta per componente** (vedi sotto, riga "In corso" di `STATO.md`).

## Protocollo di continuità (quando una delle due AI non c'è)

1. L'utente apre una chat con l'AI rimasta e le incolla il **messaggio di avvio** (in fondo a questo file).
2. L'AI rimasta legge `STATO.md`, `MANUALE-OPERATIVO.md` e le ultime tre voci di `diario/`, poi dice all'utente in poche righe a che punto siamo.
3. Da quel momento ha **la stessa autorità operativa dell'altra AI su tutti i componenti**: può leggere e scrivere sul repository, aprire rami, fare commit e push, far partire i workflow di controllo, preparare modifiche e (con l'OK dell'utente dove le regole lo richiedono) fare deploy.
4. Le regole inviolabili restano identiche. L'OK dell'utente che serve per un'azione la dà lui, nella chat in cui sta lavorando in quel momento.
5. Quando l'altra AI torna, **non riprende a memoria**: legge prima tutto quello che è stato scritto nel frattempo. Se c'è stato un cambio importante, lo si rivede con l'utente.
6. Quando entrambe sono disponibili, l'utente decide chi guida e chi collabora (rilettura, controlli, seconda opinione). Non si lavora in due sullo stesso componente nello stesso momento.

## Coordinamento di Work e chat normale (regola dal 23/10/2026)

Il protocollo completo è in `SINCRONIZZAZIONE-WORK-CHAT.md`. Si applica a Work, chat normale e, se partecipa, Claude: **leggere STATO e l'handoff su GitHub prima di agire; prenotare i componenti; registrare subito autorizzazioni e risultati con commit; rileggere quando si riprende**. Un OK di analisi/design non è un OK all'implementazione o al deploy.

Questo è un sistema di sincronizzazione **a checkpoint**, non una conversazione in tempo reale fra chat inattive. Se una chat non ha letto l'ultimo commit del ramo `diario`, non è aggiornata. Non dare mai per scontata una sincronizzazione automatica non verificata.

Il vecchio messaggio di avvio in fondo al documento vale per il caso di AI mancante; per il passaggio Work/chat normale utilizzare il messaggio aggiornato in `SINCRONIZZAZIONE-WORK-CHAT.md`.

## Come si scrive nel diario

Prima di cominciare e alla fine di ogni sessione:

```bash
git fetch origin diario
git checkout diario            # (o git worktree add ../diario diario)
git pull --rebase origin diario
# 1. aggiungere/aggiornare la voce di oggi:  diario/AAAA-MM-GG_<chatgpt|claude>.md
# 2. riscrivere STATO.md (una fotografia, non una cronaca)
git add -A && git commit -m "diario: <chi> <data> - <tema>"
git push origin diario
```

- Una voce per giorno e per autore (`2026-10-20_chatgpt.md`): così due AI non si pestano i piedi sugli stessi file. Se nello stesso giorno si lavora in più sessioni, si aggiunge in fondo alla voce con l'ora.
- **Scrivere sempre**: prima di un'azione che ha effetto (deploy, riavvio, trigger con effetti, modifica a un workflow), subito dopo con l'esito, e ogni volta che l'utente prende una decisione. Scrivere anche i tentativi falliti e le cose scoperte, non solo i successi.
- **Come è fatta una voce**: ora (Roma) · cosa è stato fatto · perché · esito verificato (come si è verificato) · cosa resta · eventuali decisioni dell'utente. Frasi brevi, fatti, nessuna ipotesi presentata come fatto.
- **Mai nel diario**: segreti di qualunque tipo, importi o saldi dei conti Bitget reali, password, indirizzi privati. Il repository è pubblico.
- Se le informazioni nel diario e quelle viste sul server o nel codice non coincidono, **vale quello che si vede dal vivo**, e si corregge il diario.

## Messaggio di avvio da incollare a una AI

> Lavoriamo sul progetto SuperBot Trading (repository GitHub `alexiptv82/superbot-trading`, è pubblico). Prima di fare qualunque cosa leggi, sul ramo `diario`, i file `LEGGIMI.md`, `STATO.md`, `MANUALE-OPERATIVO.md` e le ultime tre voci della cartella `diario/`. Poi dimmi in poche righe a che punto siamo, cosa è aperto e qual è il prossimo passo. Le regole inviolabili valgono sempre (paper, niente redeploy dei bot senza il mio OK, il cervello non si tocca, nessun segreto nel repository). L'altra AI al momento non è disponibile: prosegui in autonomia e tieni il diario aggiornato a fine sessione.
