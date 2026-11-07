# RC70 — collaudo V3 PAPER autorizzato su Singapore (7 novembre 2026)

**Perimetro utente autorizzato:** installare la nuova dashboard e predisporre i servizi manual-exit Falco/Toro sulla VPS Singapore. **Non autorizzati da questa fase:** nuove aperture, chiusure senza clic dell'utente, riavvio motori classici, reset, merge, deploy indiscriminati.

## Risultato operativo verificato

- **Dashboard V3 di collaudo installata e in funzione**, ma **solo su localhost** (`127.0.0.1:18080`) per pagina e proxy; FastAPI separata in Docker `superbot-v3-rc70-preview` su `127.0.0.1:18003`. Nessun ingresso pubblico e **nessuna sostituzione dell'app in produzione**.
- Il backend staging monta come **READ ONLY** `/opt/superbot-backups/rc69-paper-legacy-20261107T110255Z-142218/hawk` e `.../bull` e usa una **copia separata della run Brain PAPER in pausa**. DB app staging indipendente; nessuna credenziale/sessione dell'app principale copiata.
- Il backend staging è eseguito senza chiavi exchange né token Telegram, con `TRADING_MODE=paper`, `DESK_MODE=paper`, `TELEGRAM_COMMANDS_ENABLED=false`, `--restart=no`; le API protette rispondono 401 senza autenticazione. Frontend staging risponde 200.
- **Due unità installate ma DISABLED+INACTIVE**: `superbot-v3-falco-exit.service`, `superbot-v3-toro-exit.service`. Entrambe avviano soltanto `desk.exit_only` in modalità PAPER dietro preflight del proprio portfolio, backup esatto, lock e stop del container legacy. Non sono state attivate, né accodate richieste manuali.
- Per predisporre l'ambiente Python isolato, installato il solo pacchetto Ubuntu `python3.12-venv` senza upgrade generale, quindi installato `numpy` nella venv della directory staging. Nessun restart dei servizi correnti.
- **Verifica indipendente finale**: [GitHub Actions RC70 gate #42369546234](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42369546234) `SUCCESS`: frontend 200, API staging senza auth 401, web produzione 200, mount snapshot read-only, restart staging `no`, 6 PAPER Falco + 2 PAPER Toro, entrambi fermi/in pausa, unità installate disabilitate/inattive, preview **non pubblica**.

## Evidenze cronologiche e correzioni

| Passaggio | Run | Esito |
|---|---|---|
| Inventario VPS pre-installazione | [#42367915858](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42367915858) | PASS |
| Prima installazione staging | [#42368212704](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42368212704) | FAIL **solo** per permessi statici (backend creato e attivo) |
| Correzione permessi *esclusivamente* asset statici staging | [#42368379447](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42368379447) | PASS; backend/SPA/produzione sani |
| Primo tentativo unità exit-only | [#42368682534](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42368682534) | FAIL perché Ubuntu senza `python3.12-venv`, unità non create |
| Installazione isolata dipendenze e unità DISABLED | [#42368895804](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42368895804) | PASS |
| Audit indipendente post-installazione | [#42369546234](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42369546234) | PASS |

Snapshot verificato degli storici da [PR #69](https://github.com/alexiptv82/SuperBot-Trading/pull/69): 38 file Falco + 36 Toro, SHA-256 integrali e prova restore isolata. Nessuna garanzia di backup esterno off-host.

## Gate aperti prima dell'uso su telefono

**La dashboard V3 non è ancora pubblicata sul normale dominio:** l'ambiente attuale non ha autenticazione integrata per una preview pubblica. **Non copiare DB di credenziali/sessioni o segreti dal web in produzione allo staging** solo per facilitarne l'accesso. Servono un percorso autenticato coerente e test di sicurezza, oppure un cutover della web app reale con backup del database applicativo e rollback provato.

L'installazione dei due worker **non significa che siano in esecuzione**: nessun clic del telefono può ancora chiudere le vecchie posizioni. Per il GO operativo restano:
1. Validare accesso/login sul percorso web V3 definitivo senza bypass e preservando sessioni, dati dell'app e rollback.
2. Promuovere frontend e backend V3 sul percorso autenticato con verifiche API end-to-end, precauzioni contro bot start/POST non previsti, configurazione Brain 2.000 USDT PAPER e tre wallet identici.
3. Solo dopo verifica web, attivare i due servizi exit-only mantenendo i motori classici fermi; ricontrollare snapshot SHA, pause, ownership e zero richieste pendenti.
4. Smoke test **su dati di test**, poi **solo l'utente** selezionerà e confermerà eventuali chiusure reali PAPER dalla dashboard. Registrare PnL netto, `closed_by=utente`, e esempio di profit-taking nel Journal/learning senza inventare promozione automatica strategica.
5. Dopo la conclusione, nuove run PAPER (Falco/Toro 1.000, Brain 2.000), storici legacy preservati. Nessun reset dello storage storico.

**Stato finale RC70: collaudo locale e unità inattive installati, NO-GO per pubblico/mobile, NO TRADES CLOSED, NO MERGE, NO BOT RESTART.**
