# Checkpoint verificabile — hotfix Brain installato; preflight E2E isolato PASS; Brain ancora PAUSED

**Data:** 13/11/2026 14:44 Europe/Rome  
**Ambito di questo checkpoint:** sola documentazione. Le modifiche VPS qui registrate sono state eseguite dall'utente in Termius dopo autorizzazione esplicita, non da questa automazione.

## Sintesi per la ripresa

L'hotfix Brain-only dei due moduli dati Bitget è stato installato sulla VPS con backup e rollback verificati, riavviando soltanto runner ed exit Brain e mantenendo `pause.flag`. Subito dopo, il preflight isolato ha completato il percorso feed Bitget → DeepSeek → decisione Brain → journal temporaneo con esito `NO_TRADE`, senza ordine né apertura nel portafoglio operativo.

**Stato corrente verificato:** hotfix installato, feed/contratti e preflight E2E isolato PASS; Brain resta PAUSED, zero posizioni aperte. L'unpause non è autorizzato dal consenso al deploy e richiede una decisione separata.

## Fonti e limiti

Fonti primarie:
- [Issue #95 — deploy hotfix PASS](https://github.com/alexiptv82/SuperBot-Trading/issues/95#issuecomment-6854603469);
- [Issue #95 — preflight E2E isolato PASS](https://github.com/alexiptv82/SuperBot-Trading/issues/95#issuecomment-6854682127);
- installer/documentazione pinned [`e9f7710908cf0fb4fdf31c6ac1bdb66316c2a702`](https://github.com/alexiptv82/SuperBot-Trading/commit/e9f7710908cf0fb4fdf31c6ac1bdb66316c2a702).

I risultati VPS derivano dagli output Termius mostrati dall'utente e trascritti nell'Issue. Questo checkpoint non ha accesso SSH autonomo e non assume stato successivo.

## Deploy limitato Brain — PASS verificato

Autorizzazione utente verificata: installare **solo** i due fix Bitget Brain, con backup/rollback, mantenendo Brain in pausa e Falco/Toro intatti.

Output registrato:

- preflight: stage `0e29a73a36f668643da4088178bacb8616a45ac0`, pausa presente, zero posizioni, exit healthy, journal integrity OK;
- codice scaricato e sintassi verificata;
- backup privato verificato e da conservare; nessun restore distruttivo eseguito;
- installazione PASS con esattamente due file modificati:
  - `backend/v3/runner/contracts.py`;
  - `backend/v3/lab_tools/fetch_candles.py`;
- Git HEAD resta `0e29a73…`; worktree intenzionalmente dirty per **esattamente due file**;
- riavviati soltanto exit e runner Brain;
- controllo finale: exit healthy, heartbeat runner paused, journal integro, zero posizioni;
- risultato: hotfix Brain installato, `pause=1`, `open_positions=0`.

Nessuna modifica a mandato, policy, rischio, AI config, chiavi, classici, frontend/API, LIVE o GitHub Actions. Nessun merge.

## Preflight Brain E2E isolato — PASS verificato

Eseguito dopo l'installazione con lo script pinned `v3-brain-paper-preflight-readonly.sh`:

- exit service healthy;
- journal integrity/chain OK;
- chiave DeepSeek presente verificata solo come booleano;
- contratti Bitget **8/8**, nessun simbolo mancante;
- DeepSeek reale:
  - HTTP 200;
  - modello `deepseek-flash`;
  - `finish_reason=stop`;
  - JSON valido;
  - reasoning presente;
  - 8,7 secondi, entro timeout produzione 30 s;
  - 3.040 token totali, di cui 1.391 reasoning;
  - decisione `NO_TRADE`;
- ciclo isolato:
  - `state=running`, `last_error=None`;
  - decisione BTCUSDT `NO_TRADE/DRAFT` da `deepseek:analysis`;
  - zero aperture, zero errori;
- journal e budget della run operativa invariati;
- `pause.flag` ancora presente.

La prova riguarda BTCUSDT e journal temporaneo, **non tutti gli otto simboli**. Dimostra il percorso feed→AI→decisione→journal isolato, non una proposal OPEN, un'apertura operativa, TP/SL live o redditività. `NO_TRADE` è esito valido e non va forzato.

## Portafogli PAPER

- **Brain:** 2.000 USDT; floor/gate 450; leva 20–50×; ciclo 60 minuti; cap DeepSeek 0,75 USD/giorno; rischio massimo ingresso circa 4,29% (~86 USDT) e open risk 12% (~240 USDT). Hotfix installato ed E2E isolato PASS; resta PAUSED e senza posizioni.
- **Falco:** strategia SHORT originale congelata e non toccata.
- **Toro:** LONG/Twin sospeso; non toccato.
- PR #92/#93/#94 restano non operative; RC84 PR #80 resta riferimento storico.

Il valore 450 e i daily-loss gate (35% avviso, 50% blocco) non garantiscono matematicamente un pavimento sotto shock o esposizioni già aperte.

## Eseguito / preparato / rilasciato

- **Eseguito:** test Bitget VPS su file isolati; autorizzazione; backup; installazione dei due moduli; restart coordinato solo Brain in pausa; verifica salute; preflight E2E isolato DeepSeek.
- **Rilasciato sulla VPS:** esclusivamente i due moduli dati Brain, come modifica del worktree dello stage esistente.
- **Preparato:** rollback privato e gate per eventuale unpause.
- **Non eseguito/non approvato:** rimozione pausa, apertura PAPER operativa, test OPEN reale, modifica rischio/config, merge, Actions, reset, LIVE, Falco/Toro.

## Backup e chiavi

- Backup privato dell'installazione Brain creato e verificato; conservarlo, non cancellarlo. Non è certificato qui un restore completo.
- Backup esterno `work/extbackup-bot-stopped-20261109`: preparato ma non installato.
- Copia cifrata della chiave age sul PC: PowerShell `ESITO: VERIFICA OK`, chiave pubblica coincidente; non certifica backup/restore VPS.
- Nessuna chiave privata, passphrase, token o dettaglio d'accesso è riportato.

## Blocker e prossimo passo

1. Prima di qualsiasi unpause: checkpoint live di mandato approved/policy hash, run-id, servizi/exit healthy, pausa presente, journal chain e zero posizioni.
2. Richiedere autorizzazione **separata** per rimuovere esclusivamente `pause.flag` Brain.
3. Se autorizzato in futuro, monitorare il primo ciclo operativo: feed, decisione AI, eventuali rifiuti risk, costi, leve e stop; `NO_TRADE` resta valido.
4. In caso di anomalia: ripristinare/mantenere pausa, conservare uscite attive, nessun reset del journal; valutare rollback dei due file.
5. Non toccare Falco/Toro; preservare storici ed EventJournal.

## Limite conversazioni

Sono stati utilizzati solo messaggi recenti effettivamente accessibili e riscontri GitHub. Non si presume accesso a chat eliminate o trascrizioni integrali.
