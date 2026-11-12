# Checkpoint verificabile — RC84 post-cutover: Telegram nativo assente, relay da riverificare

**Data:** 12/11/2026 13:48 Europe/Rome  
**Ambito:** sola documentazione. Nessuna modifica a VPS, servizi, codice, wallet, ordini, GitHub Actions o provider.

## Novità verificata

Una schermata Termius delle **12:52 Europe/Rome** mostra un controllo in sola lettura dell'ambiente dei processi live:

- `superbot-v3-paper-falco.service`;
- `superbot-v3-paper-toro.service`.

Il controllo è terminato con `RC84_TELEGRAM_CONFIG_CHECK_COMPLETED` e ha stampato soltanto la presenza/assenza delle variabili, senza mostrarne valori o segreti:

| Worker | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_CHAT_ID` |
|---|---|---|
| Falco | **MANCANTE** | **MANCANTE** |
| Toro | **MANCANTE** | **MANCANTE** |

Questo prova che i due worker RC84 appena avviati **non hanno configurazione Telegram nativa nel loro ambiente di processo**.

## Interpretazione corretta

L'assenza delle variabili nei worker non dimostra da sola che gli avvisi Telegram siano interrotti. La [PR #84 Draft](https://github.com/alexiptv82/SuperBot-Trading/pull/84) aveva installato un relay separato, `superbot-v3-paper-telegram-alert-relay.service`, proprio perché le credenziali non erano presenti nei processi Falco/Toro. Il relay era stato verificato in precedenza con API Telegram positive e, per evitare duplicati, è progettato per rifiutarsi di continuare se i trader ricevono token nativi.

Pertanto:

- **assenza token nei worker:** verificata e compatibile con l'architettura relay;
- **relay ancora attivo/healthy dopo il cutover RC84:** non verificato dalla nuova schermata;
- **consegna Telegram post-cutover:** non verificata;
- **Brain Telegram:** non coperto dalla prova e storicamente attività separata.

Non dichiarare “Telegram rotto”, ma neppure “Telegram operativo” senza un controllo diretto del relay.

## Stato PAPER consolidato

Il checkpoint precedente resta valido:

- PR #90 Draft HEAD `0a2fa7e14ff535a20823dbe9a5d7d96c76abd75b`, blob script `dcabc6683e517f09ead3e0bca1a91a719eaf26d0`;
- cutover applicato, quattro unità passate alla sorgente candidata PR #85 `ab7e0b7d991b8f4bd714fccfec23b09a936e6717`;
- Falco/Toro `draining`, Brain runner `paused`, Brain exit `healthy` nella diagnostica post-release;
- tre pause conservate;
- nessuna nuova posizione classica durante il cutover;
- nessun reset e nessun LIVE;
- resume manuale non autorizzato.

I valori Falco 7 e Toro 3 restano soltanto conteggi dello snapshot precedente, non valori correnti. Brain non era stato contato.

## Eseguito / preparato / non approvato

### Eseguito e verificato

- Check in sola lettura dei due processi Falco/Toro.
- Configurazione Telegram nativa assente per entrambi.
- Nessun segreto stampato.
- Prompt ritornato e controllo completato.

### Preparato o storico

- Relay Telegram separato PR #84: ultimo stato storico installato e verificato, ma non ricontrollato dopo il cutover.
- Rollback unità PR #89/90 disponibile, non usato.
- Backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato.
- Verifica PC age: `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup/restore VPS.
- PR #80 RC84 resta riferimento storico Draft.

### Non approvato / non provato

- Nessuna modifica dei token o envfile.
- Nessun restart del relay o dei worker.
- Nessun messaggio Telegram di test.
- Nessun resume, merge, reset, ordine, LIVE o API a pagamento.
- Nessuna prova Telegram Brain.
- Nessuna prova di stabilità prolungata o conteggio posizioni corrente.

## Blocker aggiornati

1. **Prima del resume**, verificare in sola lettura che il relay PR #84 sia active/healthy, non in restart loop, con ledger/dedup accessibile e senza doppio sender.
2. Non inserire automaticamente token nei worker: potrebbe violare il controllo anti-duplicazione del relay.
3. Verificare separatamente il percorso notifiche Brain; non dedurlo da Falco/Toro.
4. Conservare i tre `pause.flag` e il divieto di resume finché salute servizi, owner uscite e notifiche non sono documentati.
5. Backup off-host e restore restano non certificati.

## Prossimo passo sicuro

Senza modificare configurazioni o inviare notifiche, eseguire un controllo read-only del servizio relay: stato systemd, PID/restart count, configurazione senza valori sensibili, ultimo heartbeat/ledger e assenza di doppio sender. Solo dopo questa prova decidere se serve una correzione. Mantenere PAPER e pause; nessun comando di resume è autorizzato.

## Istruzioni di ripresa

1. Leggere `STATO.md`, il checkpoint del cutover delle 12:42 e questo delta.
2. Distinguere “token nativi assenti” da “relay non funzionante”.
3. Non esporre credenziali e non copiarle nei worker senza piano anti-duplicazione.
4. Preservare EventJournal, storici, learning, snapshot e rollback.
5. Non assumere accesso a chat eliminate o stato VPS successivo alle 12:52.
