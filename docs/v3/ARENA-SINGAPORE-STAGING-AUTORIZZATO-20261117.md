# AI Arena — PREPARAZIONE autorizzata VPS Singapore, nessuna inferenza / run (17 novembre 2026)

**Autorizzazione esplicita dell'utente:** Falco e Toro sono già in pausa. Autorizzata la **preparazione** della nuova AI Arena sul VPS Singapore, mantenendo tutto PAPER e senza avviare i 14 giorni, chiamate AI a pagamento, servizi runner o modifiche agli operatori storici.

**Limite operativo di questa sessione:** ChatGPT può leggere/scrivere GitHub, ma non ha un collegamento SSH diretto al VPS Singapore. Questo file descrive **una procedura predisposta**, non certifica che l'installazione VPS sia avvenuta.

## Script conservativo, sorgente con SHA bloccato

`deploy/scripts/arena-vps-stage-paused-only-20261117.sh` nel ramo `work/arena-vps-stage-paused-only-20261117`.

Lo script usa **esattamente** la revisione `48dc07494345fe9d973b900b67cd094cec56e7e5` della PR #102 (non HEAD mobile); se GitHub espone un commit diverso, si blocca lasciando lo stage temporaneo per ispezione. Il repository è pubblico; non prevede l'uso di token GitHub sul server.

La modalità `--inspect` è sola lettura (stato servizi storici, esistenza percorsi, commit dello stage). La modalità `--stage` necessita utente root e:

1. Rifiuta target inattesi, permessi differenti da root:0700 e symlink; mai sovrascrivere uno stage con un commit diverso.
2. Clona **in una nuova cartella** il codice della PR #102 e verifica l'SHA prima di collocarlo in `/opt/superbot-arena-stage`.
3. Prepara soltanto le directory proprietario root `0700` sotto `/opt/superbot-ai-arena-paper/{deepseek,qwen,minimax}`.
4. Se è disponibile un interprete Python **già presente** e compatibile sul VPS, prova a importare il preflight offline delle tre config (27 simboli, rischio uguale, stesso capitale) usando il codice del nuovo stage. In caso contrario lo segnala e si ferma alla preparazione dei sorgenti. Non aggiorna né installa pacchetti.
5. Non modifica systemd, Docker, variabili web, API keys, conti, journal, mandati, servizi preesistenti o dashboard Samsung. Non genera nemmeno una `trial_start_ms` provvisoria: così il test ufficiale dei 14 giorni avrà un T0 deciso al suo reale avvio.

**Attenzione:** *tre cartelle provider predisposte* NON equivalgono a tre run PAPER avviate/in pausa. In questa fase non ci sono run reali, quindi lo stato della dashboard resterà `not_started`, non un falso `running`.

## Esecuzione in Termius (solo sulla VPS SuperBot Singapore)

Non eseguire in altri VPS (es. HiTV). Sostituire `<SCRIPT_COMMIT>` con il commit dello script dopo il suo push:

```sh
curl -fsSL 'https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/<SCRIPT_COMMIT>/deploy/scripts/arena-vps-stage-paused-only-20261117.sh' -o /tmp/arena-stage.sh
bash -n /tmp/arena-stage.sh
if [ "$(id -u)" -eq 0 ]; then bash /tmp/arena-stage.sh --stage; else sudo bash /tmp/arena-stage.sh --stage; fi
```

Il percorso è bloccato a un commit. Non usare pipeline di esecuzione diretta `curl | bash`, non copiare chiavi e non eseguire `systemctl start` o `docker compose up` in questa fase.

## Report che si deve ricevere

Attesi `SOURCE_STAGED_COMMIT=48dc0749...`, `THREE_PROVIDER_PARENTS_PREPARED=TRUE`, `NO_TRIAL_T0_OR_RUN_JOURNALS_CREATED=TRUE`, `STAGE_COMPLETE_ALL_RUNNERS_NOT_STARTED=TRUE`. Il preflight può stampare `SKIPPED_NO_COMPATIBLE_EXISTING_VENV`: non indica uno stage fallito, ma la necessità di preparare un venv isolato prima dei servizi.

L'utente potrà inviare soltanto le righe `ARENA_STAGE` (non log sensibili) per completare gli step di prova su VPS. Restano da fare dopo lo staging: verifiche runtime, backup storico DeepSeek Issue #101, venv stage, tre run PAPER con T0 comune, exit-worker, bridge host, web e test Samsung. L'avvio a pagamento richiederà ulteriore decisione sul budget.

**Rollback di questa fase:** non si devono fermare i servizi storici. Non fare `rm -rf` neanche sullo stage: il solo codice nuovo rimane inattivo, le cartelle vuote sono innocue. Nessun reset della memoria.

## Regola importante sulle uscite

Quando l'Arena aprirà in seguito posizioni PAPER, si potrà mettere in pausa le **nuove aperture** ma gli exit-worker dovranno rimanere attivi finché le posizioni aperte non saranno chiuse/verificate. La procedura del progetto che suggerisce di fermare gli exit-worker subito dopo i runner non è sicura con posizioni aperte.
