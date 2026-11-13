# Checkpoint verificabile — priorità Brain, Issue #95 e gate DeepSeek E2E

**Data:** 13/11/2026, 11:48 Europe/Rome  
**Ambito:** sola documentazione. Nessun merge, deploy, GitHub Actions, VPS, reboot, reset, unpause, ordine o API a pagamento. Trading esclusivamente PAPER. Storici ed EventJournal da preservare.

## Nuova decisione utente verificata

Conversazione recente effettivamente accessibile del 13/11/2026, ore 11:25 Europe/Rome:

- mettere in priorità il solo **Brain**, portafoglio separato, per iniziare finalmente un test utile;
- verificare che DeepSeek risponda davvero, produca decisioni e che il motore possa aprire trade PAPER legittimi;
- `NO_TRADE` resta valido: nessun trade deve essere forzato;
- mantenere **Falco SHORT** con strategia originale intatta;
- non attivare la coppia gemella;
- sospendere Toro LONG e studiare in futuro una strategia LONG diversa/diversificata;
- nessuna modifica ai classici durante il lavoro Brain.

Questa decisione sostituisce la priorità operativa del Twin: la PR #94 resta evidenza tecnica/negativa, non percorso da attivare.

## Riscontro GitHub — Issue #95

Aperta [Issue #95 — Brain PAPER: verifica DeepSeek E2E e avvio controllato, classici intoccabili](https://github.com/alexiptv82/SuperBot-Trading/issues/95):

- creata 13/11/2026 11:30:20 Europe/Rome;
- stato OPEN, nessun commento;
- nessun branch, commit, merge o deploy creato dall'Issue;
- descrive audit e gate, non autorizza da sola lo sblocco.

### Stato Brain verificabile dalla repo, non dalla VPS

Il codice RC84 documenta una catena possibile:

`DeepSeekL5Analyst → BrainEngine → approval/risk → commit_paper_open`

con trasporto PAPER e servizi dedicati runner/exit. Questo dimostra che il percorso è previsto nel codice, **non** che sia attivo o sano sulla VPS.

Configurazione Brain2000 documentata in repo:

- capitale PAPER 2.000 USDT;
- leva 20×–50×;
- kill/floor configurato 450;
- margine massimo posizione 20%, margine totale 55%;
- rischio massimo 4,2857% per ingresso, open risk 12%;
- ciclo 60 minuti, monitor uscite ogni minuto;
- 8 simboli;
- DeepSeek `deepseek-flash`, thinking high, max_tokens 6.000, cap 0,75 USD/giorno.

La vera configurazione RUN deve essere letta sul server: il `runner_config.json` generico sorgente è diverso e non prova cosa stia usando il processo.

### Cosa NON è ancora provato

- SHA/percorso/processi effettivamente in esecuzione sulla VPS;
- stato corrente dei due servizi Brain e unicità dell'owner uscite;
- heartbeat, journal, budget, backup, pause e mandato attuali;
- `mandate.json approved:true` con `approved_by`, `run_id` e `policy_hash` coerenti;
- presenza della chiave DeepSeek nell'ambiente del processo, senza leggerne il valore;
- credito attuale e una vera inferenza `/v1/chat/completions`;
- parsing JSON, finish_reason, latenza, usage e gestione NO_TRADE reali;
- feed Bitget e timestamp correnti;
- apertura PAPER E2E legittima e servizio uscite sano.

L'11/11 era stato verificato solo saldo DeepSeek HTTP 200/available=true, **non una vera inferenza**. Il documento readiness riportava `approved=false`; lo stato attuale va controllato, non presunto invariato.

## Gate documentati prima di qualsiasi unpause Brain

1. Audit read-only VPS: SHA, percorsi, `DESK_MODE=paper`, unità runner/exit e un solo owner uscite.
2. Integrità e freschezza: journal, budget, config RUN, marker prepared, backup, heartbeat, pause e mandato.
3. Verifica boolean della chiave e credito, senza stampare segreti.
4. Una sola inferenza DeepSeek reale NO_ORDER, senza modificare journal PAPER; `NO_TRADE` accettabile.
5. Test E2E sintetico su journal isolato per dimostrare una proposal OPEN senza forzare trade sul conto.
6. Verifica feed Bitget, rischio liquidazione, daily loss, kill 450 e uscite indipendenti dall'AI.
7. Rapporto go/no-go. Solo dopo eventuale procedura separata per approvazione mandato e rimozione `pause.flag` **SOLO BRAIN**, con rollback immediato.
8. Falco/Toro intoccabili; niente Actions o mutazioni VPS durante l'audit.

**Nessuno di questi gate è stato eseguito da questo checkpoint.** Non c'è accesso SSH/VPS attraverso GitHub e non è stata letta alcuna chiave.

## Stato dei tre portafogli PAPER

- **Brain — priorità corrente:** preparare verifica E2E reale, ma resta non sbloccato finché gate e mandato non sono provati. Ultimo stato documentato, non live: PAUSED e `approved=false`.
- **Falco:** strategia SHORT originale congelata; candidato SHORT_ONLY PR #92 resta Draft, non attivato. Nessuna modifica autorizzata.
- **Toro:** Twin PR #94 non va attivato; strategia LONG sospesa in attesa di un'ipotesi diversa. Toro finale non deciso.
- Capitali di riferimento: Falco 1.000, Toro 1.000, Brain 2.000 USDT, esclusivamente PAPER.

## PR #94 e PR #92 — aggiornamenti documentali, SHA invariati

### PR #94

[PR #94](https://github.com/alexiptv82/SuperBot-Trading/pull/94) resta Draft/non mergiata all'HEAD `4987912775f72f9b2bf0519a41fe9216fc6b45aa`.

La descrizione è stata aggiornata il 13/11/2026 alle 10:53:57 Europe/Rome e ora risolve il precedente disallineamento “test non eseguiti”:

- titolo interno: **PASS tecnico / NON APPROVATO STRATEGICAMENTE**;
- 18 test iniziali + 13 integrativi = **31 test Twin PASS**, riportati da Claude;
- **405 regressioni PASS**;
- suite **7.094 PASS, 1 FAIL ambientale preesistente**;
- replay parità Falco e Toro OFF dichiarati identici alla base;
- risultati strategici rules-only negativi già documentati;
- decisione: Twin OFF, nessun collaudo PAPER operativo.

Questi numeri sono riportati nella descrizione/commit, presenti come evidenze in repo, ma non rieseguiti da questo checkpoint. Nessuna GitHub Actions.

### PR #92

[PR #92](https://github.com/alexiptv82/SuperBot-Trading/pull/92) resta Draft/non mergiata all'HEAD `f8332c92cc2bc4edee3ea7363f71f15a0a37a816`. Descrizione aggiornata alle 10:54:23 Europe/Rome senza cambio codice; mantiene come gate il collaudo autonomo Brain DeepSeek/NO_TRADE e vieta merge/deploy senza consenso.

PR #93 resta FAIL a `c8e8992458264ff81d82f0e9805b9115e11c839c`.

## RC84, servizi, backup e chiavi

Nessun controllo live VPS in questa esecuzione. Ultimo stato documentato: RC84 da sorgente `ab7e0b7…`, Falco/Toro in draining, Brain PAUSED, exit healthy. Non assumerlo attuale senza controllo reale.

- PR #80 RC84 resta riferimento storico;
- backup esterno `work/extbackup-bot-stopped-20261109`: preparato, non installato;
- copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK`, chiave pubblica coincidente;
- la prova certifica la copia locale controllata, non backup o restore VPS;
- nessun segreto, chiave privata, passphrase o token letto o pubblicato.

## Eseguito / preparato / rilasciato

- **Eseguito:** decisione utente recuperata; Issue #95 aperta; descrizioni PR #94/#92 aggiornate; checkpoint documentale.
- **Preparato:** checklist/gate read-only per Brain.
- **Rilasciato:** nulla.
- **Non eseguito/non approvato:** audit VPS, vera inferenza DeepSeek, approvazione mandato, unpause Brain, apertura trade, merge/deploy/reset, attivazione Falco/Toro.

## Blocker e prossimo passo

1. Ottenere prova read-only della VPS e della configurazione RUN Brain senza esporre segreti.
2. Verificare una vera inferenza DeepSeek NO_ORDER e parsing/latency/usage.
3. Eseguire E2E sintetico su journal isolato; non forzare trade sul conto.
4. Verificare exit-owner unico, heartbeat e rollback.
5. Produrre go/no-go; soltanto con tutti i gate PASS e nuovo consenso separato valutare mandato/unpause del solo Brain.
6. Non modificare Falco SHORT; non attivare Toro Twin.

## Limite conversazioni

Sono stati usati soltanto messaggi recenti effettivamente accessibili. Non si presume accesso a chat eliminate, trascrizioni integrali o stato live VPS.
