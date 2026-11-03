# SuperBot — F0 configurazione account limitato riuscita — 2026-11-03, ore 05:48 Europe/Zurich

## Evidenza utente
Screenshot Termius da root@vps-a06df2a7 con output eseguito da `ops/f0/provision_account.sh` al commit `6931d84bed3867a9f773d22744795c9f5dd5c950`:
- `IDENTITA_SERVER: PASS`
- `F0_ACCOUNT_PROVISIONED`
- `ACCOUNT=superbot-f0`
- `FORCED_COMMAND=/usr/local/libexec/superbot-f0-status`
- `NO_SSH_KEY_INSTALLED`
- `F0_SETUP_INIZIALE_COMPLETATO`

## Interpretazione e stato
Installazione iniziale dell'utente diagnostico e del comando fisso riuscita secondo output Termius. La sessione NON prova ancora una connessione SSH con la nuova identità; la nuova chiave pubblica non è installata, la chiave privata non è inserita nei GitHub Secrets, e il workflow non è attivo. PR #30 resta DRAFT non mergiata (verificata via GitHub). Nessuna modifica ai bot, portafogli PAPER, backup Brain, WAL, database o PR V3 è stata effettuata da questa sessione.

## Passi successivi
1. Generare una nuova coppia Ed25519 DEDICATA al monitoraggio F0 (non riutilizzare chiave Termius root), preferibilmente da dispositivo personale sicuro. NON mostrare/inviare la chiave privata in chat o screenshot.
2. Registrare solo la pubblica sulla VPS usando `ops/f0/install_public_key.sh`, prova di proprietà root del comando fisso e `authorized_keys restrict,command`.
3. Inserire la privata **direttamente** in GitHub Repository Actions Secret `SUPERBOT_F0_SSH_PRIVATE_KEY`; verificare workflow e branch protections prima di merge separato della PR #30.
4. Testare login forced-command e rifiuto shell/forwarding, poi job di diagnostica in sola lettura. Solo una fase separata potrà trattare backup cifrati e off-host restore.

Nessuna chiave né credenziale riportata in questo diario. Il precedente backup locale F0 Brain 8.447 eventi è distinto dal progetto di collegamento e non è ancora certificato offhost.
