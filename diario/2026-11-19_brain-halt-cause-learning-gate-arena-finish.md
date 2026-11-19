# Checkpoint SuperBot — causa arresto Brain verificata; gara da completare

**Data:** 19/11/2026, 06:47 Europe/Rome  
**Ambito:** sola documentazione; trading esclusivamente PAPER; storici ed EventJournal da preservare.

## Novità verificata dopo il checkpoint delle 05:46

### 1. Controllo VPS read-only: runner Brain fermo, servizio uscite sano

Due screenshot Termius delle 06:13 mostrano il controllo read-only dei servizi Brain storici:

- `superbot-v3-paper-brain-runner.service`: `Result=success`, `NRestarts=0`, `ExecMainStatus=0`, `ActiveState=inactive`, `SubState=dead`;
- `superbot-v3-paper-brain-exit.service`: `Result=success`, `NRestarts=1`, `ExecMainStatus=0`, `ActiveState=active`, `SubState=running`, attivo dal 19/11/2026 02:16:15 UTC (03:16:15 Europe/Rome);
- `heartbeat.json`: stato `halted`, errore `halted:exit_service_unhealthy`, run `brain-v3-paper20261111`, età circa 10.664 secondi al momento del controllo;
- `exit_heartbeat.json`: stato `healthy`, nessun errore, stessa run; heartbeat recente (circa 3,4 secondi), monitor circa 33,5 secondi;
- risultato del controllo: `EXIT_SERVICE_HEALTHY = True`, `CONTROLLO_COMPLETATO`.

Conclusione limitata: il runner Brain si è arrestato quando il servizio uscite risultava non sano; il servizio uscite è poi tornato attivo e sano, ma il runner è rimasto inattivo. Questo è stato verificato sul VPS tramite screenshot Termius. **Nessun restart è stato eseguito o autorizzato.**

Le 2 posizioni PAPER aperte mostrate nell'app al checkpoint precedente restano da proteggere tramite il servizio uscite; questo controllo non certifica che siano ancora identiche né sostituisce una lettura del journal.

### 2. Decisioni utente sulla ripresa e sulla gara

Messaggio utente delle 06:37 Europe/Rome:

- prima di far ripartire Brain, vuole verificare che lo storico dei trade venga realmente usato per imparare dagli errori e non ripetere gli stessi schemi perdenti;
- la gara AI Arena deve proseguire fino alla conclusione prevista;
- valutazione provvisoria: DeepSeek appare il migliore dei tre; MiniMax è giudicato non adatto al trading;
- allo stato attuale l'utente non intende usare gli altri due modelli come consulenti;
- possibile idea futura, non approvata né definita: test combinato DeepSeek + “Cloud” per contenere i costi. Il modello/fornitore indicato con “Cloud” non è stato specificato e non va sostituito per inferenza con Claude o altro.

La preferenza su DeepSeek è una valutazione utente provvisoria durante una gara non conclusa, non un risultato finale certificato.

## Apprendimento Brain: stato da verificare prima del restart

È confermata l'esistenza di journal e storico trade, ma in questo checkpoint non è stata eseguita una nuova verifica del codice/runtime che dimostri:

- quali risultati chiusi entrano effettivamente nel contesto decisionale;
- come vengono aggregate le perdite per strategia/simbolo/regime;
- se e quando una strategia perdente viene penalizzata o sospesa;
- se le chiusure manuali dell'utente producono evidenza di apprendimento;
- se esiste retraining del modello (non va assunto).

Pertanto “Brain conserva lo storico” non equivale a “Brain impara automaticamente e corregge gli errori”. Il restart resta **non approvato** finché non viene prodotto un audit read-only della catena journal → memoria/scoreboard → contesto decisionale → gate di rischio.

## Stato consolidato per la ripresa

- **Falco/Toro:** non rispondenti/ritirati nell'app; non riattivare, non resettare, preservare storici e SHORT Falco.
- **Brain storico:** runner inattivo/dead; servizio uscite attivo/running e heartbeat sano al controllo delle 06:13; ultimo heartbeat runner halted per `exit_service_unhealthy`. App mostrava 2 posizioni aperte e 96 chiuse alle 04:55.
- **Arena PAPER:** DeepSeek/Qwen/MiniMax devono continuare fino alla conclusione prevista, con T0 `1795021392344` e stop nuove inferenze/aperture previsto 21/11/2026 18:03:12 Europe/Rome. Non alterare T0, budget, journal o servizi.
- **Universo Arena:** resta aperto il gap “rank assoluto 1–25 + metalli idonei” contro “prime 25 crypto idonee”; serve leggere lo snapshot pinned della run.
- **PR #112:** open/draft, non mergiata, HEAD `86288a356209cef9264a369d24a2e8d7914c5ec2`, nessun nuovo commento.
- **RC84 PR #80:** open/draft, non mergiata, HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`.
- **Backup/chiavi:** age PC `ESITO: VERIFICA OK` con chiave pubblica coincidente, senza certificare VPS; `work/extbackup-bot-stopped-20261109` preparato ma non installato.

## Fatto / preparato / rilasciato / non approvato

- **Fatto:** controllo VPS read-only dei servizi Brain; causa di halt registrata; decisioni utente raccolte.
- **Preparato:** backup esterno non installato; eventuale test DeepSeek+Cloud è soltanto un'idea.
- **Rilasciato in precedenza:** dashboard/backend Arena read-only; nessuna nuova release.
- **Non approvato e non eseguito:** restart Brain, modifica apprendimento, cambio modelli, correzione universo, merge, deploy, Action, reset, ordine, chiusura automatica o API a pagamento.

## Blocker

1. Audit della reale catena di apprendimento Brain mancante.
2. Stato corrente delle 2 posizioni Brain da confermare read-only nel journal.
3. Snapshot universo Arena pinned non ancora letto.
4. Gara non conclusa: nessun vincitore definitivo.
5. Significato operativo di “Cloud” non definito.

## Prossimo passo sicuro

Prima di qualsiasi restart Brain:

1. audit read-only di journal, memoria/scoreboard e costruzione del contesto decisionale;
2. conferma read-only di posizioni, exit heartbeat e possibilità di gestione delle uscite;
3. produrre una tabella “desiderato vs implementato” sull'apprendimento, senza modificare codice o runtime;
4. lasciare Arena proseguire invariata e rinviare la scelta del modello alla fine della gara;
5. leggere lo snapshot universo Arena e verificare rank/simboli effettivi.

## Limiti

Screenshot Termius puntuali delle 06:13 e messaggio utente accessibile; nessuna sessione SSH autonoma o monitoraggio continuo. Nessuna trascrizione integrale di chat eliminate.
