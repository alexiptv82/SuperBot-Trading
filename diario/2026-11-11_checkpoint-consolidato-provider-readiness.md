# Checkpoint consolidato SuperBot — 11/11/2026 12:54 Europe/Rome

## Scopo e perimetro

Checkpoint documentale di ripresa, basato solo su fonti accessibili: GitHub, Library v54 e messaggi recenti recuperabili. Non è una trascrizione integrale delle chat. Nessuna chiave, passphrase, token, valore di saldo o dettaglio di accesso è riportato.

Solo PAPER. Nessun merge, deploy, modifica di codice operativo, reboot, reset, ordine o chiamata AI a pagamento è stato eseguito da questo checkpoint. EventJournal, wallet simulati e storici restano da preservare.

## Novità verificata — provider readiness

GitHub Actions [run 42995334600](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42995334600), job `check`, COMPLETED/SUCCESS. Trigger commit [`7c3c50b662ecc42fd228d8a681e479fb7e07ffa7`](https://github.com/alexiptv82/SuperBot-Trading/commit/7c3c50b662ecc42fd228d8a681e479fb7e07ffa7), script pinned `798db58e9f8df9b502d3a3339d35bb93cd172f29`.

Il controllo era soltanto GET/metadati-saldo, senza inferenza:

- tre servizi in pausa con variabili provider presenti;
- Claude Falco: HTTP 401, credenziale non accessibile;
- Claude Toro: HTTP 401, credenziale non accessibile;
- DeepSeek saldo: HTTP 200, endpoint disponibile;
- nessun importo, chiave o risposta sensibile nei log;
- nessuna inferenza, trade, acquisto credito, deploy o restart.

Il successo del job certifica l'esecuzione del controllo, non la readiness completa: Falco/Toro non vanno sbloccati finché Claude non è corretto e ricontrollato. HTTP 200 DeepSeek non prova credito sufficiente né qualità operativa.

## Stato consolidato per la ripresa

### Tre portafogli PAPER

- Falco: 1.000 USDT simulati.
- Toro: 1.000 USDT simulati.
- Brain: 2.000 USDT simulati.
- Ultimo stato operativo verificato prima del controllo provider: nuovi servizi attivi ma tutti PAUSED; Brain exit-sidecar unico/healthy; mandato Brain `approved=false`.
- Il controllo provider non ha rieseguito un inventario completo dei servizi. Verificare nuovamente lo stato live prima di dichiararlo corrente.
- Nessuna rimozione pause, approvazione mandato o LIVE senza consenso separato.

### RC84, dashboard e PR

- [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): aperta, DRAFT, non mergiata; HEAD/pin `0e29a73a36f668643da4088178bacb8616a45ac0`, base RC82 `1e64684b9d813aad1ca1c7d344872333e451fd05`.
- GitHub Actions [run 42681449471](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42681449471): backend 7.003 PASS, 9 deselected, 3 xfailed, 0 fail; frontend 124/124 PASS e build React riuscita.
- 71/71 prove browser derivano dal rapporto Claude su ambiente sintetico locale; non equivalgono a Android fisico, VPS o trading reale.
- RC84 pubblica include Brain in Performance e Impostazioni; il 403 Nginx è stato corretto e l'utente ne ha confermato la risoluzione.
- [PR #81](https://github.com/alexiptv82/SuperBot-Trading/pull/81): aperta, DRAFT, non mergiata, HEAD `790dcb01431fd8469f50d113fe56d9e67a83e902`. Rollback RC84/RC73 conservato. UI trading read-only; chiusura singola ancora sotto gate.

### Configurazione/rischio desiderato versus autorizzato

Profilo Brain RC84 preparato per la nuova run: leva 20–50x, margine massimo trade 400 USDT, perdita teorica circa 75 USDT su 350, rischio aperto massimo 12%=240 USDT, floor 450 USDT, ciclo 60 minuti. È configurazione PAPER preparata, non autorizzazione a operare. Falco/Toro mantengono SHORT, Claude consultivo e LONG S25 opt-in. Nessun edge o apprendimento autonomo è certificato.

### Backup esterno e chiave age

- Ramo `work/extbackup-bot-stopped-20261109`, commit [`3dc2116a08058f57fc14b695431f6e3fa1a1ca45`](https://github.com/alexiptv82/SuperBot-Trading/commit/3dc2116a08058f57fc14b695431f6e3fa1a1ca45), revisionato.
- Il controllo post richiede servizio inattivo, risultato success e codice uscita 0; aggiunte prove negative su manifesto, SHA, tempi, firma e stato servizio.
- Il resoconto recente accessibile riferisce 236 test e 101 sottotest PASS; non rieseguiti da questo checkpoint.
- Backup esterno preparato ma NON installato sulla VPS; nessun backup off-host o restore reale certificato.
- Sul PC la copia cifrata della chiave age ha prodotto PowerShell `ESITO: VERIFICA OK`; decifratura riuscita e chiave pubblica coincidente. È verifica della copia locale, non del destinatario produzione, del backup VPS o del restore. Nessun segreto letto o pubblicato.

## Fatto / preparato / rilasciato

- Fatto: web RC84 read-only, Brain nelle sezioni richieste, 403 risolto, conti PAPER e servizi mantenuti in pausa, provider check con Claude 401/DeepSeek 200.
- Preparato: extbackup age V2, chiusura manuale singola PAPER, correzione credenziali Claude e gate di sblocco.
- Rilasciato: solo web/API read-only e servizi PAPER in pausa già documentati.
- Non rilasciato/autorizzato: trading PAPER attivo, mandato Brain, rimozione pause, merge PR #80/#81, LIVE, extbackup installato.

## Blocker e prossimo passo

1. Correggere in modo sicuro le credenziali Claude di Falco/Toro; ripetere GET minimo mentre tutto resta in pausa.
2. Verificare credito/budget DeepSeek solo quanto necessario; HTTP 200 non basta.
3. Collaudare chiusura singola PAPER con owner unico e rollback, senza abilitare aperture.
4. Installare extbackup solo con mandato separato; poi provare archivio cifrato off-host e restore in destinazione nuova.
5. Solo dopo chiedere OK esplicito per mandato Brain e rimozione pause.

## Istruzioni di ripresa

Leggere questo file, `STATO.md`, PR #80/#81 e Library `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md` v55. Verificare nuovamente VPS, posizioni e provider prima di descriverli come correnti. PAPER obbligatorio; preservare EventJournal e storici. Non pubblicare segreti e non confondere prove locali/CI con trading reale.

AI: checkpoint automatico ChatGPT Work
