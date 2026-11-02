# SuperBot V3 — checkpoint F1 importatore offline, 2026-11-02

## Contesto e autorizzazioni
L'utente comunica «ok ho dato incarico tecnico a cloud»: il documento di incarico per la revisione F1 è stato consegnato a Claude/Cloud, risposta ancora non ricevuta. L'attività è proseguita esclusivamente sul ramo `work/v3-foundations-event-risk-20261102` nella PR #29 DRAFT; nessun deploy, merge, reset, riavvio o scrittura sulla VPS.

## Realizzato nel ramo
- `backend/v3/offline_import.py`: primo importatore **isolato di laboratorio** per copie statiche dei registri PAPER di Falco e Toro. Esclude Brain e le posizioni ancora aperte. Richiede workspace e snapshot espliciti e separati, verifica SHA-256 di stato/trade_history/learning_log, riconciliazione multi-run ed equity contabile, valida eventi prima di aprire SQLite.
- Transazione unica `BEGIN IMMEDIATE`: controlla hash chain preesistente, manifesto SHA di sorgenti e batch, idempotenza per event_id, commit solo a lotto completo; rollback su qualsiasi errore. Manifests per-portfolio immutabili con trigger anti UPDATE/DELETE. Lo stesso snapshot reimportato non genera duplicati; snapshot alterati e record inconsistenti rifiutati.
- `backend/tests/test_v3_offline_import.py` test su copie sintetiche: retry, portafogli isolati, alterazione sorgente, non creare database su audit fallito, rollback su errore SQL, ID preesistente senza manifesto, manomissione hash chain, path e Brain bloccati.
- README V3 e corpo PR #29 aggiornati, mantenendo l'etichetta DRAFT.

## Evidenza CI
https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41499540631
- Python 3.10: **57 passed**.
- Python 3.11: **57 passed**.
Tutti i test riguardano codice isolato e dataset sintetici. Non attestano prontezza operativa, profitto o apprendimento.

## Stato dei dati legacy e limiti
- Audit pregresso su backup post-stop: 348 chiusure Hawk + 186 Bull associate a 14 sessioni; verifica book CASH delle run correnti PASS e Brain 182 aperture/182 chiusure finali/55 parziali, cash PASS dopo distinzione epoche V1/V2. Fonte: workflow https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41497955027.
- **Nessuno dei 534 eventi è stato importato realmente** nel DB V3. Nessun file originale o backup modificato e nessuna creazione dei tre nuovi portafogli PAPER da 1000 USDT.
- Backup locale integrale post-stop `/opt/superbot-v3-backups/20261102T144010Z` verificato, ma copia esterna cifrata di quel preciso snapshot **non ancora attestata**.
- Il modulo non esegue ordini, non importa OPEN, non calcola equity a prezzi correnti, non importa Brain e non fornisce API runtime.
- Claude è incaricato di fornire valutazione tecnica indipendente per import e contabilità; Grok resta disponibile per seconda revisione. Nessuna risposta esterna è ancora stata acquisita in questo checkpoint.

## Prossimo gate
Ricevere e valutare criticamente il rapporto di Claude, aggiustare casi P0/P1, certificare copia esterna post-stop, e soltanto con autorizzazione successiva e senza VPS write pensare a provare un'importazione su copia di backup in un ambiente completamente separato. Non autorizzare merge o deploy con questo checkpoint.
