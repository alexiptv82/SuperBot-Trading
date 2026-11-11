# Brain V3 — Claude Fable 5.2, secondo cervello SHADOW (PAPER, opt-in)

Data: 11 novembre 2026. Stato: **implementazione offline testata, non distribuita e non abilitata**. DeepSeek rimane analista principale; `BrainEngine` e Risk Manager sono invariati.

## Specifiche e costi verificati

- Modello Claude API: `claude-fable-5-2`.
- Prezzi listino Anthropic (11/11/2026): **8 USD / milione token input**, **40 USD / milione token output**.
- Integrazione senza cache API, fast mode, tool o streaming. `output_config.effort=low`, `max_tokens=1536` include testo e ragionamento. Prompt molto corto e limitato a 6.400 byte di payload.
- **Tetto applicativo Fable: 5 USD per mese UTC**, in un DB SQLite condiviso `/opt/superbot-v3-fable-ledger/fable_budget.db`, separato da `budget.db` di DeepSeek. Si applica alla consulenza Fable, NON al costo complessivo dell'account Anthropic (Claude usato anche da Falco e Toro). **Il saldo della Claude Console è condiviso**.
- Ogni richiesta Fable prenota su disco PRIMA della chiamata un importo molto prudente, equivalente a `2 × byte JSON × 8 + 1536 × 40` microUSD; il totale di queste prenotazioni è controllato atomicamente con `BEGIN IMMEDIATE` e non può superare **5.000.000 microUSD** nel mese UTC, nemmeno su riavvio, contemporaneità o nuova run Brain. Prenotazioni **non rimborsate** su errori/timeout, scelta conservativa. Il dato di spesa stimata effettiva da `usage` viene registrato separatamente quando disponibile, non estratto in log. Non confondere prenotazione massima con fattura Anthropic.
- Ulteriori protezioni: massimo **2 consultazioni al giorno UTC**, cooldown **6 ore per coppia**, 1 richiesta per segnale univoco, nessun retry automatico.

Documentazione prezzi e ID: https://platform.claude.com/docs/en/models/fable-5-2/overview e https://platform.claude.com/docs/en/build-with-claude/effort

## Quando interviene (solo dopo la decisione primaria DeepSeek)

- Cambio di regime osservato tra due analisi dello stesso asset: `trend_transition`.
- Proposta `OPEN` in regime `VOLATILE`.
- Proposta `OPEN` con leva >= 40×.
- Proposta `OPEN` con confidenza <= 0,62.

Se non succede nulla di particolare, non viene chiamato. Fable riceve un JSON minimale di prezzo/regime/simbolo, direzione, leva, confidenza, stop e prezzo proposto, **non** lo storico completo, le chiavi, la memoria privata, il prompt di DeepSeek, né ordini reali. Il suo output è limitato a `assessment`, `risk_code`, `summary` e salvato nel ledger privato; nessun testo arbitrario di Fable può diventare ordine, rationale del motore o decisione del Risk Manager.

**Protezione fondamentale:** `ShadowFableAnalyst.analyze(...)` restituisce lo stesso oggetto `BrainDecision` prodotto da DeepSeek, senza alterarne kind, proposta, prezzo, stop, size, status o risk quote. Se Fable, le API, il budget o il database falliscono, la decisione DeepSeek resta invariata. Chiude/gestisce stop SOLO il sidecar delle uscite Brain; Fable non interviene.

## Protezione della latenza e qualità del contesto (revisione successiva)

Il primo mock aveva una consultazione Fable **sincrona**: questo avrebbe potuto ritardare la validazione dei prezzi del ciclo DeepSeek. Prima del rilascio è stato corretto: `ShadowFableAnalyst` avvia al massimo **un worker daemon** indipendente, restituisce immediatamente l'identico oggetto `BrainDecision` e salta nuove consultazioni mentre la precedente è ancora in corso. I timeout/API falliti **non ritardano il trading PAPER** e non alterano ordini o stop. La prenotazione del costo avviene dentro il worker prima della richiesta di rete; le chiamate duplicate sono bloccate atomicamente nel ledger. Se il processo viene interrotto, l'eventuale prenotazione resta conteggiata nel tetto mensile.

L'opinione Fable vede inoltre un'istantanea **massimo tre candele già chiuse** per timeframe 15m/1h/4h, con OHLCV compatti, estratte dallo stesso CycleBars validato usato da Brain. Non riceve storico privato, segreti, dati utente o testo integrale DeepSeek. Lo snapshot è acquisito subito per evitare letture concorrenti delle candele dopo un nuovo ciclo.

**Privacy:** secondo la pagina ufficiale Fable 5.2 il modello richiede ritenzione Anthropic di 30 giorni e non offre zero-data-retention senza autorizzazione specifica. Si inviano quindi solo dati pubblici di mercato e la proposta PAPER. La consultazione resta disattivata per impostazione predefinita finché l'utente non autorizza il rilascio e la spesa.

## Staging isolato sulla VPS (senza attivazione)

Il nuovo script `deploy/scripts/v3-fable-staging-paused-only.py` prepara, soltanto dopo test e pin SHA, una copia di sorgenti GitHub in `/opt/superbot-v3-fable-shadow-staged-20261111`. Verifica tre pause PAPER, mandato Brain non approvato e gli stessi PID dei quattro servizi prima e dopo. **Non** modifica la directory software del runner esistente, unità systemd, file env, configurazione, dashboard o budget; non installa chiavi Fable e non chiama modelli. Un esito positivo prova soltanto la presenza della revisione in staging, NON il deploy operativo.

## Stato di attivazione

- Nuovo modulo: `backend/v3/runner/fable_shadow.py`.
- Wiring opt-in: `backend/v3/runner/wiring.py`.
- **Default OFF.** Serve contemporaneamente `BRAIN_FABLE_SHADOW=1`, `BRAIN_FABLE_BUDGET_APPROVED=1` **e** servizio `exit_mode=sidecar`, `DESK_MODE=paper`. Con qualsiasi flag mancante, zero DB Fable e zero chiamate; il comportamento Brain rimane identico al precedente.
- Richiede `ANTHROPIC_API_KEY` a runtime: per il rollout, riusare in modo protetto il token Claude già validato sui nuovi Falco/Toro tramite `EnvironmentFile` dedicato nel servizio **Brain PAPER**; nessuna credenziale deve essere copiata nel repo, in GitHub Actions, in chat o nei log. La chiave non è presente nell'ENV del Brain fino al futuro deploy autorizzato.
- Prima di attivare, predisporre la directory privata `/opt/superbot-v3-fable-ledger` con mode 0700, accessibile in scrittura solo al Brain runner (via `ReadWritePaths` systemd e proprietà corretta); file SQLite 0600. Non usare una directory dentro la singola run per il budget: altrimenti il limite mensile potrebbe azzerarsi sostituendo run.
- Non cambiare `runner_config.json` né mandato/policy hash per questa integrazione. Conservare 2.000 USDT PAPER Brain, 1.000 Falco e 1.000 Toro, 20–50× Brain, floor 450, NO_TRADE valido.
- Non fare deploy/merge/restart/sblocco in questa PR. La precedente richiesta utente autorizza l'integrazione come codice e il limite spesa come obiettivo, **non** l'approvazione del mandato Brain né la riattivazione degli ordini PAPER.
- Prima del rollout: test runner split con flags off/on, verifica che la directory e il servizio siano in PAPER, vista Dashboard per budget/consigli, audit chiusure manuali; **ottenere consenso separato** per attivare la spesa Fable e i bot. Con tutti i motori ancora in pausa non deve partire alcuna chiamata modello.

## Osservabilità e apprendimento

Registro SQLite indipendente append-only: `fable_observations` per regimi, `fable_reservations` per budget/trigger, `fable_results` per esito, codice rischio, sintesi e stima consumo da token API. Le opinioni vengono archiviate per confrontarle nel tempo con gli outcome dei trade PAPER usando giorno/simbolo/run/contesto. Questa prima fase è **shadow**: non dimostra un incremento di rendimento e non modifica i trade; la valutazione controfattuale/learning automatico richiederà un'analisi successiva separata.

## Collaudo eseguito

[GitHub Actions 43025542149](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43025542149): **9/9 test offline PASS** su schema SQLite, cap condiviso tra run e riavvii, no request su default OFF, dedup, timeout, output JSON rigoroso, parsing usage, cambio regime e identità decisione DeepSeek. Python AST valido. Nessuna chiamata ai provider, zero consumi AI, nessuna connessione VPS. Non equivale a un collaudo in runtime PAPER reale, che è fase successiva autorizzata.
