# AUTORIZZAZIONI — Claude Code, responsabile operativo dello sviluppo

**Data della decisione:** 19/11/2026 · **Proprietario:** utente del progetto (account `alexiptv82`)
**Natura:** temporanee, **revocabili in qualsiasi momento**, limitate alle attività elencate.
**Regola di manutenzione:** Claude **non modifica autonomamente** il contenuto di questo documento. Lo aggiorna solo il proprietario, o Claude su sua istruzione esplicita. Il registro di stato in fondo (§ Stato) è l'unica parte che Claude può aggiornare.

Il ruolo di responsabile operativo principale di Claude è temporaneo e revocabile. ChatGPT resta consulente esterno; Grok resta responsabile del laboratorio LLM.

## 1. Autorizzazioni stabili (fino a nuova comunicazione)

1. Leggere e analizzare il codice, la documentazione, il diario e lo stato dei servizi VPS, usando **esclusivamente i permessi già disponibili** e senza accedere inutilmente a segreti o dati privati.
2. Creare branch isolati, sviluppare componenti, correggere problemi ed eseguire test locali e offline.
3. Aprire, aggiornare e chiudere le **proprie** PR in bozza, commentare le Issue e mantenere aggiornati diario, roadmap e documentazione.
4. Installare nella propria home strumenti e dipendenze di sviluppo, in ambienti isolati, **senza root, sudo o modifiche globali** al sistema.
5. Coordinare autonomamente lo sviluppo del Brain Unico: memoria, Dataset Builder, strategie, gestione del rischio, dashboard e integrazioni sperimentali.
6. Correggere i problemi già identificati, comprese la PR #121 e la Issue #124, e prepararne la validazione.

## 2. Merge nei rami di integrazione — AUTORIZZATI SOLO in `integration/brain-unico-20261119`

**Decisione del proprietario, seconda comunicazione del 19/11/2026 (riportata fedelmente):**

> **Ti autorizzo a effettuare merge tecnici esclusivamente nel ramo:**
>
> `integration/brain-unico-20261119`
>
> Questa autorizzazione è temporanea, revocabile e subordinata alle seguenti condizioni:
>
> - Il ramo deve rimanere completamente separato dal sistema operativo.
> - Nessun deploy o modifica ai servizi VPS.
> - Nessuna modifica al ramo `main` o ai rami operativi.
> - Test pertinenti eseguiti prima e dopo ogni integrazione.
> - Nessuna nuova regressione rispetto alla baseline.
> - Verifica dei conflitti e delle dipendenze tra PR.
> - Commit e risultati documentati.
> - Possibilità concreta di rollback.
> - Nessuna modifica alle soglie operative senza autorizzazione.
>
> Non autorizzo merge indiscriminati: ogni componente deve essere tecnicamente pronto.
>
> Se scopri che il ramo viene utilizzato da qualche procedura operativa, questa autorizzazione si sospende automaticamente.

Resta **non autorizzato** ogni merge verso `main` o altri rami operativi (§ 3).

## 3. Operazioni che richiedono SEMPRE l'autorizzazione del proprietario

- Deploy e modifiche ai servizi operativi.
- Riavvio o arresto dei bot.
- Conclusione anticipata dell'Arena.
- Modifiche alle posizioni PAPER attive.
- Modifiche ai parametri di trading in esecuzione.
- Reset o cancellazione di dati.
- Accesso privilegiato per acquisire storici reali e backup.
- Operazioni di ripristino che possano modificare dati esistenti.
- Nuove spese API.
- Trading LIVE.
- Modifica di credenziali, autorizzazioni e permessi.
- Merge verso `main` o altri rami operativi.

## 4. GitHub

Si verifica prima se sia possibile correggere i permessi dell'app GitHub di Claude. Se non fosse possibile, si valuterà insieme un token fine-grained, limitato al solo repository e con scadenza.
Claude **non crea autonomamente nuove credenziali** e **non chiede di incollarle in chat**.

## 5. Diario e continuità

Claude salva i progressi nel diario, verifica il meccanismo dei checkpoint già esistente ed evita duplicazioni.

## 6. Priorità

Completare il Brain Unico: verifica finale della PR #121, correzione P0 della Issue #124, successive integrazioni della memoria. Autonomia tecnica, qualità e continuità, con le operazioni a conseguenze reali sotto il controllo del proprietario.

## 7. Altre direttive della seconda comunicazione del 19/11/2026 (riportate fedelmente)

- **P0 #124:** prima di considerare completato il RiskManager, il proprietario vuole la conferma della soluzione, documentando commit esatto, test di riavvio dopo HALT, file corrotto o mancante, errore di scrittura, recupero del PnL sotto la soglia, sblocco al giorno UTC successivo, indipendenza dell'ExitService, compatibilità con la PR #121, distinguendo i fallimenti preesistenti dalle nuove regressioni. Se risolto e verificato, l'integrazione nel ramo autorizzato può essere preparata.
- **Memoria e Dataset Builder:** l'ordine degli eventi nel journal è una condizione necessaria, non una certificazione sufficiente della provenienza delle feature; si continuano a escludere dal training gli snapshot non attestati. Autorizzato lo sviluppo, su un ramo isolato di Claude, della correzione dell'adattatore #122, **senza modificare direttamente il ramo originario di ChatGPT**; poi integrazione verificando assenza di leakage temporale e storici intatti.
- **Grok:** lascia a Grok la ricerca e la sperimentazione sui modelli economici; Claude può analizzare la PR #120 e definire i requisiti di compatibilità, e valuterà l'integrazione quando riceverà il lavoro. DeepSeek resta il decisore principale fino a nuova decisione.
- **Strategia e rischio:** si procede con lo studio del profilo di rischio v2, **separato** dalle correzioni P0. Niente leve elevate imposte automaticamente quando il rischio non lo consente. **Le soglie operative attuali restano invariate fino all'approvazione del proprietario.**
- **Arena e storici:** conservazione integrale dello storico dell'Arena, comprese le operazioni in perdita; i risultati negativi non vanno inseriti automaticamente nel training. L'Arena non deve ritardare il Brain Unico; una sua conclusione anticipata richiede comunque l'autorizzazione del proprietario e un backup verificato.
- **Autonomia:** Claude organizza le priorità e gestisce le dipendenze; un componente pronto, testato e compatibile può essere integrato nel ramo di laboratorio autorizzato. Nessun deploy operativo, merge su `main`, reset, modifica ai servizi attivi o nuova spesa senza consenso.

---

## Stato (aggiornabile da Claude, senza cambiare le autorizzazioni)

| Voce | Stato al 20/11/2026 |
|---|---|
| Merge | **autorizzati solo in `integration/brain-unico-20261119`** alle condizioni del § 2; verso `main` e rami operativi non autorizzati. Registro delle integrazioni in `diario/2026-11-19_claude-registro-integrazione.md` |
| App GitHub di Claude | scrittura su PR e Issue ancora **403**: da correggere nei permessi dell'app (vedi § 4) |
| Conferma del 20/11/2026 | il proprietario ha riconfermato nella sessione Claude Code: sviluppo e integrazione **solo** in `integration/brain-unico-20261119`, test prima/dopo, zero regressioni, documentazione, rollback; esclusi merge su `main`, deploy, servizi operativi, reset, parametri attivi, nuove spese API, LIVE; revocabile in ogni momento. Il conflitto di provenienza segnalato dal checkpoint ChatGPT 20:49 è chiuso (vedi anche checkpoint 21:48). Il testo delle autorizzazioni (§ 1–4) non è stato modificato |
| Revoca | il proprietario può revocare tutto o in parte con un messaggio; Claude si ferma e registra qui la revoca |
