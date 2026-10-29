# Ritorno dei classici al codice del 13/10 (9fa667f) — fatto e deployato, bot in pausa — 29/10/2026 (Claude)

## Decisione dell'utente (chat del 29/10, 11:37 e 11:57)
Dopo le perdite di ieri (Falco/Hawk run 7, Toro/Bull run 6) l'utente ordina di riportare i classici **al codice letterale del 13/10** (`9fa667f`, "come era quel giorno che lavorava bene"), con: Claude **4 ore a finestra** (come allora), **niente DeepSeek**, **niente fix del bias LONG** (da rivedere dopo), merge in `rule-pool`, **deploy vero con backup verificato**, **portafogli riportati a 1000$ ciascuno prima del deploy**, e **l'avvio lo preme lui** dall'app. I nomi Falco/Toro: solo etichette, si cambiano dopo.

## Cosa è stato fatto
1. Ramo `work/ritorno-9fa667f-claude-20261029` (base `c1a7c91`): `backend/desk/{brain,cli,learning,notifier,signals}.py` **identici** a 9fa667f; `engine.py` = 9fa667f + un solo adattatore di sola lettura (`_known_fields`) che ignora i campi sconosciuti quando legge uno stato scritto dal codice più recente (senza, il vecchio caricatore va in TypeError). Nessuna decisione cambia. Test: suite del 13/10 copiata in `backend/tests_rollback_9fa/` + prova che lo stato scritto dal codice attuale si legge e che i limiti vengono dal codice (Falco 100$/10 slot/1000, Toro 350$/3 slot/1050, daily stop 12%, kill equity 450). CI del ramo: **86 test passati**, immagine costruita, perimetro verificato (`deploy/ritorno-9fa667f/`).
2. Merge **fast-forward** in `rule-pool` → `0ad6893` (nessun force push, `work/backend-singapore-audit` non toccato).
3. `desk-deploy.yml`: `CURRENT_PAPER_BASE` e controllo versione portati da 73e9242 a **dc16e01** (il runtime che c'era), nuova riga trigger `profile=legacy_13oct` che salta SOLO i due controlli Capitale V1/Salvadanaio (il codice del 13/10 non li ha). Tutto il resto resta: paper, backup verificato, una sola istanza per bot, versione dichiarata.
4. `desk-ci.yml`: il passo con i test lunghi delle versioni successive è sostituito dalla suite del 13/10 + compatibilità dello stato. I test delle funzioni rimosse (Capitale V1, Salvadanaio, DeepSeek, macro, orari, anti-bias) restano nel repository ma non girano in `desk-ci`.
5. Nuovo workflow `desk-reset-portfolios.yml` (trigger `deploy/desk-reset-portfolios.trigger`: `confirm=paper-reset-1000`, `bots=...`, opzionale `dry_run=1`): controlla paper/container/pausa/nessun comando pendente, copia lo stato, chiude le posizioni, azzera, verifica che il cervello non sia diminuito, pubblica il resoconto come annotazione. Il primo tentativo è stato **rifiutato dal bot** ("reset Salvadanaio richiede conferma esplicita"): nessuna modifica; il comando ora porta `{"reset_vault": true}`.
6. **Reset eseguito** (run 40865230953): Falco run 7→8, Toro run 6→7, conto 1000.00$ ciascuno, nessuna posizione, entrambi in pausa. Copie di sicurezza dello stato in `/opt/superbot-backups/pre-reset-20261029-112517` (e `-112403` del tentativo rifiutato). Run precedente archiviata dal bot (Salvadanaio compreso, ora a zero).
7. **Deploy** (run 40865549823, trigger `765fd44`): `sha=0ad68935c1ec12e514a1652f6a43d09d4a23aa75`, `profile=legacy_13oct`, `capital=off`, `deepseek=off`; backup verificato del cervello prima della sostituzione; immagine precedente tenuta come `superbot-desk:rollback-<data>`. Esito: successo.
8. **Calendario di Claude**: `deploy/claude-schedule.json` ora ha tre finestre da 4 ore come il 13/10 (gio 29/10 14:30-18:30, ven 30/10 00:00-04:00, sab 31/10 08:00-12:00, ora svizzera, 0,70$ per finestra e bot); i bot lo leggono (verificato). Le vecchie finestre da 8 ore (14-22) sono state sostituite.

## Stato di arrivo (verificato in sola lettura dopo il deploy)
Falco run 8 e Toro run 7: conto 1000.00$, **in pausa**, PAPER, versione `0ad6893`, 0 riavvii del container, battito fresco. Cervello (storico trade, appunti, registro di apprendimento) intatto: stesse dimensioni prima e dopo il reset. **Nessuno ha premuto Avvia: lo fa l'utente dall'app.**

## Da sapere (ChatGPT e chi prosegue)
- **Il controllo di baseline di `desk-deploy.yml` ora blocca qualunque deploy futuro** finché non si aggiorna: pretende che il runtime dichiari `dc16e01`, ma il runtime è `0ad6893`. Prima del prossimo deploy: aggiornare `CURRENT_PAPER_BASE` e il test di versione al nuovo SHA (o decidere un'altra regola) con OK dell'utente.
- La vista Salvadanaio sparisce dai bot (il codice del 13/10 non ha il vault); i giornali restano su disco. Alcuni campi della dashboard per le funzioni nuove possono essere vuoti.
- Limiti attuali: Falco max 100$/trade, Toro 350$/trade con 3 slot. Niente DeepSeek, niente Capitale V1.
- Il Brain Scalp è un altro componente (ChatGPT): non toccato; i suoi nomi restano suoi.
- Il laboratorio delle uscite (ramo `work/classics-exit-lab-claude-20261029`, solo lettura, nessun file di produzione) è disponibile: vedere `backend/exit_lab_claude/results/report.md`.

## Aperto
Rinominare Hawk→Falco e Bull→Toro come etichette (solo app/Telegram, nessuna cartella o container); rivedere e reintegrare il fix del bias LONG; laboratorio di strategie nuove (obiettivo dell'utente: giorni buoni da ~100$, senza perdere la base); latch sullo stop giornaliero legacy; log VPS del 29/10.

AI: claude
