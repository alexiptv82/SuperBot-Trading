# Checkpoint verificabile — SuperBot-Trading

**Data:** 18/11/2026, 15:51 Europe/Rome  
**Tipo:** delta append-only rispetto ai checkpoint delle 13:53 e 14:48. Questa esecuzione modifica solo documentazione.

## Novità verificate

### 1. Sostituzione auditabile delle tre run PAPER completata

Il commento [PR #110 delle 14:58 circa](https://github.com/alexiptv82/SuperBot-Trading/pull/110#issuecomment-6980732437), basato su screenshot Termius delle 14:57, registra l'esecuzione tramite unità transiente systemd del wrapper pinnato a `3dd6aa588339c6136d52e9ff027c91e5e3f80377`:

- zero posizioni verificato prima dell'operazione;
- vecchie run archiviate in una nuova directory di backup e stage precedente conservato;
- tre nuove run preparate in `PREPARED_PAUSED_NO_T0`;
- risultato `PREPARED_RUNS_REPLACED_EXITS_HEALTHY`;
- tre exit-worker DeepSeek/Qwen/MiniMax attivi;
- `T0_ASSIGNED=FALSE`, `RUNNERS_STARTED=FALSE`, `PAID_INFERENCE=FALSE`;
- bridge e Brain storico dichiarati non toccati dallo script.

È avanzamento VPS realmente eseguito e documentato tramite screenshot/commento, ma questo checkpoint non ha accesso SSH indipendente. Non ripetere la sostituzione.

### 2. Smoke PAPER con feed Bitget reale completato senza crediti AI

Il commento [PR #110 delle 15:08 circa](https://github.com/alexiptv82/SuperBot-Trading/pull/110#issuecomment-6980981924) registra il completamento e la disattivazione corretta della unità smoke:

- trasporto modello finto `NO_TRADE`, nessuna chiave/inferenza AI;
- Qwen: 27 simboli, 27 decisioni e 27 model call simulate, zero aperture, zero errori, stato `running`;
- un altro provider visibile solo parzialmente mostrava 27 simboli e zero errori, ma non è identificabile con certezza;
- risultato generale `real_runs_stage_after=PREPARED_PAUSED_NO_T0` e `real_runs_untouched=true`;
- la parte alta del JSON non è visibile nello screenshot: non promuovere a prova completa i dettagli DeepSeek/MiniMax o il campo `network_ai_calls`, pur essendo lo smoke progettato senza chiamate AI.

### 3. Credenziali OpenRouter diagnosticate, quote ancora da riverificare

Il commento [PR #110 delle 15:37 circa](https://github.com/alexiptv82/SuperBot-Trading/pull/110#issuecomment-6981703048) documenta senza mostrare segreti:

- file OpenRouter, schema, base URL, permessi, modelli e due chiavi distinte: OK;
- Qwen e MiniMax: validazione locale OK e OpenRouter raggiungibile;
- entrambe le chiavi risultavano `LIMITE_6_USD=NON_CONFORME` al momento del test.

Uno screenshot successivo accessibile mostra la schermata OpenRouter della chiave MiniMax con limite 6 USD, reset `N/A` e spesa 0 USD; il messaggio utente `fatto✅` non contiene un riscontro tecnico post-salvataggio. Non è quindi ancora verificato tramite API che MiniMax, e soprattutto Qwen, abbiano entrambi `limit=6`, nessun reset e residuo sufficiente. Non sono state eseguite inferenze a pagamento.

## Stato consolidato per la ripresa

- **Falco/Toro/Brain storici:** Falco e Toro ritirati/archiviati ma conservati; SHORT Falco, trade, storici ed EventJournal intoccabili. Brain storico resta separato dall'Arena.
- **AI Arena:** DeepSeek/Qwen/MiniMax, solo PAPER, 27 mercati, stessa baseline/risk policy, screening 72 ore. Le tre run sono ora sostituite e nuovamente preparate in pausa; T0 assente e runner decisionali non avviati.
- **Budget:** massimo desiderato 18 USD, 6 per provider e 2/giorno. Qwen/MiniMax richiedono verifica remota finale dopo configurazione. DeepSeek resta limite interno con margine, non hard cap lato provider; non ridurre il saldo condiviso col Brain storico.
- **App e chiusura manuale:** ancora bloccate. Il container produzione non monta il socket Arena e non abilita le route/flag; Samsung manual close, GET Arena autenticato e apprendimento dalle chiusure non sono certificati.
- **Memoria:** journal/run preservati; la memoria finale condivisa che apprende dai tre portafogli e dai motivi umani non è ancora dimostrata operativa.
- **Backup:** vecchie run e stage archiviati durante la sostituzione; backup locale precedente verificato. Nessuna nuova prova di copia esterna. Age PC `ESITO: VERIFICA OK`/chiave pubblica coincidente non certificano VPS. `work/extbackup-bot-stopped-20261109` resta preparato e non installato.
- **GitHub:** PR #110 ancora draft a `3dd6aa588339c6136d52e9ff027c91e5e3f80377`; 1.028 test locali riportati PASS + 2 fallimenti di base. RC84 PR #80 invariata a `0e29a73a36f668643da4088178bacb8616a45ac0`.

## Fatto / preparato / rilasciato

- **Fatto su VPS, da prova screenshot/commento:** sostituzione delle tre run con archiviazione e uscite sane; smoke Bitget/fake-NO_TRADE completato; diagnosi non sensibile delle chiavi OpenRouter.
- **Preparato ma non rilasciato:** candidato web isolato/rollback, mount socket e journal, API read-only, manual close Samsung, trainer fixes e memoria finale.
- **Rilasciato:** nessun T0, runner decisionali Arena, inferenza pagata, ordine LIVE, merge o nuova immagine web in produzione.
- **Non approvato:** avvio gara, ricreazione/switch del container produzione, modifica Brain storico, saldo DeepSeek, estensione oltre 72 ore o ripetizione replace/smoke.

## Blocker e prossimo passo

1. Verificare con controllo booleano/non sensibile che entrambe le chiavi OpenRouter dedicate abbiano limite 6 USD, nessun reset e residuo sufficiente; il solo `fatto✅` non basta.
2. Preparare e testare un candidato web su porta loopback alternativa, preservando immagine, binding, mount, auth/login/impronta e vecchio bridge; nessun cambio alla produzione prima degli smoke.
3. Certificare sessione negata/positiva, GET Arena read-only e status bridge; test manual close reale solo con consenso separato.
4. Risolvere gate trainer/gestione e controllo DeepSeek, poi preflight finale. Solo una nuova autorizzazione esplicita può assegnare T0 e avviare i tre runner PAPER.

## Istruzioni di ripresa e limiti

Leggere questo delta dopo i checkpoint 13:53 e 14:48, poi gli ultimi commenti della PR #110. Non ripetere `--replace-prepared` o lo smoke già concluso. Conversazioni accessibili solo come estratti e immagini; nessuna trascrizione integrale di chat eliminate. Nessun accesso SSH live in questa esecuzione.
