# Checkpoint verificabile — roadmap Brain unico, continuità storica e collaborazione Work/Cloud

**Data:** 19/11/2026, 07:47 Europe/Rome  
**Tipo:** delta append-only rispetto al checkpoint delle 06:47.  
**Ambito:** sola documentazione; trading esclusivamente PAPER.

## Fonte e limite di accesso

- GitHub verificato sul ramo `diario`: HEAD iniziale `00d88a126c71739044eb26970a342508410c2b90`; `STATO.md` indicizzava il checkpoint delle 06:47.
- Library verificata: `ULTIMO-STATO-SUPERBOT.md`, v112, `file_00000000a24881f5956061a69ae67b5a`.
- Conversazioni recenti: accessibili soltanto come estratti indicizzati e come messaggio recente del progetto, non come trascrizione integrale. Le decisioni sotto sono riportate senza estenderne l'autorizzazione.
- Nessun controllo live VPS eseguito in questo checkpoint.

## Novità verificate: decisioni e roadmap

L'utente chiede di iniziare subito la **preparazione** del nuovo progetto del **Brain unico** mentre la gara/training Arena prosegue senza interventi. Requisiti e decisioni verificabili:

1. collaborazione tra ChatGPT Work e Cloud per distribuire il lavoro e mitigare i rispettivi limiti d'uso;
2. desiderio di un agente Cloud dedicato e di istruzioni/prompt ripetibili, ancora da progettare;
3. accesso futuro alla VPS desiderato per ridurre screenshot e comandi manuali, ma **non configurato né autorizzato operativamente da questo checkpoint**;
4. nessun reset totale: tutti i mesi di dati, trade, journal, memorie, scoreboard e storico decisionale devono essere conservati;
5. capacità di apprendimento del nuovo Brain come requisito centrale e da dimostrare, non da presumere;
6. Falco e la sua logica SHORT devono restare patrimonio consultivo del Brain; Toro/Falco restano portafogli PAPER storici, non cancellati;
7. interfaccia futura dedicata al Brain, più pulita, con trade aperti, statistiche e panoramica; solo requisito, non implementazione;
8. la gara Arena in corso non viene modificata da questo checkpoint. L'orientamento verso un'unica architettura Brain è roadmap successiva, non ordine di fermare servizi o alterare la run.

## Stato consolidato utilizzabile per la ripresa

### Obiettivo e portafogli PAPER

- **Falco:** portafoglio storico PAPER; la strategia SHORT e i suoi risultati devono restare disponibili come segnale/consiglio.
- **Toro:** portafoglio storico PAPER; conservazione obbligatoria.
- **Brain:** portafoglio PAPER da evolvere verso un cervello unico. Il runner storico è fermo secondo l'ultimo controllo disponibile; il servizio uscite risultava sano. Non è stato riavviato.
- **Arena AI:** esperimento separato ancora da lasciare concludere invariato; DeepSeek rimane favorito provvisorio, non vincitore certificato. L'etichetta “Cloud” non identifica ancora un modello o fornitore.

### Desiderato contro implementato/provato

- **Desiderato:** Brain unico con apprendimento verificabile, memoria storica completa, collaborazione Work/Cloud, automazione operativa e UI Brain dedicata.
- **Provato:** esistono storici, EventJournal, trade e componenti di memoria/scoreboard; la sola presenza dei dati non dimostra che la catena journal → memoria/scoreboard → contesto decisionale → gate di rischio modifichi davvero le decisioni.
- **Provato:** il runner Brain era `inactive/dead` dopo `halted:exit_service_unhealthy`; l'exit service era poi `active/running` e healthy. Nessun controllo successivo in questo checkpoint.
- **Non implementato/non approvato:** nuovo Brain unico, agente Cloud dedicato, accessi VPS per Work/Cloud, nuova UI, migrazione dati, restart, reset o deploy.
- **Preparato soltanto:** backup esterno sul ramo `work/extbackup-bot-stopped-20261109`; non installato.
- **Chiave age:** sul PC è stato ottenuto `ESITO: VERIFICA OK` e la chiave pubblica coincide; questo **non certifica** il backup né la chiave sulla VPS. Nessun segreto letto o registrato.

### GitHub, PR e test

- PR #112: open/draft, non mergiata, HEAD `86288a356209cef9264a369d24a2e8d7914c5ec2`; ultimo commento verificato 18/11/2026 19:57 Europe/Rome.
- RC84 PR #80: open/draft, non mergiata, HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Nessun nuovo commit sul ramo predefinito dopo il precedente checkpoint.
- I test restano quelli già documentati nelle rispettive fonti GitHub; nessuna suite è stata rieseguita in questo checkpoint e non si dichiara un nuovo PASS.
- Gap Arena invariato: il codice seleziona 25 crypto idonee continuando oltre il rank assoluto 25 dopo esclusioni; lo snapshot effettivo della run non è stato verificato.

## Problemi e blocker

1. apprendimento Brain non ancora provato end-to-end;
2. runner Brain fermo all'ultimo riscontro e nessun nuovo stato live;
3. architettura e responsabilità Work/Cloud non definite;
4. accesso VPS multi-agente non progettato con least privilege, audit e separazione dei segreti;
5. migrazione/continuità di storico, memoria e EventJournal non ancora collaudata;
6. “Cloud” e l'eventuale AI assistente non sono specificati in modo univoco;
7. backup esterno non installato e verifica age PC non equivalente a restore test VPS.

## Prossimo passo autorizzabile, non eseguito

Preparare, in documentazione e ramo isolato, un piano del Brain unico con:

- inventario read-only di dati, journal, memorie, scoreboard, trade e configurazioni;
- mappa desiderato/implementato e criteri di accettazione dell'apprendimento;
- strategia di conservazione e migrazione senza cancellazioni;
- ruoli Work/Cloud, prompt di handoff e procedura di ripresa;
- modello di accesso VPS a privilegi minimi, senza condividere segreti in chat o GitHub;
- piano di test PAPER e rollback, senza interferire con Arena.

Qualunque accesso VPS, installazione, modifica codice, restart, deploy o migrazione richiede autorizzazione separata e controlli specifici.

## Invarianti

- PAPER soltanto; nessun ordine LIVE.
- Storici, trade, posizioni, EventJournal, memorie e scoreboard da preservare.
- Nessun merge, deploy, GitHub Action, VPS, reboot, restart, reset, modifica di rischio o API a pagamento.
- Nessuna chiave privata, passphrase, token, segreto o dettaglio d'accesso pubblicato.
