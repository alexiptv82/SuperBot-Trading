# Checkpoint SuperBot — FRRD registrato; Toro Swing LONG solo proposto; weekend senza modifiche

**Data:** 14/11/2026, 08:48 Europe/Rome  
**Ambito:** sola documentazione; trading esclusivamente PAPER; storici ed EventJournal da preservare.

## Sintesi verificabile

Dopo il checkpoint delle 01:55 è emersa una lacuna importante:

1. L'[Issue #95](https://github.com/alexiptv82/SuperBot-Trading/issues/95) è stata aggiornata alle 07:46 circa Europe/Rome con un'analisi di sola lettura della proposta **Fast Reversal & Regime Detector (FRRD)** per Brain.
2. Una conversazione recente effettivamente accessibile registra la decisione utente delle 08:22 circa Europe/Rome: **nessuna modifica nel weekend**; Falco/Toro restano in pausa; la strategia SHORT esistente non si tocca; Brain prosegue esclusivamente PAPER. Per Toro si studierà separatamente una strategia LONG non-scalp, su timeframe più alti e durata più lunga.

Non è stato eseguito alcun controllo SSH live in questo checkpoint e non sono disponibili trascrizioni integrali delle chat. Nessun dato runtime successivo viene quindi certificato come stato VPS corrente.

## Fatto / verificato

- **FRRD documentato nell'Issue #95, non in una PR #95.** Commento: [analisi FRRD](https://github.com/alexiptv82/SuperBot-Trading/issues/95#issuecomment-6873326487).
- Riscontro codice registrato nell'Issue, riferito al commit storico `0e29a73a36f668643da4088178bacb8616a45ac0`:
  - payload Brain basato su 15m con feed 15m/1h/4h, senza 5m/1m;
  - ciclo indicato 15 minuti;
  - classificatore regime attuale dichiarato senza memoria e senza isteresi;
  - peer PAPER già leggibili come posizioni, non come motivazioni/metriche complete.
- FRRD è giudicato idoneo soltanto a un laboratorio isolato e shadow: CHoCH/BOS 5m–15m, CUSUM opzionale, stati persistenti con isteresi, timestamp causali e confronto con baseline invariata. Non prova redditività e non autorizza deploy.
- Decisione utente recente:
  - lasciare trascorrere il weekend senza cambiare strategie o parametri;
  - Falco e Toro restano in pausa;
  - preservare integralmente lo SHORT esistente;
  - Brain continua solo PAPER;
  - progettare per Toro un LONG separato e non-scalp, con timeframe più alti, durata da ore a giorni e possibili leva/margine/slot differenti, tutti ancora da approvare e validare.
- L'indicazione conversazionale di quattro posizioni Brain è disponibile solo come riepilogo di chat, senza output diretto/SSH in questo checkpoint: **non viene promossa a fatto runtime verificato**.

## Preparato / proposto, non implementato

- **Brain FRRD:** piano di laboratorio baseline vs CHoCH/BOS osservatore vs CHoCH/BOS+CUSUM osservatore; niente veto, trade forzati, rischio o percorso esecutivo modificato.
- **Toro Swing LONG V1:** proposta preliminare di laboratorio. I numeri suggeriti in conversazione (4H–1D, ingresso 1H–4H, 1–5 giorni o più, leva indicativa 3–6x) sono ipotesi tecniche, **non parametri finali approvati né implementati**.
- **Falco SHORT-only:** ramo `work/falco-short-only-20261114` invariato a `154f5535396551265592fe6605c00e2cffc18f49`; test presenti ma nessun nuovo output di esecuzione, nessuna installazione o PR.
- **Backup esterno:** ramo `work/extbackup-bot-stopped-20261109` invariato a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`; preparato, non installato.

## Rilasciato / stato documentato

- Nessun rilascio, merge, deploy, GitHub Actions, restart, reset, unpause, ordine o modifica di rischio eseguiti da questo checkpoint.
- Brain branch `work/brain-exit-observability-20261113` invariato a `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`.
- L'ultimo stato operativo puntuale documentato resta quello delle 01:07 Europe/Rome: Brain riportato RUNNING e exit HEALTHY in PAPER. **Non equivale a verifica live alle 08:48.**
- RC84 [PR #80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta Draft/non mergiata, HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Toro [PR #99](https://github.com/alexiptv82/SuperBot-Trading/pull/99) resta Draft/non mergiata e strategicamente NO-GO, HEAD `4b06716546f91b1bb9f34bfc9256d57f321f1d84`.
- Verifica copia cifrata chiave age sul PC: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; prova locale, **non certifica il backup sulla VPS**.

## Test e fonti

- Nessun nuovo test eseguito o output PASS aggiunto nella finestra.
- Restano validi soltanto i risultati già documentati con fonte nei checkpoint storici, inclusi Brain P0 192/192 PASS isolati.
- Le conversazioni recenti sono accessibili solo in forma parziale/riassunta; nessuna trascrizione integrale di chat persa è stata ricostruita.

## Problemi / blocker

- Nessuna verifica runtime live di Brain alle 08:48.
- Redditività e utilità FRRD non provate.
- Toro Swing LONG non preregistrato né testato; parametri e gestione slot/rischio non approvati.
- Falco SHORT-only non collaudato con output verificato e non installato.
- Backup esterno non installato; copia age verificata solo sul PC.

## Prossimo passo sicuro

1. Durante il weekend non modificare i tre percorsi operativi.
2. Al prossimo controllo autorizzato, produrre un report **READ-ONLY** Brain: health, journal, aperture/chiusure, LONG/SHORT/NO_TRADE, PnL netto, feed e anomalie.
3. Solo dopo il report, preregistrare separatamente:
   - laboratorio FRRD shadow senza impatto decisionale;
   - laboratorio Toro Swing LONG con costi, stop, target, hold massimo, leva, size, slot, benchmark e gate OOS fissati prima dei risultati.
4. Prima di un eventuale riavvio PAPER Falco, eseguire i test offline della patch SHORT-only preservando integralmente la strategia SHORT esistente.

**Vincoli permanenti:** solo PAPER; storici ed EventJournal preservati; nessun segreto o dato di accesso; nessun LIVE.
