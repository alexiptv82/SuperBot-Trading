# Checkpoint verificabile SuperBot-Trading — 20/11/2026 06:51 Europe/Rome

## Esito e fonti consultate

Novità verificata dopo il checkpoint 05:47: il ramo laboratorio `integration/brain-unico-20261119` è avanzato da `5c2edfcaa4d64a50f0a1496515ec64bb9d8caf87` a `3f1c5b9fa2b672f37d303193e85b6ce5c2b2e93f` con cinque commit. Consultati GitHub (commit/diff, `STATO.md`, diario, PR/Issue), Library v129 e conversazioni recenti effettivamente accessibili. Nessun controllo live VPS, nessun download di candele e nessuna chiamata a provider sono stati eseguiti.

## Stato consolidato immutato

- Tre portafogli separati, esclusivamente **PAPER**: **Falco**, **Toro**, **Brain**. Riferimenti desiderati già documentati: 1.000/1.000/2.000 USDT. Storici, posizioni, decisioni, trade, Arena, scoreboard ed EventJournal devono restare integri.
- DeepSeek resta decisore primario; altri modelli sono laboratorio SHADOW fisso. PR #120 non integrata; PR #123 laboratorio isolato, senza apertura trade o provider.
- Rischio desiderato/immutato: WARN 35%, HALT 50%, floor equity 450 USDT. Leva 20–50× può essere compatibile con rischio 1–1,5% solo con margine ridotto; nessun parametro runtime modificato.
- Sviluppo/integrabilità solo su `integration/brain-unico-20261119`; esclusi `main`, deploy, VPS, servizi, restart, reset, ordini, LIVE e API a pagamento.

## Novità implementate nel solo laboratorio

1. `9acd96d7ac1ff5b5fa3d40b6cd28f6a6f2618918` — provenienza verificabile degli archivi di candele. Il builder separa quattro requisiti: coerenza matematica delle feature, integrità dei file, provenienza attestata e attestazione del journal. Il solo `candles_meta.json` non basta più, neppure per le etichette.
   - Provenienza `attested`: fonte pubblica attesa uguale al runtime, dati riderivati dalle risposte grezze conservate, URL/simbolo/granularità coerenti, sole candele chiuse e SHA-256 del manifest uguale a un'ancora esterna registrata dall'operatore.
   - L'ancora protegge il manifest ma, da sola, non prova l'autenticità originaria delle risposte.
2. `1aadf4ec9e4609f2a2b11ac8d0be5018fc8b715d` — modalità opzionale `per_symbol`: ogni simbolo usa un istante proprio; deduplicazione per slot anche dopo riavvio. Il predefinito resta `cycle`, `wiring.py` invariato.
   - Scenario riferito: 8 simboli/modello lento/sidecar a metà ciclo, snapshot validi 2/8 in `cycle` contro 8/8 in `per_symbol`.
   - Difetto documentato ma non corretto nel percorso attuale: riavvio nello stesso slot in `cycle` può ridecidere tutti i simboli (16 decisioni invece di 8).
3. `0453433edca2403e4cbee5f70046742363705ef5` — etichette LLM migliorate: osservati separati dai controfattuali, NO_TRADE solo relativi al riferimento, incertezza e limiti espliciti.
4. `24b18d0823b25cd5ac109ddc502b3c3962ca452a` — corregge l'incidente del commit precedente, pubblicato con un test di isolamento fallito; storia preservata. Il difetto era un commento che nominava un componente operativo. Rimedio procedurale documentato: pubblicazione condizionata a suite verde.
5. `3f1c5b9fa2b672f37d303193e85b6ce5c2b2e93f` — procedura di acquisizione 15m/1h/4h **preparata e non eseguita**:
   - stesso `fetch_rows`/endpoint pubblico Bitget `history-candles` usato dal runtime;
   - risposte grezze conservate, riderivazione e controllo incrociato;
   - solo candele chiuse, nessuna sovrascrittura;
   - nessuna rete senza `--confirm-network`; `--plan` per stima;
   - destinazione nuova fuori dal repository, manifest e ancora dell'operatore.

## Test e fonte

- Diario Claude `diario/2026-11-20_claude-provenienza-istante-esiti-acquisizione.md`, commit `fed87aef0f00be52a54661d34af5f29f3894c9cf`.
- Suite V3 offline riferita: 5.235 → **5.264**, 0 falliti alla HEAD; Dataset Builder **153**.
- Mutazioni rieseguite senza cache: copertura 16/16, validatore 14/14, tesi 12/13 (una equivalente), provenienza 15/15, istante 10/10, etichette 10/10.
- L'incidente intermedio è registrato: `0453433e` aveva 1 test fallito; corretto circa cinque minuti dopo da `24b18d08`.
- Questo checkpoint ha verificato SHA, diff, messaggi e documentazione, ma **non ha rieseguito** suite, Actions o collaudi VPS.

## Decisioni e autorizzazioni: divergenza da non nascondere

- La conversazione recente accessibile riporta un consenso limitato a una sola acquisizione pubblica controllata, con `--plan`, massimo 350 tentativi HTTP e 100 MB, senza training.
- Il diario pubblicato dichiara ancora che serve autorizzazione prima dell'esecuzione.
- Per non assumere più del provato, il checkpoint registra la divergenza e mantiene **acquisizione non eseguita**. Prima di usare rete va riconciliato il mandato esplicito; nessuna autorizzazione al training è presente.

## Desiderato versus implementato / preparato

- **Implementato nel laboratorio:** provenienza e integrità separate, validazione feature, opzione `per_symbol`, dedup per slot in quella modalità, etichette LLM con incertezza.
- **Preparato ma non attivo:** acquisizione pubblica, `per_symbol`, anti-reingresso `enforce`, protocollo confronto LLM.
- **Non certificato/non approvato:** candele reali attestate, ancora operatore reale, attestazione journal Fase 0, training, numeri rischio ricostruiti, provider/costi, attivazione runtime, deploy/VPS.
- Anti-reingresso resta `observe`; `per_symbol` non è cablato operativamente.

## Branch, PR e issue verificati

- Integrazione laboratorio: `3f1c5b9fa2b672f37d303193e85b6ce5c2b2e93f`.
- `diario` prima di questo checkpoint: `fed87aef0f00be52a54661d34af5f29f3894c9cf`.
- PR #80 RC84: OPEN/DRAFT, HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`.
- PR #120/#121/#122/#123: OPEN/DRAFT, HEAD `f4f745788e4514d01dc11e11402eb689a2ec7c74`, `5b7403aa333b43d801ca7e28825ea4707f6847b4`, `513448e57747f381e11ce23ab09788d6a41e6cb0`, `c51c7520b35640518baea217404da9657702d4f5`.
- Issue #124 resta OPEN. Correzione presente nel ramo laboratorio non equivale a deploy o certificazione live.

## Servizi, backup e chiavi

- Nessun controllo live VPS: non inferire stato di runner, servizi o timer.
- Backup esterno: `work/extbackup-bot-stopped-20261109@3dc2116a08058f57fc14b695431f6e3fa1a1ca45`, preparato nel repository; installazione, copia off-host e restore VPS non certificati. Un precedente rapporto indiretto sul timer resta conflittuale e non è prova.
- Verifica PC della copia cifrata age: PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. Non certifica backup age, restore o installazione VPS.
- Nessun segreto, token, chiave privata, passphrase o dettaglio d'accesso letto o salvato.

## Blocker, prossime attività e ripresa

1. Ripartire da `integration/brain-unico-20261119@3f1c5b9fa2b672f37d303193e85b6ce5c2b2e93f` e dal diario Claude sopra indicato.
2. Riconciliare il mandato sull'acquisizione prima di qualunque rete; se autorizzata, eseguire prima `--plan` e rispettare i limiti riportati, senza training.
3. Rieseguire offline le suite sullo SHA esatto e poi validare un archivio reale con manifest, risposte grezze e ancora esterna.
4. Decidere separatamente se collaudare/attivare `per_symbol`; misurare duplicati e snapshot tardivi in PAPER.
5. Preregistrare campione, `target_r`, orizzonte e costi prima di provider reali.
6. Conservare fail-closed sulle nuove aperture, uscite indipendenti e tutti gli storici/EventJournal.
