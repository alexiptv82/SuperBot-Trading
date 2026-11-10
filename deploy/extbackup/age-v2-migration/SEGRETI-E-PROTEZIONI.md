# Segreti di GitHub e protezioni: che cosa protegge che cosa (piano corretto)

**Stato dichiarato: il Secret `SUPERBOT_AGE_RECOVERY_KEY_V2` NON è protetto dall'ambiente.** Esiste a livello di **repository**; l'ambiente `age-recovery`
(se esiste) non lo copre. Questo documento non lo dichiara protetto e nessun controllo automatico può dire il contrario: il valore di un Secret non si può
leggere (nemmeno dal proprietario) e il `GITHUB_TOKEN` di un workflow non può elencare dove sia memorizzato. Si controlla solo dall'interfaccia di GitHub
(§5) e si dichiara «protetto» soltanto dopo la sostituzione descritta in §3.

## 1. Le cinque cose, distinte
| Cosa | Che cosa fa davvero | Che cosa NON fa |
|---|---|---|
| **Secret di repository** (Settings → Secrets and variables → Actions → *Repository secrets*) | È disponibile a **ogni** workflow del repository, su **qualunque ramo** in cui il file del workflow esista, **senza approvazione**. | Nessuna protezione: non conta se il job nomina un ambiente o no. Chiunque possa far girare un workflow (scrittura sul repository, anche un agente/app con permesso `workflows`) può leggerlo e stamparlo. |
| **Secret di ambiente** (Settings → Environments → `age-recovery` → *Environment secrets*) | È disponibile **solo** ai job che dichiarano `environment: age-recovery` e **solo dopo** che le regole dell'ambiente sono soddisfatte. Se esiste con lo stesso nome di uno di repository, per quei job prevale quello di ambiente. | Non tocca gli altri job: lo stesso nome nel repository resta leggibile da chiunque finché non viene **cancellato**. |
| **Required reviewers** (regola dell'ambiente) | Il job si ferma finché un revisore approva *quella* esecuzione (ramo e commit sono mostrati). «Prevent self-review» impedisce che approvi chi ha avviato (con un solo revisore, il proprietario, va lasciato spento). | Non impedisce a qualcuno di **modificare il workflow**: protegge il momento dell'esecuzione, non il contenuto del file. Chi approva deve guardare il diff. |
| **Deployment branches** (regola dell'ambiente) | Limita i rami da cui un job può usare l'ambiente (es. solo `work/age-v2-recovery-run-20261110`). Un workflow modificato su un ramo qualsiasi non ottiene i Secrets *di ambiente*. | Chi può fare push su un ramo consentito può eseguire lì un workflow modificato: il ramo consentito va protetto (riga sotto). |
| **Protezione dei rami / rulesets e autorizzazioni di scrittura** | Decide chi può creare/aggiornare/cancellare i rami e modificare `.github/workflows/**` (es. ruleset: solo il proprietario sul ramo di esecuzione, no force push, no cancellazione; revisione obbligatoria sul percorso dei workflow). Chi ha **scrittura** può comunque far partire workflow sui rami che può creare. | Non protegge un Secret di **repository**: quello resta raggiungibile da un ramo qualunque creato da chi ha scrittura. |
Impostazioni Actions utili: *Workflow permissions* = sola lettura; richiedere approvazione per i workflow delle pull request da fork; consentire solo azioni scelte (questi workflow non usano nessuna azione di terzi).

## 2. Che cosa implica per questo progetto
* I workflow `age-v2-key-check` e `age-v2-recovery-verify` dichiarano `environment: age-recovery`: l'approvazione umana vale per **loro**. Ma finché la chiave è un Secret di
  repository, **un qualunque altro workflow** (anche scritto da un agente con scrittura sul repository, su un ramo come `cursor/...`) potrebbe leggerla senza approvazione.
* Il repository è **pubblico** e il codice è visibile, ma gli archivi stanno in un repository **privato**: la chiave di lettura in sola lettura (`SUPERBOT_BACKUPS_READ_KEY`) va tenuta
  allo stesso modo come **Secret di ambiente**, non di repository (apre tutti gli archivi cifrati: da sola non basta a leggerli, ma insieme alla chiave V2 sì).
* L'impronta di approvazione dentro il workflow protegge dagli **errori** (file diversi da quelli rivisti), non da un attore con scrittura: un workflow modificato può semplicemente saltare quel controllo.
  Il vero limite è: ambiente con revisore + rami consentiti + protezione di quei rami + niente Secret omonimi nel repository.

## 3. Come mettere davvero in sicurezza la chiave (nessuno può spostare un valore che non può leggere)
Un Secret non si «trasferisce»: si **sostituisce**. Poiché oggi **non esiste nessun archivio V2** (il primo backup V2 non è stato fatto), sostituire adesso non costa nulla.
**Percorso consigliato (B): chiave nuova, solo di ambiente.**
1. Sul PC del proprietario (non in chat, non sulla VPS): crea la chiave con il kit (`chiave_personale.py crea --cartella … --nome chiave-actions`, vedi `CHIAVE-PERSONALE.md`); annota la pubblica.
2. GitHub → Settings → Environments → `age-recovery` → *Add environment secret* → nome `SUPERBOT_AGE_RECOVERY_KEY_V2` (stesso nome: i workflow non cambiano) → incolla il contenuto del file
   della privata dal PC, **senza passare da chat**; cancella in modo sicuro il file locale della chiave *Actions* (resta la chiave personale, §6 di `LEGGIMI.md`, come copia indipendente).
3. Settings → Secrets → *Repository secrets*: **cancella** `SUPERBOT_AGE_RECOVERY_KEY_V2` (e `SUPERBOT_BACKUPS_READ_KEY` se creato lì: ricrearlo nell'ambiente). Senza questo passo l'ambiente non protegge nulla.
4. Nel repository: `python3 deploy/extbackup/v2/set_recipients.py --add <PUBBLICA_ACTIONS>` e `--add <PUBBLICA_PERSONALE>`; se si decide di non fidarsi più della V2 vecchia (il cui valore era un Secret di repository),
   `--remove <PUBBLICA_V2_DOCUMENTATA>`. Commit, revisione, nuova impronta di approvazione. **Prima** di installare sul server.
5. Esegui `age-v2-key-check` (percorso a push, §4): con la chiave nuova dirà «destinatario documentato il 23/10: NO», «tra i destinatari di questo commit: OK», «chiave sostituita» e `ESITO COMPLESSIVO: OK`.
**Percorso alternativo (A): tenere la V2 com'è** — solo se il proprietario accetta che la chiave sia raggiungibile da chiunque abbia scrittura sul repository. Non si può dichiarare protetta e il
ripristino indipendente affidato alla V2 vale quanto la fiducia in quegli accessi. Resta comunque obbligatoria la chiave personale.

## 4. `workflow_dispatch` fuori dal ramo predefinito
GitHub rende eseguibile `workflow_dispatch` (pulsante *Run workflow* e API) **solo se il file del workflow è sul ramo predefinito**; da un ramo di lavoro l'API risponde 404 e il
pulsante non compare. **Non sposto i workflow sensibili su `main`**: la decisione è del proprietario. Quindi:
* **Percorso supportato oggi:** creare dal commit approvato il ramo di esecuzione (`work/age-v2-recovery-run-20261110`, `work/age-v2-keycheck-run-20261110`), aggiungervi il file `RUN.trigger`/`KEYCHECK.trigger`
  con la riga `approval=<impronta>` e fare il push: il trigger `push` esegue il workflow **così come sta in quel commit**. L'ambiente `age-recovery` (revisore, rami consentiti) ferma il job prima dei Secrets *di ambiente*.
* **Chi approva deve confrontare** il commit del ramo di esecuzione con il commit rivisto (`git diff <approvato> <ramo-di-esecuzione>` deve mostrare solo il file `*.trigger`); non lo fa il workflow.
* Il percorso `workflow_dispatch` resta nel file per il giorno in cui il proprietario deciderà di portare il workflow sul ramo predefinito.

## 5. Lista di controllo per il proprietario (solo interfaccia GitHub; ogni voce è oggi «da fare/da verificare»)
| Voce | Dove | Atteso |
|---|---|---|
| Nessun Secret «age» tra i *Repository secrets* | Settings → Secrets and variables → Actions | assenti `SUPERBOT_AGE_RECOVERY_KEY_V2` e `SUPERBOT_BACKUPS_READ_KEY` (la pagina mostra solo nomi e date) |
| Secret nell'ambiente | Settings → Environments → age-recovery | presenti i due Secrets |
| Required reviewers | stesso ambiente | il proprietario; «Prevent self-review» spento se unico revisore |
| Deployment branches | stesso ambiente | *Selected branches*: `work/age-v2-recovery-run-20261110`, `work/age-v2-keycheck-run-20261110` |
| Protezione di quei rami | Settings → Rules → Rulesets | creazione/aggiornamento solo proprietario, no force push, no cancellazione (verificare cosa offre il piano) |
| Chi ha scrittura | Settings → Collaborators and teams; Settings → GitHub Apps / Integrations | solo il proprietario; nessuna app con permesso *Workflows: write* senza motivo |
| Workflow permissions | Settings → Actions → General | *Read repository contents permission* |
| Repository V2 | `superbot-backups-v2` → Settings | privato; deploy key della VPS **in scrittura**, deploy key di lettura **senza** scrittura; regole su `main`, `brain-v3`, `brain-free` (no force push, no cancellazione) |
Finché le prime quattro righe non sono verificate, la frase corretta è: «la chiave di recupero è un Secret di repository, raggiungibile da qualunque workflow con scrittura».
