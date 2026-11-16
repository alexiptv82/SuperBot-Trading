# SuperBot V3 — AI Arena: isolamento provider e tre portafogli (16 novembre 2026)

**Ramo isolato:** `work/brain-arena-provider-isolation-20261116`  
**Stato:** libreria di connessione e piano puro implementati; **runner e app non modificati da questo intervento**. Nessun deploy, avvio, pause, merge o GitHub Actions.

## Evidenza delle API — screenshot Termius alle 11:24

- Qwen `qwen/qwen3.7-plus`: `QWEN_JSON_response_status=PASS_NO_TRADE_JSON`, risposta con `finish_reason=stop`, 50 token input, 25 output, nessun token di ragionamento, schema JSON rigoroso e ragionamento disattivato **solo nel test diagnostico**. `QWEN_JSON_RESULT=QWEN_VERIFIED_NOT_ACTIVATED`.
- MiniMax `minimax/minimax-m3.1-flash`: gia' `PASS_NO_TRADE_JSON` nel test OpenRouter, 261 input e 16 output.
- Credenziali conservate localmente sulla VPS in `/etc/superbot-brain-ai-arena/openrouter-keys.json` con permessi 0600, cartella 0700, due chiavi distinte e limite di spesa 2 USD per chiave.
- I due modelli sono accessibili e rispondono al test sintetico; **non** e' ancora dimostrato che producano decisioni OPEN valide, che Qwen con ragionamento attivo dia JSON, o che eseguano PAPER correttamente.

## Codice nuovo

- `backend/v3/arena/openrouter_transport.py`: trasporto con selezione rigida del provider, verifica segreti root-only, endpoint OpenRouter fissato, nessuna azione di trading. **Disabilitato** se `allow_inference` non e' esplicitamente `True`, `DESK_MODE` non e' `paper`, o manca l'ulteriore `spending_gate(provider)` separato. Rifiuta richieste con strumenti, chiavi in payload, streaming e model ID errato. Prima di una chiamata controlla `GET /key` e nega inferenza se limite per chiave supera 2 USD o residuo sotto 0,03 USD. Nessun retry e nessun fallback incrociato.
- `backend/v3/arena/trial_plan.py`: definisce un **piano non eseguibile** per tre wallet di 2.000 USDT, run ID differenti, file SQLite `journal.db` e `budget.db` distinti, flag `enabled=False` e `approved=False` per ogni AI. Non scrive filesystem e non avvia processi.
- `test_openrouter_transport.py` e `test_trial_plan.py`: test sintetici di negazione per mode diverso da PAPER, provider errato, spesa non consentita, isolamento credenziali, nessuna rete se disabilitato, unicita' delle run, capitale totale 6.000 USDT e piano senza effetti collaterali. Test creati, **non ancora eseguiti in CI o VPS**.

### Perche' serve una separazione fisica delle run

Nel motore V3 esistente il valore interno `portfolio_id='brain'` e' un contratto chiuso e il database ha CHECK di `brain/hawk/bull`. Per questo il progetto non deve trasformare Qwen/MiniMax in `hawk` o `bull` né cambiare il database principale: **ogni istanza avra' un proprio database, cartella, run_id, saldo, budget e servizio uscite**, mantenendo `portfolio_id='brain'` all'interno del suo journal. L'ID esposto all'app sara' distinto (`deepseek`, `qwen`, `minimax`).

L'attuale `DeepSeekL5Analyst` e `BrainEngine` hanno codici di provenienza e autorizzazione specifici (`deepseek:analysis`, `originating_ai=deepseek`, `portfolio_id=brain`). **Non basta cambiare la chiave API**: prima di attivare Qwen/MiniMax bisogna adattare in un ramo isolato il percorso delle decisioni, il mandato di rischio, la persistenza dei journal e la gestione delle uscite con provenienza corretta, test di isolamento e rifiuto di qualsiasi fallback DeepSeek. Il semplice trasporto nuovo NON e' ancora cablato a un runner.

## Condizioni di partenza del confronto di 14 giorni

1. La run corrente DeepSeek `brain-v3-paper20261111` rimane un archivio storico e non viene azzerata o modificata in silenzio. Decidere con l'utente il `T0` comune e cosa fare delle eventuali posizioni ancora aperte.
2. Creare tre nuove run PAPER, ciascuna con **2.000 USDT effettivi di capitale iniziale**, stessa lista di 8 simboli, stessi indicatori e rischio; nessun privilegio diverso per i nuovi modelli. Fino al collaudo tutti `enabled=False`.
3. Tre contatori costi separati e tetti giornalieri che NON permettano di esaurire in poche ore i 2 USD di ciascun account; 2 USD possono non coprire 14 giorni H24. Niente acquisti automatici.
4. Eseguire prove corrette di JSON con ragionamento comparabile e di formati OPEN; poi test a mercato sintetico, risk, stop, uscite/chiusura manuale, recovery e gestione pause.
5. Quando si passa al runtime: acquisire uno snapshot identico di candele *chiuse* e distribuirlo alle tre AI, registrando decisione, tempo risposta, costi, rifiuti pre/post rischio e ordini PAPER in journal separati. Nessun percorso per ordini reali.
6. Falco e Toro: **non eliminare**; controllare prima posizioni aperte e uscite, mettere in pausa soltanto le nuove aperture, mantenere backup. La UI Arena puo' nasconderli come preferenza senza fermarli automaticamente.
7. UI `work/brain-ai-arena-ui-shadow-20261116`: esiste un'anteprima che mostra DeepSeek e stati Qwen/MiniMax, ma non e' pubblicata e non contiene ancora una sorgente live affidabile per gli sfidanti. Non inventare PnL finche' non esistono i journal.

## Stato attuale

**Disponibilita' API: 2/2 verificata.**  
**Provider trasporto: implementato su ramo, non avviato.**  
**Piano wallet: implementato, non eseguibile, nessun journal creato.**  
**Tre runner PAPER simultanei: non ancora realizzati.**  
**Test 14 giorni: NON iniziato.**

Nessuna modifica al Brain in funzione, a Falco o a Toro.
