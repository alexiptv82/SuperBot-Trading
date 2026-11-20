# Checkpoint verificabile SuperBot-Trading — 20/11/2026 07:45 Europe/Rome

## Esito e fonti

Novità verificata: `integration/brain-unico-20261119` è avanzato da `3f1c5b9fa2b672f37d303193e85b6ce5c2b2e93f` a `8e03235dd9e3d9f3ccd467be9e051254cbf7ca52`. Consultati commit/diff GitHub, `STATO.md`, diario `2026-11-20_claude-acquisizione-duplicazione-dashboard.md`, PR/Issue, Library v130 e conversazioni recenti accessibili. Nessun controllo live VPS.

## Perimetro consolidato

- Solo **PAPER**, portafogli separati **Falco/Toro/Brain**; riferimenti 1.000/1.000/2.000 USDT. Preservare storici, posizioni, decisioni, trade, Arena, scoreboard ed EventJournal.
- DeepSeek resta decisore; altri modelli solo laboratorio SHADOW. PR #120 non integrata, PR #123 laboratorio isolato.
- Rischio invariato: WARN 35%, HALT 50%, floor 450 USDT. Nessun parametro runtime cambiato.
- Lavoro consentito solo sul ramo laboratorio; nessun `main`, deploy, VPS, servizi, restart, reset, ordine, LIVE, training o API a pagamento.

## Acquisizione candele: eseguita una volta e interrotta fail-closed

- `a3967b51b13a5c4dad28d8aa65e4da7e03437872`: limiti rigidi implementati prima della rete: massimo 350 tentativi HTTP complessivi, retry inclusi; archivio massimo 100 MB; massimo 47 giorni; solo 8 simboli e 15m/1h/4h; cartella temporanea resa definitiva solo dopo tutti i controlli.
- `--plan` riportato: 04/10/2026–20/11/2026 00:00 UTC, 24 file, 272 richieste stimate, ~11,8 MB.
- Unica esecuzione autorizzata: interrotta dopo **24 tentativi HTTP** su `derivation_differs_from_runtime:15m:BTCUSDT`.
- **Nessun archivio, manifest o SHA-256 di attestazione prodotto; nessun dato conservato.** Resta soltanto un rapporto `.ABORTED.json` con `archive_written=false`.
- `2c07f7a94c8de3520b6da442ad5f4be256a8c051`: derivazione corretta per usare la stessa regola del runtime e diagnostica migliorata. La causa sui dati reali è solo probabile, non confermata.
- Nessun secondo download: serve una nuova autorizzazione e una nuova destinazione.

## Correzioni e nuove funzioni nel ramo laboratorio

1. `bd4f28801f6fd35c45e3a3c94f12f6d876266cf8` — deduplicazione per slot anche in modalità `cycle`: un riavvio non ridecide i simboli già processati; dopo ciclo parziale decide solo i mancanti. Gravità classificata media: costi AI/campioni duplicati e possibile riapertura nello stesso slot, ma non doppia posizione.
2. `b71e706fcd51300c6f4a088496a42f14ac25a008` — Dataset Builder assegna a ogni riga `verified`, `unverified` o `excluded`, senza cancellarla. `verified` significa candidata, non autorizzazione; `training_authorized=false`.
3. `c768a6f4e2acd58e534cd1b8fad3558b794a17e8` — memoria/apprendimento nella schermata esistente “V3 · 3 bot”:
   - endpoint GET autenticato, sola lettura, `no-store`;
   - decisioni, link validi, snapshot mancanti/invalidi, NO_TRADE, aperture senza traccia, tesi e reingressi observe;
   - sempre `training_authorized=false` e `model_active=false`; nessuna feature, numero rischio o testo del modello.
   - pannelli Memoria decisionale, Tesi e reingressi, Apprendimento; fallimento memoria non rompe il resto della Overview.
4. `8e03235dd9e3d9f3ccd467be9e051254cbf7ca52` — aggiorna l'inventario delle rotte RC84 per la nuova GET. Il gate ha bloccato la pubblicazione finché il test non è stato corretto; l'unica rotta di scrittura resta la chiusura Brain preesistente.

## Test e provenienza

- Fonte primaria: diario Claude commit `2925d442f45e587ce2adf80f0361bc9f67f7406a`.
- Test riferiti alla HEAD: V3 **5.298**, 0 falliti; Builder **157**; Jest **129/129**; build frontend di produzione OK in directory temporanea.
- Limiti acquisizione: 21 test offline, mutazioni 14/14. Deduplicazione: mutazioni 3/3.
- Gate di pubblicazione collaudato su esiti simulati e una sonda fallita; ha bloccato la pubblicazione del nuovo endpoint fino al fix.
- Numeri verificati come documentazione/commit, ma non rieseguiti da questo checkpoint, non Actions e non VPS.

## Stato desiderato versus implementato

- **Implementato nel laboratorio:** limiti acquisizione, fail-closed senza archivio parziale, dedup slot nel percorso `cycle`, stati dataset e memoria read-only nell'app.
- **Preparato/non attivo:** modalità `per_symbol`, anti-reingresso `enforce`, acquisizione corretta per un nuovo tentativo, protocollo LLM.
- **Non approvato/non eseguito:** nuova acquisizione, archivio attestato, training, provider, attivazione `per_symbol`, deploy/app pubblicata/VPS.
- Anti-reingresso resta `observe`; cablaggio temporale resta `cycle`.

## Branch, PR e issue

- Laboratorio: `8e03235dd9e3d9f3ccd467be9e051254cbf7ca52`.
- `diario` pre-checkpoint: `2925d442f45e587ce2adf80f0361bc9f67f7406a`.
- PR #80 RC84 OPEN/DRAFT @ `0e29a73a36f668643da4088178bacb8616a45ac0`.
- PR #120/#121/#122/#123 OPEN/DRAFT @ `f4f745788e4514d01dc11e11402eb689a2ec7c74`, `5b7403aa333b43d801ca7e28825ea4707f6847b4`, `513448e57747f381e11ce23ab09788d6a41e6cb0`, `c51c7520b35640518baea217404da9657702d4f5`.
- Issue #124 resta OPEN; presenza del fix nel laboratorio non certifica deploy/live.

## Servizi, backup e chiavi

- Nessuna verifica live VPS; non inferire stato runner/servizi/timer.
- Extbackup: `work/extbackup-bot-stopped-20261109@3dc2116a08058f57fc14b695431f6e3fa1a1ca45`, preparato; installazione/off-host/restore VPS non certificati. Rapporto indiretto sul timer resta conflittuale.
- Copia cifrata age sul PC: PowerShell **`ESITO: VERIFICA OK`**, chiave pubblica derivata coincidente. Non certifica backup age o VPS.
- Nessun segreto, token, chiave privata o passphrase letto/salvato.

## Blocker e ripresa

1. Ripartire da `integration/brain-unico-20261119@8e03235dd9e3d9f3ccd467be9e051254cbf7ca52` e dal diario Claude sopra citato.
2. Non ripetere l'acquisizione senza nuova autorizzazione; usare destinazione nuova. Prima rieseguire offline i test sulla derivazione corretta.
3. Validare poi manifest/risposte grezze/ancora e i quattro requisiti, senza autorizzare training implicitamente.
4. Collaudare separatamente `per_symbol`; mantenere `cycle` finché non approvato.
5. Dashboard futura: latch perdita giornaliera e riepilogo dei quattro requisiti quando esisterà un rapporto reale del builder.
6. Conservare fail-closed sulle aperture, uscite indipendenti e tutti gli storici/EventJournal.
