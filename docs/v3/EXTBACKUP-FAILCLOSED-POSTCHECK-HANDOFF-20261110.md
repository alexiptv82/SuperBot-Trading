# SuperBot — backup esterno: hardening pre/post check (10 novembre 2026)

**Stato:** patch su ramo di lavoro OFFLINE, non rilasciata; NO VPS / NO merge / NO GitHub Actions / NO installazione. Richiede collaudo indipendente di Claude **Sonnet 5.5** e review ChatGPT.

## Base e commit
- Ramo: `work/extbackup-bot-stopped-20261109`, base preparata da Claude (commit `521f7fd`).
- Correzione script: `7fd6f93e95fa9b7644927e75bbe2287cd9893485`
- Aggiunta regressioni: `446b800100b3f6d737431a11cd2abd76677bd7f6`
- Modificati **soltanto** `deploy/extbackup/check-stopped-readonly.sh` e `deploy/scripts/test_extbackup_stopped.py`. `run.sh`, `install-wrapper.sh`, strumenti di backup e runtime dei bot NON modificati.

## Modifiche
1. Il check `pre` accetta `inactive` e `failed` per il servizio backup, blocca `active`, `activating` e qualunque stato assente/sconosciuto, senza assumere che sia sicuro.
2. Il check `post` richiede la firma di 16 caratteri esadecimali restituita da `pre`; firma mancante, malformata o differente è un blocco.
3. `status.json` deve mostrare un `ultimo_successo` non precedente a `ultimo_tentativo` e vicino nel tempo all'ultimo tentativo (massimo 30 minuti), in aggiunta all'assenza di errore e alla freschezza del successo.
4. Il manifesto verificato è selezionato tramite il nome dell'archivio dichiarato in `status.json`, non con `ls|tail` dell'ultimo manifesto. Si controllano nome, istante, SHA del manifesto e SHA del file age cifrato locale; permane il controllo di HEAD Git remoto. Questo non sostituisce la verifica di copia remota indipendente già presente in `external_backup.py`.
5. Aggiunte quattro prove negative: stato servizio sconosciuto, firma pre assente/non valida, ultimo tentativo discordante, archivio cifrato mancante.

## Colloquio con Claude Sonnet 5.5: esecuzione richiesta
Senza usare GitHub Actions, senza rete verso VPS, senza segreti e senza modifica del ramo di release:
- Checkout del commit esatto `446b800100b3f6d737431a11cd2abd76677bd7f6` in sandbox offline.
- Verifica shell `sh -n deploy/extbackup/{run,check-stopped-readonly,install-wrapper}.sh`.
- Esegui test offline con `age`, `age-keygen`, `git`, `sh`, `timeout` presenti e `SUPERBOT_REQUIRE_INTEGRATION=1 python3 -m unittest discover -s deploy/scripts -p 'test_extbackup_stopped.py' -v`. La rete verso GitHub/VPS non è necessaria: repository remoto e servizi sono finti/locali. Riporta PASS, FAIL, SKIP e tempi **esatti**; zero SKIP su prove integrate quando `SUPERBOT_REQUIRE_INTEGRATION=1`.
- Aggiungi test negative se opportuno per manifesto che appartiene a un altro archivio, SHA locale alterato, `ultimo_successo` futuro e post senza firma. Controlla che lo script `post` non modifichi alcun dato o servizio.
- Esamina particolarmente `find` del manifesto, `sed` che estrae il nome, parsing dei timestamp UTC, shell portability, e possibile race tra controllo `pre`, installazione e backup. Segnala anche criticità nuove.
- Non dichiarare il lavoro approvato finché non ci sono risultati reali. Se ci sono difetti, correggili **solo sul ramo di lavoro**, mantenendo inalterati i file operativi e avvisa con SHA, diff e risultati.

## Chiave age e copertura
L'utente ha verificato in PowerShell che la copia cifrata della sua chiave `age` si decifra e che la chiave pubblica ricavata coincide con l'originale. **NON** prova ancora che la chiave privata sul PC corrisponda al destinatario del backup effettivo. Prima di installare, confrontare **solo le chiavi pubbliche** e fare un restore su macchina isolata di un archivio reale, senza divulgare chiave privata/passphrase o copiare segreti in repo pubblico. In caso di chiave differente, non sovrascrivere il destinatario e non perdere la vecchia chiave prima di provare i vecchi backup.

Il vecchio backup esterno è per **Falco/Toro (hawk/bull)**. L'estensione a **Brain V3** è separata e ancora aperta.

## Gate
Restano da fare: prova offline indipendente, code review, controllo read-only VPS con mandato specifico, verifica chiave destinatario, installazione con OK esplicito, backup nuovo+restore isolato, conferma push remoto e conservazione storia. Nessuna ripartenza PAPER automatica.
