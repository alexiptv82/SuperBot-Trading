# Checkpoint verificabile — 13/11/2026 23:51 Europe/Rome

## Esito sintetico

Novità verificata: **Brain PAPER è stato rimesso in pausa**; un ramo separato contiene una correzione candidata per rendere fail-closed il monitor uscite quando il feed 1m è vuoto, incompleto o obsoleto. La correzione è **preparata ma non installata** e non esiste prova accessibile di una suite pytest completata sul nuovo HEAD. Nessun PR, merge, deploy, GitHub Action, restart o ordine è stato eseguito da questo checkpoint.

## Fonti e limiti

- GitHub: ramo `diario`, `STATO.md`, PR/commit recenti e ramo `work/brain-exit-observability-20261113`.
- Conversazioni recenti effettivamente accessibili e screenshot Termius forniti dall'utente; non sono disponibili trascrizioni integrali delle chat perse.
- Nessun accesso SSH indipendente o controllo VPS live è stato eseguito in questo checkpoint. Gli screenshot attestano soltanto l'output mostrato all'ora indicata.
- Library `ULTIMO-STATO-SUPERBOT.md` v96 letta prima dell'aggiornamento.

## Brain — fatto, preparato, rilasciato

### Fatto e verificato

- Decisione utente: accettata la pausa Brain per bloccare nuove aperture.
- Screenshot Termius delle 23:31 CET: `PAUSA=ATTIVA`, runner `active`, servizio uscite `active`, stato uscite `healthy`, `ERROR: None`, heartbeat 0,6 s.
- Il dato `healthy`/heartbeat prova attività del processo nel momento osservato, **non** prova copertura completa del feed, valutazione di ogni stop, redditività o stato continuativo.
- Screenshot read-only delle 23:08–23:11 mostrano un controllo delle candele attorno a stop PAPER, inclusi casi con minuto finale mancante e confronto tra primo attraversamento dello stop e fill. È diagnostica puntuale, non certificazione generale delle uscite.

### Preparato su GitHub, non eseguito/installato

- Ramo: `work/brain-exit-observability-20261113`.
- HEAD verificato: [`4efd1a31051dd023480d4d9a327016ae9a6f9a0e`](https://github.com/alexiptv82/SuperBot-Trading/commit/4efd1a31051dd023480d4d9a327016ae9a6f9a0e), commit “Fix isolated test harness: ephemeral pinned pytest, never modify Brain venv [skip ci]”.
- Modifiche candidate:
  - monitor uscite segnala `exit_feed_incomplete` con posizione aperta e copertura 1m vuota, stantia o con buchi;
  - prezzo dell'ultimo minuto rifiuta una barra non immediatamente precedente;
  - otto test sintetici dedicati coprono feed vuoto, minuto d'apertura parziale, ultimo minuto mancante, buco interno, copertura completa, stop prima di un gap e prezzo 1m stale/fresco;
  - harness isolato con blob pinning e pytest 8.4.2 temporaneo; dichiara di non modificare il venv Brain.
- Non c'è PR associata trovata né prova accessibile di esecuzione completata della suite sul HEAD `4efd1a3…`. Il file di test contiene otto casi, ma “otto test preparati” non equivale a “otto test PASS”.
- Nessuna installazione nello stage/VPS, nessun restart, nessun unpause e nessuna modifica di rischio/configurazione sono attestati.

### Rilasciato

- Nulla.

## Stato desiderato versus implementato

- **Desiderato:** uscite Brain fail-closed quando le candele 1m non coprono integralmente i minuti eleggibili; prezzo operativo sempre fresco; pausa mantenuta finché test, review e installazione separata non siano autorizzati.
- **Implementato nel runtime:** non verificato; l'ultimo runtime osservato resta quello precedente, con la nuova pausa attiva. La patch esiste soltanto sul ramo di lavoro.
- **Rischi/configurazioni:** nessuna variazione verificata a capitale, leva, sizing, stop, TP, budget AI o Guardian. L'audit precedente resta NO-GO alla certificazione delle uscite e dell'edge.
- **Conteggi operativi:** non si registrano come verificati conteggi di cicli, decisioni, approvazioni, posizioni o PnL non accompagnati da fonte primaria accessibile.

## Tre portafogli PAPER

- **Brain:** in pausa per nuove aperture al controllo delle 23:31; runner ed exit sidecar attivi. Patch osservabilità solo preparata.
- **Falco:** congelato, nessuna riattivazione verificata.
- **Toro:** sospeso. PR #99 resta NO-GO strategico (361 trade, media −32,455 bp, PF 0,5938, DD close-only 89,73%, 1/8 gate); nessuna promozione o integrazione.

## Commit, rami, PR e test

- `work/brain-exit-observability-20261113` HEAD `4efd1a31051dd023480d4d9a327016ae9a6f9a0e`.
- Nessuna nuova PR trovata dopo il checkpoint delle 22:44.
- Test del ramo: otto casi dedicati presenti nel sorgente; esecuzione/PASS **non verificati**.
- RC84 [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta riferimento storico, non prova di questo cambiamento e non autorizza deploy.

## Backup, chiavi e conservazione

- Verifica PC della copia cifrata age: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente. Non certifica presenza, integrità o restore del backup sulla VPS.
- `work/extbackup-bot-stopped-20261109`: preparato, non installato.
- Solo PAPER. Storici ed EventJournal devono restare intatti; nessun reset.
- Nessun segreto, chiave privata, passphrase, token o dettaglio d'accesso è riportato.

## Problemi e blocker

1. Patch candidata non ancora testata con risultato completo verificabile sul suo HEAD.
2. Nessuna review/PR dedicata e nessuna prova di compatibilità con lo stage Brain installato.
3. Lo stato `healthy` attuale non distingue ancora, nel runtime attestato, attività del processo da copertura effettiva del feed.
4. Stato VPS successivo agli screenshot e risultati economici Brain non verificati.

## Prossimo passo di ripresa

1. Mantenere Brain in pausa e non avviare istanze concorrenti.
2. Verificare il ramo e i blob esatti; eseguire soltanto, con autorizzazione operativa separata, il test isolato pinned e conservare output completo, conteggio test, exit code e prova `stage_unchanged/pause_preserved`.
3. Se e solo se la suite passa, aprire/revisionare una PR Draft circoscritta; non installare senza nuovo consenso e piano rollback.
4. Dopo eventuale installazione separatamente autorizzata, dimostrare feed vuoto/incompleto → degraded, feed completo → healthy e stop idempotente, preservando journal/storici.
5. Non riattivare Falco/Toro e non dedurre edge o redditività dai soli test sintetici.

## Vincoli invariati

Solo documentazione in questo checkpoint. Nessun merge, deploy, GitHub Actions, VPS, reboot, restart, reset, ordine, wallet o API a pagamento. Trading esclusivamente PAPER; storici ed EventJournal preservati.
