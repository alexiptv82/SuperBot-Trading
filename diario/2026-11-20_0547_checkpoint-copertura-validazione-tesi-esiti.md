# Checkpoint verificabile SuperBot-Trading — 20/11/2026 05:47 Europe/Rome

## Esito e fonti consultate

Novità verificata: il ramo laboratorio `integration/brain-unico-20261119` è avanzato da `a5a920401e0259c63a316ceb6eea573b4a12ac8a` a `5c2edfcaa4d64a50f0a1496515ec64bb9d8caf87` con quattro commit. Fonti: API GitHub (ramo/commit/diff), `STATO.md`, diario `2026-11-20_claude-copertura-validazione-tesi-esiti.md`, PR/Issue correnti, Library v128 e conversazioni recenti effettivamente accessibili. Nessun controllo live della VPS è stato eseguito.

## Obiettivo e perimetro immutati

- Sistema esclusivamente **PAPER**, con tre portafogli separati: **Falco** e **Toro** (classici) e **Brain** (laboratorio/Brain Unico). Preservare storici, posizioni, decisioni, trade, Arena, scoreboard ed EventJournal; nessun reset.
- Capitale di riferimento desiderato già documentato: Falco 1.000 USDT, Toro 1.000 USDT, Brain 2.000 USDT, ma nessuna nuova run o modifica runtime è autorizzata da questo checkpoint.
- DeepSeek resta il decisore primario desiderato/implementato nel ramo noto; altri modelli restano laboratorio SHADOW a configurazione fissa. PR #120 non è integrata; PR #123 è laboratorio isolato e non apre trade.
- Soglie rischio desiderate e non modificate: WARN 35%, HALT 50%, floor equity 450 USDT. Leva 20–50× può rispettare rischio 1–1,5% solo riducendo il margine; lo studio non modifica parametri.
- Autorizzazione riconfermata: sviluppo e integrazione solo su `integration/brain-unico-20261119`; esclusi `main`, deploy, servizi, VPS, restart, reset, parametri attivi, ordini, API a pagamento e LIVE.

## Novità implementata nel solo ramo laboratorio

Confronto GitHub `a5a92040…5c2edfca`:

1. `14f42c40b6cd7b8def8da0bf61507c07987f4f90` — regola canonica unica per decisione → snapshot → apertura, controllo di hash/catena/ordine/causalità/ritardi; `trace_coverage` conta solo link validi. Feature catturate prima del modello, istanti di riferimento/dati/cattura/scrittura separati, digest e finestra delle candele. EventJournal letto tramite query indicizzate.
2. `d63e31a8d558ce4cd6284667a666fd693370f204` — validatore indipendente delle feature nel Dataset Builder, senza rete né import del runtime, partendo da copie attestate delle candele. Solo `verified` rimuove `snapshot_unverified`; la riga resta esclusa finché il journal non è attestato (Fase 0), e i numeri di rischio restano esclusi.
3. `1193ffaaf072fd1fd3257f4aff07fdb4f9c5c1c5` — `thesis_id` persistente e anti-reingresso cablato in modalità **observe**. Il blocco `enforce` è implementato/testato ma non attivo; soglie da misurare con E0 e approvare dal proprietario.
4. `5c2edfcaa4d64a50f0a1496515ec64bb9d8caf87` — etichette di esito di mercato per il laboratorio LLM: stesse regole per ogni modello, EV netto in R e confronto NO_TRADE; accordo con il riferimento non è criterio di correttezza. Nessun provider chiamato.

### Prestazioni e test, con fonte

- Benchmark riportato nel diario Claude: lettura completa del journal ~0,14 s a 10.000 eventi, ~1,0 s a 60.000, ~4,5 s a 200.000. Ciclo 8 simboli/60.000 eventi: 28,7 s → 1,3 s (senza traccia 7,7 s → 1,1 s).
- Suite V3 offline riferita: 5.147 → **5.235**, 0 falliti; Dataset Builder 134 dopo ogni passo. Mutazioni: copertura/provenienza 16/16, validatore 14/14, tesi 12/13 con superstite dichiarata equivalente, etichette 10/10.
- Fonte primaria dei numeri: commit e diario Claude sul ramo `diario`, commit diario `82cfea0ffecb1ed28f1b18c0d582822cc140e154`. Questo checkpoint ha verificato SHA, diff, messaggi e documentazione, ma **non ha rieseguito** le suite, non ha usato GitHub Actions e non ha provato la VPS.

## Desiderato versus implementato / limiti aperti

- Desiderato: copertura causale affidabile, input verificabili, nessun leakage, ciclo scalabile. Implementato nel ramo laboratorio: regola canonica, letture indicizzate, provenienza distinta e validatore indipendente.
- Non ancora certificato: copie attestate delle candele 15m/1h/4h, attestazione Fase 0 del journal, ricostruzione/verifica dei numeri di rischio e collaudo PAPER con storico reale.
- Sidecar/cicli lunghi: snapshot tardivi vengono ora registrati come `recorded_*_late` ma non valgono per training. Molti simboli successivi possono risultare tardivi finché la decisione usa l'istante d'inizio giro. Cambiare a un istante per decisione altererebbe la freschezza degli input e richiede decisione utente.
- Anti-reingresso: sola osservazione. Nessun blocco attivo e nessuna soglia runtime approvata.
- Confronto LLM: protocollo (campione, `target_r`, orizzonte, costi) da fissare prima di chiamate reali; qualunque spesa/provider richiede autorizzazione.

## Branch, PR e issue verificati

- `diario` prima di questo checkpoint: `82cfea0ffecb1ed28f1b18c0d582822cc140e154`.
- Integrazione laboratorio: `5c2edfcaa4d64a50f0a1496515ec64bb9d8caf87`.
- PR #80 RC84: OPEN/DRAFT, HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`.
- PR #120/#121/#122/#123: tutte OPEN/DRAFT, HEAD rispettivamente `f4f745788e4514d01dc11e11402eb689a2ec7c74`, `5b7403aa333b43d801ca7e28825ea4707f6847b4`, `513448e57747f381e11ce23ab09788d6a41e6cb0`, `c51c7520b35640518baea217404da9657702d4f5`.
- Issue #124 resta OPEN. La correzione P0 è presente nel ramo laboratorio, ma non equivale a deploy/certificazione live.

## Servizi, backup e chiavi — solo evidenze non sensibili

- Nessun controllo live VPS in questa esecuzione; non inferire stato attuale di servizi, runner o timer.
- Backup esterno: ramo `work/extbackup-bot-stopped-20261109` verificato a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`. È **preparato** nel repository; installazione, esecuzione off-host e restore VPS non sono certificati. Un precedente rapporto indiretto su un timer è in conflitto e non risolve la prova.
- Copia cifrata locale della chiave age sul PC: output PowerShell **`ESITO: VERIFICA OK`** e chiave pubblica derivata coincidente. Questa prova riguarda la copia locale cifrata e **non certifica** il backup age, il restore o l'installazione sulla VPS.
- Nessun segreto, token, chiave privata, passphrase o dettaglio d'accesso è stato letto o riportato.

## Eseguito, preparato, non approvato

- **Eseguito/verificato:** avanzamento del solo ramo laboratorio e sua documentazione; SHA/diff/PR/Issue/backup branch controllati; nessuna azione operativa.
- **Preparato:** validazione indipendente da candele attestate, anti-reingresso `enforce`, etichette laboratorio e backup esterno.
- **Non approvato/non eseguito:** attestazione/download candele, training, chiamate provider, attivazione anti-reingresso, merge su `main`, deploy, VPS, servizi, restart, reset, nuovi ordini/run PAPER, API a pagamento o LIVE.

## Blocker, prossime attività e istruzioni di ripresa

1. Ripartire da `integration/brain-unico-20261119@5c2edfcaa4d64a50f0a1496515ec64bb9d8caf87` e dal diario `2026-11-20_claude-copertura-validazione-tesi-esiti.md`.
2. Prima di promuovere: rieseguire offline le suite sullo SHA esatto; misurare in PAPER il tasso `recorded_*_late` e le prestazioni su journal reale senza modificare servizi.
3. Ottenere consenso separato prima di attestare/scaricare candele, usare provider, attivare `enforce`, cambiare parametri, fare deploy o toccare VPS.
4. Mantenere Fail-closed sulle nuove aperture, con ExitService/chiusure indipendenti; preservare integralmente Falco/Toro/Brain, Arena, storici ed EventJournal.
5. In caso di dubbio distinguere sempre: commit di laboratorio ≠ installato/deployato; test riferito ≠ rieseguito; backup preparato ≠ certificato; verifica age PC ≠ verifica VPS.
