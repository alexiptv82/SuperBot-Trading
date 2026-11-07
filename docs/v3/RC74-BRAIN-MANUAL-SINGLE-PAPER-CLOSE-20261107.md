# SuperBot V3 — RC74: chiusura manuale singola Brain, identica a Falco/Toro

**7 novembre 2026 — DRAFT / TESTED OFFLINE / NON DISTRIBUITO.**
Il test pratico del bottone Falco/Toro è stato confermato dall'utente. L'utente chiede lo stesso controllo manuale per Brain (chiudere una posizione PAPER quando il profitto soddisfa, senza forzare la riapertura o chiedere consenso al modello).

## Esperienza utente richiesta

- Percorso `Classici → Brain → Posizioni aperte → Chiudi <simbolo> → Conferma`. Stessa logica visiva e interazione in due passi dei classici.
- Solo **singola posizione** PAPER per clic, non un nuovo comando “Chiudi tutte”. Il server distingue `position_id`, il Brain non condivide chiavi, quote, posizioni o capitale con i classici.
- L'app attende il `close_result.json` della **stessa richiesta**, distingue conferma di ricezione da chiusura realizzata, e aggiorna `Trade → Brain` mostrando commissioni, P&L netto e causa `manual`.
- L'esito diventa **`manual_learning`** (`profit_protection_example`, `loss_reduction_example` o `break_even_example` dal P&L netto). È un esempio annotato, NON una strategia automaticamente appresa/promossa.
- In caso di prezzo non disponibile, esito degradato o altra posizione già chiusa dal monitor, NON creare un secondo close. Mostrare l'errore e ricaricare.

## Codice RC74, opt-in disattivato

- `backend/v3/cutover_gate.py`: `V3_ALLOW_BRAIN_SINGLE_CLOSE=1` richiede simultaneamente `TRADING_MODE=paper`, `DESK_MODE=paper` e `V3_CUTOVER_READONLY=1`. Può superare il blocco HTTP **solo** `POST /api/v3/brain/close`; ogni avvio, reset, altro mutating endpoint resta protetto.
- `backend/v3_api.py`: quando l'opt-in è presente il server accetta soltanto `position_id` di una posizione aperta nella **run Brain configurata**; `all: true` produce HTTP 423. Richiede la presenza reale di un **exit-sidecar indipendente sano**, con lock/lease valido e heartbeat fresco sullo stesso `run_id`. Non è sufficiente il battito del motore AI. Lo stato delle disponibilità viene pubblicato nell'overview come `brain_single_close_allowed`, e nella scheda Brain come `manual_close_allowed`.
- `backend/v3/runner/manual_close.py`: acquisizione della richiesta con lo stesso lock di directory dell'API; una richiesta in `.close_request.work` è sempre completata *prima* della nuova, non sovrascritta o persa. Il vero journaling conserva idempotenza di `paper_close`.
- Interfacce `Classici → Brain` e `V3 → Brain`: abilitano singoli pulsanti **solo quando il server certifica il servizio di uscita**. `Chiudi tutte` non compare durante il cutover; nessuna apertura e nessun avvio automatico.

## Verifiche

- [CI RC74 #42380869478](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42380869478): **181 test backend PASS**, compreso run PAPER sintetico con AI in pausa, sidecar reale, click API singolo, ricevuta, close journal, esito `manual`, rifiuto doppio click, mismatched run/path, owner non attivo e tutti i flag PAPER; **87 test frontend PASS (12 suite)** + build React PASS.
- Nessun test ha scritto nei volumi Singapore originali; **nessun merge né deploy Brain** è stato effettuato.

## Gate di attivazione reale (NON soddisfatti nel 7/11)

1. Brain V3 è ancora la **run PAPER 2.000 USDT preparata e in pausa**, senza posizioni da chiudere. **Non accendere il motore AI e non aprire un trade per provare il bottone.**
2. Il `backend/v3/runner/exit_worker.py` esiste come sidecar, ma **non è ancora installato, attivato e certificato** sulla VPS per la run Brain. Necessario handover “single owner” tra runner storico e sidecar; non avviare due servizi che chiudono le stesse posizioni.
3. Il deploy della futura app deve montare la directory corretta della run e usare **i nomi esatti** `V3_CLOSE_REQUEST_PATH=<dir Brain>/close_request.json`, `V3_CLOSE_RESULT_PATH=<dir Brain>/close_result.json`, `V3_RUNNER_CONFIG_PATH=<dir Brain>/runner_config.json`, `V3_JOURNAL_PATH=<dir Brain>/journal.db`. In passato il web ha avuto nomi `manual_close_request.json` e `manual_close_result.json` non compatibili con il worker: **RC74 li respinge esplicitamente**. Non modificare i mount e i dir originali dei classic.
4. `V3_ALLOW_BRAIN_SINGLE_CLOSE` rimane **DISABLED** sulla web app finché non è dimostrato il nuovo exit worker e collaudo di un close su una **run Brain sintetica isolata**. Un flag da solo non autorizza alcuna chiusura.
5. Al momento del GO, fare nuovo snapshot locale di journaling Brain, preservare lo storico e configurare il rollback; collaudare dal telefono solo dopo posizione PAPER aperta naturalmente dalla run. L'utente decide se/quale posizione chiudere. Portafogli restano Falco 1.000, Toro 1.000, Brain 2.000 USDT PAPER nella nuova run.

**Attuali 6+2 trade legacy e manual-close già operativo Falco/Toro: nessun cambiamento RC74.**
