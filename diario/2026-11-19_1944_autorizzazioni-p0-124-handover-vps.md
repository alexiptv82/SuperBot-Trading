# Checkpoint verificabile — autorizzazioni Claude, P0 #124 e handover operativo

**Data:** 19/11/2026 19:44 Europe/Rome  
**Ambito:** consolidamento documentale; nessuna azione operativa eseguita da questo checkpoint.

## Novità verificate dopo il checkpoint delle 18:45

### Autorizzazioni temporanee e revocabili

- Nel ramo `diario` è presente [`AUTORIZZAZIONI.md`](https://github.com/alexiptv82/SuperBot-Trading/blob/diario/AUTORIZZAZIONI.md), blob `2f4968d39be6f413e951a3d181c8edaa919d2ca4`, registrato dal commit diario `f649cb51cf198573b7f5ec6ff24bbbab22b4ce6f`.
- Il documento formalizza Claude/Cloud come responsabile operativo principale **temporaneo e revocabile**; ChatGPT resta consulente esterno e custode dei checkpoint; Grok resta sul laboratorio LLM.
- Autorizzati: lettura/analisi con permessi già disponibili; branch isolati; sviluppo e correzioni; test locali/offline; proprie PR draft/Issue/documentazione; dipendenze isolate nella home senza root; coordinamento tecnico del Brain Unico; preparazione delle correzioni #121/#124.
- **Merge non autorizzati.** Richiedono ancora decisione del proprietario, anche sul ramo di integrazione.
- Richiedono sempre consenso separato: deploy, servizi, restart/stop, conclusione Arena, posizioni PAPER attive, parametri trading, reset/cancellazioni, storici/backup privilegiati, restore, nuove spese API, LIVE, credenziali/permessi e merge verso rami operativi.
- L'app GitHub di Claude continua a ricevere 403 sulle scritture PR/Issue; nessuna nuova credenziale è stata creata.

### Handover Claude e test aggiornati

- Nuovo rapporto: [master handover e roadmap](https://github.com/alexiptv82/SuperBot-Trading/blob/diario/diario/2026-11-19_claude-master-handover-roadmap.md), commit diario `a2aa87a8aa85f4e23f0e7f33e6a34f2635e5c2b3`.
- PR #121 resta open/draft @ `5b7403aa333b43d801ca7e28825ea4707f6847b4`. Claude riferisce ora 8/8 test mirati e suite pertinente **1117 PASS, 0 FAIL** dopo installazione delle dipendenze mancanti; i cinque precedenti fail `rc84_import_paths` erano ambientali per `numpy` assente.
- Questi risultati provengono dal worktree isolato Claude, non da GitHub Actions: 0 workflow/status sulla HEAD e nessun merge.
- PR #122 @ `513448e57747f381e11ce23ab09788d6a41e6cb0`: Claude riferisce 11 test/13 sottotest PASS. Resta un rischio di leakage temporale: il collegamento con #118 dovrà usare il numero di sequenza del journal e test anti-retrodatazione.
- PR #120 resta non conforme: router gratuito primario, DeepSeek fallback e `auto:smart`; inoltre confligge su `wiring.py`. Non integrabile nella forma attuale.

### P0 #124 corretto su branch, non ancora in PR

- Branch verificato: `claude/brain-unico-daily-loss-latch-p0-20261119` @ `ddd130847ae6ccdd2300b4d4ceba1ccde7e2a75e`, impilato sulla PR #121.
- Rapporto: [P0 #124 latch](https://github.com/alexiptv82/SuperBot-Trading/blob/diario/diario/2026-11-19_claude-p0-124-latch.md).
- Il candidato introduce stato v2 e ricostruzione della giornata da EventJournal/candele 1m quando la continuità non è dimostrata; incertezza ⇒ blocco delle sole nuove aperture, con uscite/sidecar autonomi.
- Claude riferisce: baseline vulnerabile `ok` ⇒ candidato `halt`; 32 nuovi test; suite V3 **5063 PASS, 0 FAIL, 1 skip**; mutazioni 14/15 più wiring. Test offline, worktree isolato, non-root.
- Soglie 35% WARN, 50% HALT e floor equity 450 USDT invariati.
- Nessuna PR draft è stata aperta per il 403 dell'app Claude; branch pubblicato e descrizione pronta. Issue #124 resta open e il NO-GO deploy resta valido fino a review/PR/integrazione autorizzata.

### Ramo di integrazione proposto

- Branch verificato: `integration/brain-unico-20261119` @ `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`, non protetto.
- È un semplice puntatore alla base usata dalle PR #120–#123, senza codice nuovo.
- Claude riferisce base suite V3 **5023 PASS, 1 skip**, nessun workflow automatico push/PR su `integration/*`; restano workflow manuali selezionabili da una persona.
- Rollback proposto: merge `--no-ff` e `git revert -m 1`; nessun force push.
- **Stato:** ramo creato, ma merge ancora non autorizzati. La richiesta di autorizzazione continua è una proposta, non un consenso già dato.

## Stato VPS riferito da Claude — non ricontrollato qui

Il rapporto Claude dichiara osservazione non-root, senza sudo, segreti, journal/DB o modifiche ai servizi:

- Arena: tre runner e tre servizi uscite più close bridge riferiti attivi, codice `3dd6aa5`.
- Brain V3: servizi uscite/close bridge/relay riferiti attivi; runner di nuove aperture riferito fermo.
- App web riferita attiva.
- `superbot-extbackup.timer` riferito attivo, ultimo esito success 19/11 03:21 UTC.

Questi punti sono evidenza attribuita al rapporto Claude, **non verifica live indipendente di questa esecuzione**.

### Incongruenza extbackup

- GitHub conferma ancora il ramo preparato `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- Il precedente stato “non installato” è ora in conflitto con il timer VPS riferito da Claude.
- Non sono verificati versione installata, destinazione, contenuto, cifratura, off-host o restore. Quindi il backup esterno **non è certificato** e non va dichiarato né assente né funzionante end-to-end finché non viene svolta una verifica autorizzata.

## Stato consolidato dei portafogli PAPER

- **Falco:** storico e logica SHORT preservati; nel Brain Unico advisor non bloccante. Nessuna modifica operativa qui.
- **Toro:** storico preservato come archivio/benchmark; nessun reset.
- **Brain:** Brain Unico non è ancora un sistema in esecuzione; componenti e filoni #114–#123 restano draft/laboratorio. Brain storico/Arena, EventJournal, memorie, decisioni, trade e posizioni vanno preservati integralmente.
- Dati Arena negativi: conservare integralmente, ma ammissione al training solo con prove di provenienza, sequenza causale e attestazione.
- Configurazione LLM desiderata: DeepSeek primario; advisor economici solo shadow con modelli/provider/versioni fissati. Nessuna promozione automatica.

## Riferimenti e sicurezza invariati

- RC84 PR #80: open/draft @ `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK`, chiave pubblica coincidente; verifica della copia locale, non del backup/restore VPS.
- Nessun segreto letto o pubblicato. Nessuna trascrizione integrale di chat eliminata.
- Nessun merge, deploy, Action, modifica VPS, restart, reset, ordine, training o API a pagamento eseguito da questo checkpoint.

## Blocker e prossime attività

1. Aprire/revisionare la PR draft del P0 #124 solo con i permessi disponibili; mantenere NO-GO deploy.
2. Review indipendente del branch `ddd1308…`, soprattutto ricostruzione, continuità, skip/mutazione sopravvissuta e dipendenza dalla #121.
3. Non usare il ramo di integrazione per merge finché il proprietario non autorizza esplicitamente.
4. Collegare #122→#118 con `seq` del journal e test anti-leakage prima del training.
5. Verificare extbackup soltanto con consenso per accesso/configurazione/restore; fino ad allora stato non certificato.
6. Preservare Arena e storici; nessuna conclusione/stop/reset senza consenso separato.

## Istruzioni di ripresa

Leggere nell'ordine: `STATO.md`, `AUTORIZZAZIONI.md`, questo checkpoint, handover Claude, rapporto P0 #124, PR #121/#122 e Issue #124. Distinguere sempre fra autorizzato, proposto, preparato, verificato offline, riferito dalla VPS, approvato e installato.
