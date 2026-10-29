# Ritorno dei classici al codice del 13/10 (9fa667f) - ramo di lavoro, NESSUN deploy

Richiesta dell'utente (29/10/2026): riportare Falco (hawk) e Toro (bull) al comportamento del 13/10, quando le run
andavano bene, senza le correzioni anti-bias LONG/SHORT. Questo ramo prepara il ritorno e lo verifica in CI.
Non distribuisce nulla: il deploy richiede il via libera esplicito dell'utente (regola 1) e un suo trigger.

## Cosa cambia rispetto a rule-pool (c1a7c91)
* `backend/desk/{brain,cli,learning,notifier,signals}.py` = identici a 9fa667f.
* `backend/desk/engine.py` = 9fa667f + UN adattatore di sola lettura (`_known_fields`): il vecchio caricatore dello stato
  rifiuta i campi aggiunti dopo il 13/10 (provato: `Limits.__init__() got an unexpected keyword argument ...`).
  Nessuna decisione di trading cambia.
* Gli altri 66 file aggiunti dopo il 13/10 restano sul disco ma il vecchio codice non li importa.
* `.github/workflows/desk-deploy.yml`: (a) profilo `profile=legacy_13oct` nel file trigger, che salta SOLO i controlli
  Capitale V1 che il codice del 13/10 non puo' soddisfare; (b) la baseline attesa passa da 73e9242 a dc16e01, che e'
  cio' che gira davvero (la guardia fallisce comunque in modo sicuro se i sorgenti in esecuzione non corrispondono).
* `backend/tests_rollback_9fa/`: la suite del 13/10 (test_desk.py di allora) + test di compatibilita' dello stato.

## Parametri che tornano (dal codice di allora)
Falco: margine massimo 100$ per trade (forzato 60$ a leva 15, tipo scalp), 10 posizioni, budget 1000$.
Toro: 350$ per trade (minimo 150$, forzato 200$ a leva 15, tipo medio), 3 posizioni, budget 1050$.
Soglie 60 (BTC/ETH/oro/argento) e 70 (altre); stop giornaliero 12%, capitale minimo 450$.
Claude: finestre orarie da `claude_schedule.json` (budget 0,70$ a finestra per bot); senza file, budget giornaliero.
Non ci sono: DeepSeek, Salvadanaio, Capitale V1, filtro macro, anti-bias LONG/SHORT, opportunita' additive.
