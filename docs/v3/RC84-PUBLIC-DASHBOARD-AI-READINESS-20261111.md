# 11 novembre 2026 — RC84: gate dashboard pubblica e AI per le nuove run PAPER

**Stato:** verifica VPS REALMENTE eseguita, read-only, [GitHub Actions 42983972925](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42983972925), job 130400670427 SUCCESS. **Nessuna chiave letta in output**, nessuna richiesta ai modelli e nessun ordine, nessun riavvio, nessuna pubblicazione web. La nuova run rimane in pausa e Brain ha il mandato `approved=false`.

## Risultati VPS verificati

| Componente | Esito |
|---|---|
| `superbot-v3-paper-falco`, `superbot-v3-paper-toro`, `superbot-v3-paper-brain-runner` | Tutti ACTIVE |
| Tre `pause.flag` nuove | PRESENTI |
| `superbot-v3-paper-brain-exit` | ACTIVE, heartbeat HEALTHY |
| Brain `mandate.json` | NON approvato |
| Credenziale `ANTHROPIC_API_KEY` nei vecchi container `superbot-desk-hawk` e `superbot-desk-bull` | Presente, valore NON visto |
| Credenziale `DEEPSEEK_API_KEY` nel vecchio `superbot-brain-free` | Presente, valore NON visto |
| Nuovi file `/etc/superbot-v3-paper/falco-ai.env`, `toro-ai.env`, `brain-ai.env` | NON disponibili come file privati validi; i nuovi servizi NON risultano approvvigionati |
| Preview RC84 via Nginx loopback `127.0.0.1:18081` | GET overview senza login = 401, POST Brain close = 423 |
| Dashboard pubblica RC73 `127.0.0.1:8002` | API health = 200 |

**Nota:** la presenza della chiave nel vecchio container NON certifica credito, validità o funzionamento del provider. I file nuovi assenti non provano che nessuna chiave esista nei processi tramite altre origini; ma non vi è prova di provisioning per le nuove unità. Non attivare la strategia senza assicurare Claude su Falco/Toro e DeepSeek su Brain: in assenza di Claude il codice classico può ripiegare sulle regole.

## Passaggio delle credenziali: ancora NON eseguito

Una bozza di trasferimento automatico di chiavi tra vecchi container e file ambiente nuovi **non è stata eseguita** ed è stata **rimossa dal ramo**. Non è stato creato alcun workflow di trasferimento, nessun valore segreto è stato pubblicato, non chiedere all'utente di incollare credenziali in chat/GitHub e non stamparle in log Actions. Usare un metodo di amministrazione segreti sul VPS, revisionato e protetto, che scriva **solo** i tre file di ambiente con permessi 0600 in directory root 0700, senza chiavi exchange e senza logging valori. Poi riavviare **solo i quattro nuovi servizi con tutte le pause presenti**, verificare heartbeat e presenza di chiavi senza chiamare fornitori; lo sblocco richiede consenso distinto e controllo eventuale credito DeepSeek.

## Cutover dashboard pubblica RC84: gate operativo

La preview è isolata, **NON** può essere promossa copiando soltanto il frontend: usa un database di autenticazione separato, mount PAPER in sola lettura e tutti i close disabilitati. La versione pubblica deve preservare il login esistente e i pulsanti `Chiudi ora` corretti.

Prima della pubblicazione, creare una procedura di cutover con rollback che faccia:
1. Backup coerente e prova di apertura DB autenticazione attuale `/opt/superbot/data/superbot.db`, senza estrarre password/WebAuthn.
2. Build pubblica RC84 da commit `0e29a73a36f668643da4088178bacb8616a45ac0`, con frontend e backend stesso SHA, mai sostituire il container RC73 alla cieca.
3. Reindirizzare `DESK_DATA_DIR` e `DESK_DATA_DIR_BULL` alle **NUOVE** run e `V3_RUN_ID`, journal, budget, heartbeat, config, pause, close request/result alla nuova `brain-v3-paper20261111`; nessun vecchio stato sovrascritto.
4. `TRADING_MODE=paper`, `DESK_MODE=paper`, `V3_CUTOVER_READONLY=1`, Telegram mutanti disattivati. Abilitare `V3_ALLOW_CLASSIC_SINGLE_CLOSE=1` solo con prova worker fresco nella nuova run. `V3_ALLOW_BRAIN_SINGLE_CLOSE=1` solo se lease/heartbeat exit-sidecar sano e volume comandi Brain scrivibile esclusivamente dall'app, per singoli close PAPER autorizzati. Mantenere START/RESET/CLOSE_ALL bloccati.
5. Preservare vecchia immagine e frontend, non modificare Nginx di altri servizi; check `/api/health` 200, GET overview 401 senza login, tutti i mutating gate corretti; se non passa, **rollback automatico** a RC73. Non provare un close inventando posizioni.
6. Prova browser autenticato con account esistente da parte dell'utente: tre wallet, capitale, leva e pulsanti solo quando sono realmente disponibili; controllare che i legacy restino nello storico e non nelle nuove posizioni.

## Invarianti per il prossimo avvio PAPER

- Falco 1.000, Toro 1.000, Brain 2.000 USDT, storici precedenti intatti.
- Modalità esclusivamente PAPER, leva Brain 20–50×, stop floor 450, non forzare slot, NO_TRADE valido, nessuna chiusura automatica a mezzanotte.
- Brain split con EXIT sidecar come singolo owner. Startup cooldown 15–30 minuti.
- Nessun merge/deploy automatico, nessun rilascio web o rimozione pause sulla base di questa sola ispezione.
