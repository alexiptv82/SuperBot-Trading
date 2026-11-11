# 11 novembre 2026 — Fable 5.2 SHADOW: staging protetto sulla VPS, 11/11 test PASS

**Intervento confermato su VPS Singapore**: [GitHub Actions #43028485087](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/43028485087) COMPLETED/SUCCESS, job 130549126493. L'utente ha detto «ok procediamo» dopo che gli era stato indicato il prossimo passo: preparare il rilascio Fable inizialmente disattivato, poi affrontare Chiudi ora. Scope mantenuto: **solo test offline + staging isolato, senza attivazione**.

## Lavoro concreto

- PR [Draft #82](https://github.com/alexiptv82/SuperBot-Trading/pull/82), ramo `work/brain-fable-shadow-budget-20261111` già aperto, NON mergiato. Revisione in staging **SHA `6d5ff5d1196c06f13d0c96ca3f401b292da20cc0`**.
- Corretto un difetto importante nel primo Fable shadow: la consultazione sincrona poteva ritardare decisioni DeepSeek. Ora `ShadowFableAnalyst` restituisce **immediatamente lo stesso oggetto `BrainDecision`** e usa al massimo UN worker daemon non bloccante. Se la consultazione è lenta, salta altri consulti e il motore prosegue senza Fable. Ledger SQLite aperto con `check_same_thread=False` e transazioni protette.
- Riepilogo Fable migliorato: ultime **tre candele già validate** per timeframe 15m/1h/4h, catturate nel thread decisionale prima che `CycleBars` cambi. Solo mercato pubblico, no storici/credenziali/risposte private.
- Limite budget invariato: **5 USD/mese UTC** applicativo, prenotazione conservativa PRIMA di chiamata al provider, persistente tra run e restart; max 2/giorno, cooldown 6 ore/asset, dedup. `output_config.effort=low`, `max_tokens=1536`; Fable ID `claude-fable-5-2`, listino ufficiale 8 USD/M input e 40 USD/M output. La spesa totale Anthropic comprende **anche** Falco/Toro ed è diversa dal cap Fable.
- Allargati test a 11 casi, inclusi **risposta Fable volutamente lenta che non blocca DeepSeek**, no consultazioni simultanee e payload con massimo tre candele. **11 passed in 0.14s**, Python AST PASS, zero richieste AI.
- Nuovo script `deploy/scripts/v3-fable-staging-paused-only.py`, eseguito tramite workflow a SHA pinned; sulla VPS ha creato esclusivamente la directory sorgenti `/opt/superbot-v3-fable-shadow-staged-20261111` con revisione esatta. Non ha sostituito `/opt/superbot-v3-rc84-stage` né cambiato unità systemd, envfile, chiavi, utenti, journal, web o settings.
- Log VPS verificati: `FABLE_PAPER_PAUSE_PREFLIGHT=PASS`, `FABLE_SOURCE_STAGED_ISOLATED=PASS`, `FABLE_STAGED_SOURCE_SHA=6d5ff5d1196c`, `FABLE_ALL_FOUR_SERVICE_PIDS_UNCHANGED=True`, `FABLE_NO_SERVICE_RESTART_NO_PROVIDER_CALLS=True`, `FABLE_NO_MANDATE_APPROVAL_NO_UNPAUSE=True`, `FABLE_PAUSED_STAGING_SUCCESS=PASS`.
- Rischio/privacy: Anthropic Fable 5.2 richiede 30 giorni di ritenzione dati salvo autorizzazione specifica per zero-retention; il payload è limitato a informazioni pubbliche di mercato e proposta PAPER (documentazione: https://platform.claude.com/docs/en/models/fable-5-2/overview).

## Stato operativo — NON confondere stage con rilascio

Falco 1.000 USDT PAPER, Toro 1.000, Brain 2.000, **tutti ancora in pausa**, mandato Brain `approved=false`. La dashboard RC84 che l'utente ha confermato funzionante è immutata; i tre motori/exit sidecar non sono stati riavviati. Fable **NON è attivo**, non usa credenziali sulla nuova run e non ha consumato credito. DeepSeek resta unico analista del runner attuale.

**Prossimi passaggi distinti**:
1. Completare/sottoporre a test il ponte «Chiudi ora» solo su singola posizione PAPER dei tre wallet, preservando `V3_CUTOVER_READONLY=1`, controlli writer/exit lease e blocco start/reset/bulk; attualmente la web ha nuovi run mount `:ro` e flag `V3_ALLOW_*_SINGLE_CLOSE=0`, quindi frontend da solo NON basta.
2. Separatamente: eventuale deploy controllato del nuovo Brain code (Fable ancora OFF) con rollback, directory SQLite privata condivisa e chiave Claude al processo Brain; ottenere approvazione esplicita prima di usare budget Fable e avviare trade PAPER. La chiave Claude già aggiornata dall'utente su Falco/Toro NON è stata copiata.
3. Non fare merge della PR #82 e non usare nuove suite CI massive; quota Actions limitata fino al 1 dicembre.

**Nessuna chiamata API a pagamento in questo incarico; nessun nuovo trade.**
