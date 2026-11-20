# Checkpoint verificabile SuperBot-Trading — 20/11/2026 21:44 Europe/Rome

## Esito sintetico

Dal checkpoint delle 20:46 sono emerse due novità verificate nel ramo di integrazione: è stato preparato un laboratorio offline preregistrato per confrontare le uscite e il proprietario ha scelto il **profilo di rischio B Bilanciato** come riferimento del primo collaudo PAPER. La scelta non è ancora un mandato applicato: nessun parametro operativo, runtime, journal, servizio o runner è stato modificato. Il nuovo laboratorio non ha analizzato dati reali e non può promuovere automaticamente una strategia.

## Obiettivi e decisioni consolidate

- Trading esclusivamente **PAPER**, con tre portafogli separati: **Falco**, **Toro**, **Brain**.
- Falco e Toro restano storici integri e intoccabili, `semantic_not_certified`, conservati per memoria/audit ma esclusi da split, sufficienza e training.
- Brain Unico resta la priorità: memoria verificabile, protezione dei profitti, rischio esplicito, dati attestati, collaudo misurabile e rollback.
- Profilo B scelto per il primo PAPER da 2.000 USDT:
  - rischio per trade **1% / 20 USDT**;
  - massimo **4 posizioni** e **4%** di rischio aperto;
  - avviso giornaliero al **3%**, stop alle nuove aperture al **4%**;
  - pavimento equity **1.600 USDT**;
  - leva consentita **1–30×**.
- Il mandato definitivo e il relativo `policy_hash` restano da preparare e approvare: il profilo non è attivo.
- Nessuna importazione da fonti esterne, nessuna seconda memoria operativa; Fase A soltanto dopo la RC, offline/read-only e su dati attestati.
- Nessuna ulteriore indagine o prova Termius su Falco/Toro senza una nuova richiesta.

## Configurazione e rischio: desiderato contro implementato

| Area | Desiderato/deciso | Implementato o verificato nel repository | Non operativo / non provato |
|---|---|---|---|
| Falco/Toro | conservazione integrale, nessun training | righe `excluded` / `semantic_not_certified`; originali preservati | riconciliazione sospesa; nessuna nuova prova autorizzata |
| Brain | PAPER AI-first, memoria e uscite verificabili | memoria read-only completa, inclusi duplicati per slot; laboratorio uscite preregistrato | collaudo PAPER e stato live non verificati qui |
| Rischio | profilo B per 2.000 USDT | scelta registrata e aritmetica confrontata col RiskManager | mandato non applicato; configurazione nuova run non creata/approvata |
| Leva | intervallo 1–30× con protezione liquidazione | il modello propone la leva; il motore può soltanto abbassarla se insicura e registra `risk:leverage_adjusted` | leva minima calcolata non operativa |
| Costi | misurare impatto senza introdurre blocchi prematuri | previste metriche per aperture con costi stimati >25% del rischio | filtro bloccante fuori dal primo PAPER |
| Perdita giornaliera | avviso 3%, stop nuove aperture 4% | valori scelti nel profilo B | Issue #124 P0 aperta; persistenza fail-closed da chiudere prima del deploy |
| Uscite | proteggere profitto con confronto imparziale | bracci offline e protocollo statistico preregistrati | nessuna analisi su dati reali, nessun runtime cambiato |
| Backup | componenti indispensabili separati dagli storici | candidato `75a714be…`, parti cifrate da 90 MiB e 74 test dichiarati | prova reale, installazione, copia off-host e restore PC non eseguiti/certificati |

## Laboratorio uscite preregistrato

Commit `26e4159ffa9b427e0d4e599591a973a5bf2ccd64`:

- riferimento identico a `exits.py`: stop, take-profit 2R, durata massima 24 ore;
- famiglie alternative: pareggio, trailing, protezione dei profitti e inversione EMA20 su 1h;
- stesse entrate, stesse candele chiuse 1m e stessi costi;
- calibrazione cronologica, embargo, test fuori campione, bootstrap a blocchi per giorno e correzione di Holm;
- scenari di funding; minimo 100 trade e 20 giorni;
- soltanto posizioni e candele attestate; Falco/Toro, fonti esterne e dati non attestati esclusi;
- preregistrazione SHA-256 `acfb5f9f958aaf7ebe8f14f92cedf6739345cee44fa686c346c1eba247f74650`;
- nessuna esecuzione su dati reali e nessuna promozione automatica a runtime/training.

## Test con fonte

- `26e4159f…`: 15 test del laboratorio uscite, incluse 2 mutazioni rilevate; 18 test dei profili rischio con parità rispetto a `quote_paper_risk`, secondo il messaggio del commit.
- Gate riferito da `STATO.md` / commit diario `d5533918…`: V3 **5.388**, Dataset Builder **158**, Jest **153**.
- `73f68ad03fa5c14e86eca1f5f02116aace34d93c`: modifica documentale della decisione sul profilo B e delle metriche osservazionali; nessun parametro operativo modificato.
- I test non sono stati rieseguiti da questo checkpoint e non sono presentati come GitHub Actions indipendenti.

## Backup, chiavi e servizi senza dati sensibili

- Prova precedente: archivio cifrato 117.472.954 byte; journal tecnicamente validi Brain 1.058, DeepSeek 1.260, Qwen 1.281, MiniMax 1.306.
- Esito invariato: integrità tecnica Brain/Arena verificata; semantica Falco/Toro non certificata. Restano le anomalie PAPER +21,13 USDT Falco, +39,08 USDT Toro e 30 trade Toro soltanto nello storico.
- Candidato corrente `claude/extbackup-storici-20261121` @ `75a714be3976a732afa88a9aed3c6dc8c248e70f`: codice preparato, non prova di installazione o backup off-host riuscito.
- Ramo storico `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: preparato ma non installato/certificato.
- Copia cifrata della chiave `age` sul PC: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica coincidente. È una prova locale; non certifica backup o restore sulla VPS.
- Stato live generale di runner, ExitService, app, backup e VPS: **non verificato**.
- Nessuna chiave privata, passphrase, token, segreto o dettaglio d’accesso è stato letto o pubblicato.

## Branch, PR, issue e SHA verificati

- `diario` prima di questa scrittura: `8436cbb7e3761b97201e5ca54bf065457b338fe9`.
- `integration/brain-unico-20261119`: `73f68ad03fa5c14e86eca1f5f02116aace34d93c`.
- `claude/extbackup-storici-20261121`: `75a714be3976a732afa88a9aed3c6dc8c248e70f`.
- `work/extbackup-bot-stopped-20261109`: `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`, invariato.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80): **open/draft**, head `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Issue [#124](https://github.com/alexiptv82/SuperBot-Trading/issues/124): **open**, P0 e ancora bloccante.

## Eseguito, preparato, non approvato

- **Deciso:** profilo B come riferimento del primo PAPER.
- **Eseguito nel repository:** laboratorio uscite, preregistrazione, profili rischio, documentazione e test offline.
- **Preparato:** mandato/configurazione della nuova run, Fase A dopo RC, prova finale extbackup per componenti.
- **Non applicato:** profilo B, leva minima calcolata, filtro costi, mandato, `policy_hash`, runtime e servizi.
- **Non eseguito/certificato:** analisi uscite su dati reali, nuova prova backup, installazione, copia off-host, restore PC, collaudo PAPER e verifica live VPS.
- **Non approvato:** merge/deploy, training, ordini, LIVE, API a pagamento, uso di dati esterni, seconda memoria.

## Blocker e prossime attività

1. Preparare mandato e configurazione della nuova run con profilo B; richiedere approvazione prima di applicarli.
2. Chiudere e verificare Issue #124 prima di qualunque deploy Brain Unico.
3. Completare RC; soltanto dopo eseguire il laboratorio uscite sui dati attestati.
4. Eseguire, con consenso separato, prova amministrativa del backup per componenti, primo invio cifrato e restore sul PC.
5. Pre-collaudo PAPER con metriche di memoria, costi, leve corrette, perdita giornaliera, uscite e rollback.
6. Conservare Falco/Toro ed escluderli dal training; nessuna riscrittura degli storici.

## Istruzioni di ripresa

1. Leggere `STATO.md`, questo checkpoint e l’ultima versione di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare le HEAD di diario, integrazione, candidato extbackup, PR #80, Issue #124 e ramo extbackup storico.
3. Usare `73f68ad0…` come HEAD integrazione documentata; profilo B è deciso ma **non applicato**.
4. Trattare `26e4159f…` come laboratorio offline preregistrato, non come strategia approvata o analisi già svolta.
5. Trattare `75a714be…` come candidato extbackup preparato, non installato né certificato off-host.
6. Preservare PAPER, EventJournal, storici append-only, dati attestati e divieto di pubblicare segreti.

---

Checkpoint esclusivamente documentale; nessun merge, deploy, modifica VPS/servizi, reboot, reset, ordine, training o API a pagamento.
