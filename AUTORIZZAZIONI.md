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

## 2. Merge nei rami di integrazione — **NON ancora autorizzati**

Il proprietario è favorevole ad autorizzare merge tecnici senza conferma per ogni PR, ma **per il momento non autorizza alcun merge**. Prima Claude deve comunicare il nome esatto del ramo e l'esito di questi controlli:

- non è utilizzato dalla VPS operativa;
- non attiva deploy o modifiche ai servizi;
- non è collegato a workflow che producano cambiamenti operativi;
- ogni modifica è verificata con test pertinenti;
- è possibile tornare allo stato precedente.

Dopo la comunicazione, il proprietario potrà autorizzarne l'uso continuativo. Fino ad allora: nessun merge.

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

---

## Stato (aggiornabile da Claude, senza cambiare le autorizzazioni)

| Voce | Stato al 19/11/2026 |
|---|---|
| Merge | **non autorizzati**. Proposta di ramo di integrazione in `diario/2026-11-19_claude-ramo-integrazione-proposta.md`, in attesa di decisione |
| App GitHub di Claude | scrittura su PR e Issue ancora **403**: da correggere nei permessi dell'app (vedi § 4) |
| Revoca | il proprietario può revocare tutto o in parte con un messaggio; Claude si ferma e registra qui la revoca |
