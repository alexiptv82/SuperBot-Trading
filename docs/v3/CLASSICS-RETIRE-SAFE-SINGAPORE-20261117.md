# Falco e Toro — ritiro operativo autorizzato e reversibile (17-11-2026)

**Decisione utente:** Falco e Toro sono ora portafogli di archivio; l'operatività futura è Brain con tre AI. Conservare integralmente storia, configurazione e la strategia SHORT di Falco. Nessun reset di trade, nessun LIVE.

## Evidenza ottenuta sulla VPS

Alle 20:02 lo stato nei file `/opt/superbot-desk-data/{hawk,bull}/state_v2.json` indica, per entrambi, directory presente, `pause.flag` presente e `main.positions` vuoto (zero posizioni). I processi systemd `superbot-v3-paper-falco.service` e `superbot-v3-paper-toro.service` erano ancora active e usavano `desk.cli loop --portfolio hawk/bull`.

**Diagnostica aggiuntiva delle 20:58:** il processo Falco (`DESK_MODE=paper`) usa in realtà `/opt/superbot-v3-paper-runs/classic-hawk-paper20261111`; Toro usa `/opt/superbot-v3-paper-runs/classic-bull-paper20261111`. Le cartelle `/opt/superbot-desk-data/{hawk,bull}` sono **storiche**. Il primo tentativo di ritiro è stato rifiutato correttamente: `FALCO_DATA_PATH_OR_PAPER_MODE_UNVERIFIED`. La versione aggiornata del file di ritiro ora controlla i dati **effettivi**, conserva un backup pre-stop della loro storia e un backup post-stop **sia dei due runtime sia dei due archivi storici**.

**La presenza di zero posizioni nelle due cartelle storiche non prova ancora zero posizioni nei runtime reali**: il codice aggiornato deve trovare `pause.flag` e `state_v2.json` con `main.positions={}` in entrambe le cartelle reali **prima** di fermare qualsiasi servizio. Se questa verifica fallisce, lo script deve rifiutare.

`RUN_CLASSICI_TROVATE=0` era un controllo sullo schema V3 errato e non autorizza lo stop.

## Procedura predisposta sul ramo della PR #106

File: `deploy/scripts/classic-paper-retire-preserve-20261117.py`.

Invocare esclusivamente come root con `--retire`. Usa solo stdlib Python + systemd installato, nessuna rete/chiave/provider. Fino al completamento della **copia pre-stop** effettua soltanto letture e scritture nel nuovo archivio root:0700, non tocca nessun servizio. Ogni condizione anomala rifiuta l'intervento:

1. Verifica Brain storico: unità `superbot-v3-paper-brain-runner.service` e `superbot-v3-paper-brain-exit.service` devono restare active.
2. Verifica che i processi reali delle due unità classiche siano `desk.cli loop` per il portafoglio giusto, in PAPER, con `DESK_DATA_DIR` esattamente `/opt/superbot-desk-data/hawk` o `bull`. Blocca eventuali container legacy `superbot-desk-hawk/bull` ancora attivi.
3. Verifica `pause.flag` e `state_v2.json` reale/non symlink, struttura `main.positions` e zero posizioni aperte per entrambi.
4. Crea un archivio privato e copia pre-stop verificata SHA-256 di stato, trade history, learning log, lessons, errors, flag e file disponibili. Salva la definizione systemd originale. Verifica che PID, stato e posizioni non siano cambiati.
5. Solo dopo, `systemctl disable --now` applicato **soltanto** ai quattro servizi classici esatti: runner Falco/Toro ed exit-only Falco/Toro (questi ultimi risultavano già `failed`). Non disabilita web, bridge, Telegram, Brain o Arena.
6. Crea un tar completo post-stop delle due directory dati, prova di lettura dell'archivio e SHA-256. Conferma che i due servizi Brain siano ancora active. Non cancella né ricrea nessun file originale.

**In caso di rifiuto:** non forzare lo spegnimento manuale, non cambiare env a tentativi; acquisire esclusivamente la riga `CLASSIC_RETIRE_REFUSED=...` e riesaminare. In caso di errore **dopo** `STOPPED_DISABLED`, non cancellare backup: i servizi classici possono già essere disattivati, da verificare con `systemctl is-active/is-enabled`.

La strategia SHORT è già referenziata dal ramo GitHub `archive/falco-short-before-ai-arena-20261116` sullo SHA `fed2e3fd32ff162d22b045b4a8e5f0524e88a9b7`. Questo NON sostituisce i backup VPS di stato, che vengono creati dalla procedura.

**Stato alla stesura:** script salvato e da eseguire tramite Termius su VPS Singapore. Non è stato eseguito né testato sul target da ChatGPT; solo lo screenshot dell'inventario e delle posizioni è verificato. I servizi classici NON sono ancora stati spenti.

**Versione aggiornata:** commit `0519858d14cad3fad759c4248dcf00233ef55cce`. Prima di usarla, verificarne sintassi e percorsi e NON ripetere lo script vecchio al commit `f0bc3970`. A oggi non è stato eseguito alcun ritiro completo.
