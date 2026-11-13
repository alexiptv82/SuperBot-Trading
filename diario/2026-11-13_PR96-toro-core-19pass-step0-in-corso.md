# Checkpoint verificabile — PR #96 Toro Profit Hunter: core isolato testato; Step0 Bitget ancora in corso

**Data:** 13/11/2026 16:47 Europe/Rome  
**Ambito di questo checkpoint:** sola documentazione. Nessun merge, deploy, GitHub Actions, riavvio, reset, ordine, modifica Brain o attivazione dei classici eseguiti da questa automazione.

## Sintesi per la ripresa

La decisione utente sul nuovo Toro LONG Profit Hunter è ora concretizzata in una PR Draft isolata. Il core candidato e il replay Step0 sono presenti su GitHub; i test isolati eseguiti dall'utente via Termius sono arrivati a **19/19 PASS** con stage operativo dichiarato invariato.

Lo Step0 read-only su dati Bitget pubblici è stato avviato ma, all'ultimo riscontro delle 16:43 Europe/Rome, era ancora in esecuzione. La chiusura accidentale della finestra Termius non ha interrotto il processo: non occorre rilanciarlo e non va avviata una seconda istanza. Nessun report finale, expectancy, profit factor o verdetto strategico è ancora disponibile.

## Fonti e limiti

- [PR Draft #96](https://github.com/alexiptv82/SuperBot-Trading/pull/96), ramo `work/toro-profit-hunter-v1-20261113`.
- HEAD verificato [`862c110bdb4eac615c26f00d8613f91972189e50`](https://github.com/alexiptv82/SuperBot-Trading/commit/862c110bdb4eac615c26f00d8613f91972189e50), base `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Commenti PR #96 con output/screenshot Termius delle 16:11, 16:21, 16:34 e 16:43 Europe/Rome.
- Conversazioni recenti consultate soltanto nelle parti effettivamente accessibili; nessuna trascrizione integrale o recupero di chat eliminate.
- Nessun accesso SSH autonomo o controllo VPS live continuo. Gli esiti host derivano dagli screenshot/output forniti dall'utente.

## Implementato nella PR #96

PR aperta, Draft, non mergiata, 25 commit e 7 file modificati. Il perimetro verificato comprende:

- `backend/desk/toro_profit_hunter.py`: nucleo puro/isolato LONG con BB100 e conferma 1H chiusa, contesto EMA50/200 4H e ADX, ATR, anti-knife, stop strutturale e no lookahead;
- sizing: rischio massimo proposto 16 USDT per trade, 40 USDT aggregati, margine massimo 200 per trade/800 aggregato, riserva 200, 5 slot, leva calcolata fino a 20× e soggetta ai tier;
- gate R:R netto costi, nessun DCA;
- simulazione maker pending PAPER conservativa con attraversamento successivo e scadenza;
- Profit Guardian advisory con high-water mark, ratchet floor e decisioni HOLD/CLOSE/PARTIAL su dati chiusi;
- replay Step0 offline/read-only con confronto 4/8/12 ore e benchmark casuale appaiato;
- test unitari, harness isolato e script read-only Bitget;
- documentazione tecnica dedicata.

## Test eseguiti con fonte

Gli output Termius registrati nella PR attestano:

1. **16/16 PASS** alle 16:11, stage invariato;
2. **18/18 PASS** alle 16:21, stage invariato;
3. **19/19 PASS** alle 16:34, stage invariato; avvio fetch Bitget BTCUSDT 1H per 365 giorni.

Il PASS riguarda il core e gli strumenti isolati. Non certifica edge storico, redditività, contabilità PAPER, fill maker operativo, Guardian al minuto nel runner, chiusura manuale, integrazione CLI o attivazione Toro.

Nota di consistenza: il corpo iniziale della PR contiene ancora frasi “test non eseguiti”; i commenti successivi con output reale costituiscono l'evidenza più recente. Aggiornare la descrizione prima di qualsiasi gate di rilascio.

## Step0 Bitget — stato verificato

- Script SHA-pinned/read-only avviato dopo i 19 test.
- Obiettivo: 365 giorni di barre chiuse 1H/4H per BTC, ETH, SOL, BNB e XRP, coverage/freshness, segnali e confronto random appaiato per 4/8/12 ore con costi.
- Alle 16:43 il processo era ancora vivo dopo la chiusura accidentale di Termius.
- Verificata la presenza parziale dei CSV BTC ed ETH 1H/4H.
- Report finale ancora assente; nessun numero di segnali, expectancy, PF o confronto random disponibile.
- Non rilanciare in parallelo, non interrompere e non dedurre successo strategico dai test unitari o dal download parziale.

## Blocchi di rilascio

1. Core non collegato a `backend/desk/cli.py` o `engine.py`; nessun flag operativo supportato.
2. PaperAccount legacy non implementa ancora il modello maker proposto; mancano integrazione contabile, claim, persistenza, manual close e gestione PARTIAL/residuo.
3. Profit Guardian resta advisory e non integrato nel journal/monitor operativo.
4. Step0 non completato: nessun edge dimostrato; gli studi LONG precedenti sono negativi.
5. Falco SHORT_ONLY richiede gate separato e regressioni senza modificare i segnali SHORT; la base VPS corrente non lo incorpora.
6. Stato operativo Falco/Toro non verificato direttamente; nessun unpause o riavvio autorizzato da questa PR.
7. Il branch parte dalla base `0e29a73…`, precedente ai due hotfix Brain installati localmente: non sovrascrivere lo stage VPS o i due file Brain.

## Tre portafogli PAPER — desiderato vs implementato

- **Brain:** già unpaused nel checkpoint precedente; questa attività Toro non lo ha modificato. Primo ciclo completo sugli 8 simboli non risulta ancora documentato da nuove evidenze GitHub.
- **Falco:** SHORT originale invariato e ancora non riattivato. Gate SHORT_ONLY non rilasciato.
- **Toro:** core Profit Hunter V1 implementato e 19 test isolati PASS; Step0 in corso. Non integrato nel runner, non rilasciato e non riattivato.

## Eseguito / preparato / rilasciato / non approvato

- **Eseguito:** implementazione core isolato, harness/replay; test progressivi 16/18/19 PASS; avvio Step0 read-only; verifica che il processo sia sopravvissuto alla chiusura Termius.
- **Preparato:** PR #96, documentazione, script Bitget e rapporto JSON finale atteso.
- **Rilasciato:** nulla sui classici; nessun merge/deploy/riavvio. Brain invariato.
- **Non ancora approvato/eseguito:** adapter Toro, integrazione contabile/Guardian, merge, deploy, attivazione Toro, riaccensione Falco/Toro, reset o ordini.

## Backup, chiavi e conservazione

- Extbackup `work/extbackup-bot-stopped-20261109`: preparato ma non installato.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup/restore VPS.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta riferimento storico.
- Solo PAPER; storici ed EventJournal devono essere preservati.
- Nessuna chiave privata, token, passphrase o dettaglio utile all'accesso VPS salvato.

## Prossimi passi e istruzioni di ripresa

1. Attendere la conclusione dell'unica istanza Step0; non rilanciarla.
2. Leggere e validare il report finale: fonti/hash, coverage e freschezza, segnali per simbolo/regime, gross/netto costi e benchmark random 4/8/12h.
3. Se coverage insufficiente o Step0 non mostra edge plausibile: fermare l'integrazione operativa senza tuning sulla stessa finestra.
4. Solo con esito credibile: completare adapter PAPER, maker/contabilità/claim, Guardian 1m, manual close, stop/liquidazione e regressioni Falco SHORT.
5. Richiedere autorizzazione separata prima di merge/deploy o riattivazione Falco/Toro.
6. Per riprendere leggere questo checkpoint, `STATO.md`, PR #96 e i suoi commenti cronologici; non confondere test unitari PASS con strategia profittevole o release-ready.
