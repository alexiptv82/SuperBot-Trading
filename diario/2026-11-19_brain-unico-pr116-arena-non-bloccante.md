# Checkpoint 19/11/2026, 11:44 Europe/Rome — STEP 1, PR #116 E ARENA NON BLOCCANTE

**Ambito:** sola documentazione; trading esclusivamente PAPER. Nessun merge, deploy, Action, modifica codice operativo, VPS, servizio, reboot, reset, ordine, wallet o API a pagamento.

## Novità verificate rispetto alle 10:48

1. **STEP 1 non privilegiato eseguito, con limiti.** I commenti pubblicati su Issue #113 e PR #115 riportano una discovery eseguita da Claude Code come utente non privilegiato. Processi/systemd risultano leggibili; 13 unità sono state enumerate. Il riepilogo riferisce Arena con sette componenti attivi, stage Python 338/338 allineato al commit `3dd6aa588339c6136d52e9ff027c91e5e3f80377`, otto radici dati su nove non leggibili, backup esterno inattivo e servizi di uscita Falco/Toro in errore. Non sono stati letti journal/DB né modificati servizi o dati. ChatGPT non ha accesso al report privato e non ha verificato il runtime VPS: questi sono risultati sanitizzati riferiti da Claude, non stato live indipendente.
2. **Decisione utente aggiornata.** Brain Unico è prioritario; Arena non deve ritardarlo. L'utente accetta in linea di principio che la prova Arena PAPER possa terminare prima, anche bloccando nuove aperture o gestendo posizioni simulate, ma soltanto dopo conservazione e riconciliazione verificabili di eventi, trade, NO_TRADE, motivazioni, run ID e stato delle uscite. Non è un ordine di stop immediato, reset o cancellazione e non autorizza questa esecuzione documentale ad agire sulla VPS.
3. **Nuova [PR #116](https://github.com/alexiptv82/SuperBot-Trading/pull/116).** È open/draft, non mergiata, branch `claude/brain-unico-fase0-sealed-20261119`, base esatta PR #115 `465e0d92d76dc24b1dc8ec5df75ec557457f1498`, HEAD `9bf08ac36f868aaf96fb9e63d6c43a3912230aae`. Un commit, 12 file, +2987/−14. Prepara un bundle deterministico per operatore, runner privilegiato con controllo integrità/proprietà, spec incorporata e separazione tra preflight di soli metadati e snapshot completo. È solo codice da revisionare: nessuna esecuzione root o su dati reali autorizzata.

## Stato consolidato per ripresa

### Obiettivo e portafogli PAPER

- **Falco:** storico PAPER e specializzazione SHORT da preservare integralmente; runner non da riattivare. Il risultato Step 1 sui servizi di uscita è un'anomalia riferita, da non correggere automaticamente.
- **Toro:** storico PAPER da preservare; runner non da riattivare. Proposte LONG precedenti non sono promosse.
- **Brain storico:** dati, EventJournal, memoria e scoreboard da conservare; resta fermo salvo decisione separata. Il nuovo Brain non è un reset del vecchio.
- **Brain Unico desiderato:** un solo decisore AI con revisore, apprendimento quantitativo verificabile da feature point-in-time, esiti, NO_TRADE, MFE/MAE, costi/funding e provenienza; Falco SHORT solo advisory, non veto/copy-trading. Questo è obiettivo, non funzione già rilasciata.
- **Arena PAPER:** corsie DeepSeek/Qwen/MiniMax e relativi journal restano fonti storiche. Può continuare finché non ostacola il progetto e i gate reggono; se conclusa prima, registrare durata effettiva e motivo, bloccare nuove aperture, preservare uscite e riconciliare prima dello stop finale. Nessuna azione Arena è stata eseguita da questo checkpoint.

### Desiderato contro implementato

- **Implementato/preparato in GitHub:** inventario statico PR #114; Fase 0 PR #115; bundle sealed PR #116. Tutte open/draft e dipendenti, nessuna mergiata o distribuita.
- **Eseguito:** solo Step 1 non privilegiato, secondo riepilogo Claude pubblicato. Non ha risolto l'accesso alle fonti: otto radici su nove restano non leggibili.
- **Non eseguito/non autorizzato:** preflight root, Step 2/3, snapshot reale, copia dati, restore su dati reali, training, merge, deploy, modifica servizi o chiusura Arena.
- **Non provato:** completezza delle sei fonti, coerenza cross-source, quiescenza SQLite/WAL, backup esterno cifrato, restore indipendente e apprendimento end-to-end.

## GitHub, test e fonti

- PR #114: open/draft, HEAD `52d84778443727a29715848ba71c82e873c7c820`.
- PR #115: open/draft, HEAD `465e0d92d76dc24b1dc8ec5df75ec557457f1498`.
- PR #116: open/draft, HEAD `9bf08ac36f868aaf96fb9e63d6c43a3912230aae`; compare contro #115: avanti di un solo commit, 12 file.
- Test PR #116 riferiti da Claude/commit: 40 bundle + 90 Fase 0 + 29 inventory PASS; 28 mutazioni su 28 rilevate. Non rieseguiti indipendentemente da ChatGPT.
- Sullo SHA #116 risultano 0 workflow run, 0 check run e nessuno status al controllo; il commit contiene `[skip ci]`, che non è garanzia generale.
- L'hash SHA-256 dichiarato per il bundle è presente nella PR, ma deve essere verificato indipendentemente su una copia pinnata prima di qualunque uso; non è certificato da questo checkpoint.
- `main` non risulta cambiato da queste PR; nessuna release.
- Baseline storiche: PR #112 `86288a356209cef9264a369d24a2e8d7914c5ec2`; RC84 PR #80 `0e29a73a36f668643da4088178bacb8616a45ac0`.

## Backup, chiavi e servizi

- Copia cifrata della chiave age sul PC: output PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica coincidente. Prova la copia PC, non certifica backup o restore sulla VPS.
- Ramo `work/extbackup-bot-stopped-20261109` preparato, non installato. Step 1 lo riferisce inattivo; nessuna attivazione eseguita.
- Nessun segreto, percorso privato, token, passphrase o dettaglio di accesso è incluso qui.
- Non esiste in questa esecuzione un controllo SSH/live VPS; i risultati Step 1 derivano dal riepilogo sanitizzato pubblicato su GitHub.

## Problemi e blocker

1. Code review approfondita di runner privilegiato, builder e bundle generato: boundary di privilegio, catena root-owned, TOCTOU, symlink/mount, allineamento source/bundle e output sanitizzati.
2. Verifica indipendente del commit e dell'hash del bundle prima anche del solo preflight root.
3. Accesso temporaneo e strettamente controllato alle fonti, senza ACL permanenti all'agente e senza pubblicare dati.
4. Spec reale e completa per Falco, Toro, Brain storico e tre Arena; politica WAL/quiescenza e consistenza cross-source.
5. Destinazione con capienza, backup cifrato fuori host, witness/manifest privato e restore su copia vuota. `certifies_backup=false` finché questi gate non sono superati.
6. Se Arena deve terminare prima: procedura idempotente separata con blocco nuove aperture, cattura stato, uscite/chiusure PAPER tracciate, riconciliazione, snapshot su copia e solo infine stop. Richiede consenso operativo separato.

## Prossimo passo sicuro

Revisionare staticamente la PR #116 e verificare in modo indipendente il bundle deterministico e il suo hash, senza eseguirlo. In parallelo continuare solo laboratorio su Training Dataset Builder e procedura di archiviazione anticipata. Qualunque preflight root, snapshot o intervento Arena richiede un nuovo consenso esplicito dopo presentazione dell'azione concreta.

## Istruzioni di ripresa e limiti

Leggere nell'ordine `STATO.md`, questo checkpoint, Issue #113 e PR #114/#115/#116 con i commenti più recenti. Separare sempre: decisione utente, codice preparato, test dichiarati, riscontro GitHub e stato live non verificato. Le conversazioni recenti sono accessibili soltanto come estratti indicizzati; nessuna trascrizione integrale di chat eliminate. Preservare PAPER, storici, EventJournal, memorie, scoreboard, run e backup.
