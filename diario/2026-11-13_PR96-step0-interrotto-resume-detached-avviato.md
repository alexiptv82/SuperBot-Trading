# Checkpoint verificabile — PR #96 Step0 interrotto; ripresa detached avviata

**Data:** 13/11/2026 17:46 Europe/Rome  
**Ambito:** sola documentazione; esclusivamente PAPER; storici ed EventJournal da preservare.

## Novità verificata

Dopo il checkpoint delle 16:47, i commenti cronologici della [PR Draft #96](https://github.com/alexiptv82/SuperBot-Trading/pull/96) documentano che l'esecuzione Step0 originale non era più attiva e non aveva prodotto `report_step0.json`. Restavano otto CSV: BTC, ETH, SOL e BNB, ciascuno 1H/4H; XRP mancava. Non è stata provata la causa dell'interruzione e il controllo riportato non ha trovato evidenza OOM. Questo **non è un fallimento della strategia**, ma rende il replay storico incompleto e privo di expectancy.

È stata quindi preparata e avviata una ripresa isolata/detached. L'ultimo output verificato prova soltanto:
- sorgenti pinned accettate e syntax check OK;
- unità detached avviata;
- riuso previsto degli otto CSV e fetch previsto del solo XRP;
- log e risultati persistenti per simbolo.

Non prova il completamento, la validità effettiva di tutti gli otto CSV, il download di XRP, la presenza del report, un edge positivo o l'autorizzazione al rilascio.

## GitHub verificato

- PR #96: aperta, Draft, non mergiata, mergeable; base `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Ramo: `work/toro-profit-hunter-v1-20261113`.
- HEAD: `0a4574de847ee518b5d480f8e3f50a5ae139e317`; 27 commit, 9 file.
- `f89487c2f66993c3a4619042e44882182ad72ea3`: procedura di resume con intervallo storico originale congelato, verifica SHA/formato/freshness/copertura, risultati per simbolo e report finale solo se tutti i cinque asset risultano validi.
- `0a4574de847ee518b5d480f8e3f50a5ae139e317`: launcher detached isolato con sorgenti pinned, limiti risorse e log persistente.
- Test core già verificati in precedenza: 19/19 PASS con stage invariato. Lo syntax check del resume non è un test storico né una prova di edge.
- Il corpo iniziale della PR resta in parte obsoleto rispetto ai commenti cronologici; questi ultimi sono l'evidenza più recente.

## Tre portafogli PAPER — desiderato vs implementato

- **Brain:** desiderato attivo PAPER dopo i gate; verificato già unpaused nel checkpoint precedente. Nessuna nuova prova del primo ciclo completo sugli otto simboli, di aperture/chiusure o PnL. Invariato da questa attività.
- **Falco:** desiderato SHORT originale con gate separato; non risulta riattivato o modificato.
- **Toro:** desiderato LONG Profit Hunter con rischio candidato già documentato; core isolato e 19 test PASS, ma replay Step0 ancora incompleto e integrazione CLI/engine/contabilità/Guardian non rilasciata. Non risulta riattivato.

## Fatto / preparato / rilasciato

- **Fatto:** accertata l'interruzione dell'istanza originale senza report; conservati 8/10 CSV; avviata la ripresa detached secondo output utente documentato.
- **Preparato:** resume verificabile e launcher detached ai due SHA sopra, con riuso dati e fetch del solo XRP.
- **Rilasciato:** nulla sui portafogli classici; nessun merge o deploy. Brain non modificato.
- **Non approvato/non provato:** esito finale Step0, edge, adapter PAPER Toro, contabilità maker/claim, Guardian operativo, merge/deploy, riattivazione Falco/Toro.

## Problemi e limiti

1. Report Step0 assente all'ultimo riscontro; nessun dato finale su coverage, segnali, expectancy lorda/netta, PF o benchmark casuale 4/8/12h.
2. Causa dell'interruzione originale ignota; non attribuirla a SSH, eccezione, OOM o altro senza evidenza.
3. L'avvio detached non equivale a completamento; attendere status/log/report.
4. Nessun controllo SSH live indipendente da questo checkpoint e nessuna trascrizione integrale di chat eliminate.
5. PR #96 non è connessa al runner Toro e la sua base precede i due hotfix Brain installati localmente: non sovrascriverli.

## Backup, chiavi e riferimenti storici

- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; **non certifica** backup o restore sulla VPS.
- Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato.
- RC84 PR #80 resta riferimento storico; nessuna assunzione di rilascio ulteriore.
- Nessun segreto, token, passphrase, chiave privata o dettaglio utile all'accesso VPS registrato.
- Solo PAPER; storici ed EventJournal devono restare integri.

## Prossimo passo / istruzioni di ripresa

1. Verificare in sola lettura stato finale dell'unità detached, coda del log e presenza del report.
2. Se completo, acquisire per tutti i cinque asset: SHA/fonti, coverage/freshness, segnali, expectancy lorda/netta costi, PF e benchmark appaiato 4/8/12h, inclusi errori.
3. Se incompleto, diagnosticare dai log senza lanciare un job concorrente e senza tuning sulla stessa finestra.
4. Non interpretare i 19/19 PASS o il semplice avvio come prova di redditività.
5. Qualsiasi merge, deploy o riattivazione Falco/Toro richiede consenso separato; nessuna azione operativa è autorizzata da questo checkpoint.
