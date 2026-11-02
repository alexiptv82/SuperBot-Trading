# SuperBot V3 / F1 — nucleo isolato, NON operativo

**Stato:** progettazione e unit test. Nessun deploy, merge, reset, apertura PAPER, chiamata ai provider AI o modifica a dati legacy.

Questa directory contiene due componenti indipendenti:

- `events.py`: giornale SQLite append-only con `portfolio_id` (hawk, bull, brain), `run_id` esplicito, event_id idempotente, catena SHA-256 e trigger che rifiutano UPDATE/DELETE. Non modifica gli storici legacy. Per riaprire una sessione PAPER si crea un nuovo `run_id`, **mai** si cancella un evento.
- `risk.py`: funzione pura `quote_paper_risk(policy, request)` che produce una quota teorica NON eseguibile. Calcola quantità e margine rispettando budget in USDT di perdita attesa allo stop inclusi costi stimati, limite di equity assoluta, margine, rischio aggregato, latched daily lock, qualità dei dati e buffer dalla liquidazione. Se manca qualcosa: NO_TRADE.

Le soglie nei test (1,5% rischio/trade, 6% rischio aggregato, 450 USDT floor) sono **fixture illustrative**; nessuna configurazione definitiva è stata autorizzata. Il limite storico 450 USDT dei classici deve comunque restare invariato fino a nuova approvazione. L'equity PAPER di 1000 USDT per ciascuno dei tre nuovi wallet è la configurazione progettuale confermata dall'utente, non un reset eseguito.

## Limitazioni IMPORTANTI prima di qualunque integrazione

1. Una catena hash e trigger SQLite rilevano molti errori, ma **non** impediscono manomissioni privilegiate: firmare / ancorare hash fuori host, archiviare copie esterne e verificare WAL.
2. Il quoting di rischio non è un executor. Mancano motore prezzi, calcolo mark-to-market, funding storico bidirezionale, gap/slippage stress, modello exchange/tick, rischio reale di liquidazione, correlazione tra simboli, esposizioni lato e lifecycle di ordini; attualmente NON va esposto alle API di trading.
3. Serve un **unico writer** per portfolio e idempotenza persistente dei comandi manuali, con gateway di rischio che separa chiusure da nuove aperture e consente un'uscita anche quando il portafoglio è bloccato.
4. I dati legacy vanno importati in sola lettura e riconciliati per run, trade, PnL e contesto prima di diventare memoria L0/L1. Eventi da utenti non sono automaticamente lezioni valide.
5. Scegliere politiche di rischio versionate e approvate; test di proprietà, replay, ritardi dati, due gruppi shadow comparativi e misure net R/percentuali OOS sono ancora da implementare.
6. Nuove strategie NON si promuovono direttamente dal Brain: ipotesi → walk-forward OOS → shadow → revisione e OK dell'utente.

## CI

```bash
PYTHONPATH=backend python -m pytest -q backend/tests/test_v3_events.py backend/tests/test_v3_risk.py
```

Solo libreria standard Python + pytest nei test. Non importa componenti legacy per evitare side effect.


## Audit di riconciliazione legacy (staging: non è un'importazione attiva)

`legacy_audit.py` legge le **copie offline** dei dati PAPER senza creare o modificare file:
- Falco/Toro: `state_v2.json` e `trade_history.jsonl` rappresentano due viste delle stesse chiusure. Le righe vengono confrontate integralmente (inclusi record di chiusura parziale), assieme al P&L netto e al conteggio. `learning_log.jsonl` serve a verificare la copertura delle registrazioni, non è un terzo elenco di trade da sommare.
- Per una run archiviata, passare esplicitamente `learning_path=/percorso/condiviso/learning_log.jsonl`. L'archiviatore legacy non copia il learning log nelle singole cartelle `archive/`; il campo `run_no` individua le righe della run.
- `plan_classic_closed_events()` produce solo una **lista di eventi in memoria**, con ID stabile anche quando una posizione ha più chiusure parziali e hash della singola riga. Se ci sono anomalie restituisce **zero eventi** e un rapporto `eligible=False`. Non invoca `EventJournal.append()`.
- Brain Free usa `brain.sqlite3`, con schema ed eventi diversi: `audit_brain_snapshot()` conta gli eventi, conferma PAPER/integrità ma riporta sempre `import_eligible=False` finché non avremo definito la riconciliazione contabile specifica.
- I file in produzione vanno lasciati intatti. Per i test con dati reali si usano solo directory di backup già estratte, senza riprendere bot o AI.

**Importante:** l'idoneità del rapporto locale su dati sintetici non certifica ancora il backup VPS, lo storico di tutte le run né la corrispondenza dell'equity. Mancano l'audit sui dati storici effettivi, la riconciliazione delle aperture e dei movimenti di cassa e le proiezioni finali. La nuova memoria non deve considerare la stessa chiusura ripetuta su più file come eventi distinti.


## Esito audit reale sul backup post-stop (2 novembre 2026)

L'audit iniziale `legacy_audit.py` confrontava **tutto** `trade_history.jsonl` con le sole chiusure di `state_v2.json`: sui dati reali il file storico è cumulativo e questo confronto dà un falso allarme di scarsa copertura. La verifica corretta è ora `legacy_multirun.py`, che assegna ogni riga dello storico a una run verificata tramite la corrispondente voce `close` di `learning_log.jsonl`.

Esito su copie già estratte e ferme in `/opt/superbot-v3-backups/20261102T144010Z/restore-test`:
- **Falco:** 348 chiusure riconciliate, run **2–8**, 59 della run corrente, 6 posizioni PAPER lasciate aperte prima dello stop;
- **Toro:** 186 chiusure riconciliate, run **1–7**, 23 della run corrente, 2 posizioni PAPER lasciate aperte prima dello stop;
- **Totale:** **534** chiusure dei classici associate individualmente alle rispettive run senza duplicazioni; stato corrente e relativo sottoinsieme coincidono.
- Metadata legacy `start_equity` compare in alcuni record storici senza essere stato riportato nel learning log: il valore originale viene conservato; una differenza quando il campo è presente su entrambe le sorgenti blocca l'audit.
- `plan_classic_multirun_events()` ha prodotto e validato **534 eventi in memoria**, senza scriverli nel database V3 e senza modificare alcun originale.
- **Brain Free:** SQLite integri; 8.447 eventi di vario tipo, 182 di tipo `trade_closed`, zero posizioni aperte; importazione ancora bloccata fino al contratto di riconciliazione Brain P&L.

Esecuzioni GitHub: [riconciliazione completa](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41493073676), [534 eventi staging RAM](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41493242680); [CI 35/35 per Python 3.10 e 3.11](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41492985727).

**Nessun import persistente eseguito.** Mancano la riconciliazione dei movimenti di cassa, delle posizioni aperte e del P&L Brain; non interpretare questo audit come approvazione economica delle strategie. L'archivio generale post-stop è verificato localmente ma una copia esterna cifrata successiva al fermo non è ancora attestata.


## F1 — contabilità storica congelata: risultati verificati (2 novembre 2026)

Nuovi moduli *solo lettura*:
- `legacy_accounting.py`: quadratura Falco/Toro della run corrente: `cash + margine_open = capitale_iniziale + Σ net_chiusure - fee_apertura_residue`, tolleranza 0,01 USDT. Non è equity mark-to-market, che richiede prezzi freschi; non sostituisce il confronto multi-run.
- `legacy_brain_books.py`: verifica il flusso Brain di apertura, uscita parziale e chiusura finale, evitando di sommare le parziali una seconda volta al `net` cumulativo della chiusura finale. Le identità sono `(epoca, simbolo, id)`, perché il passaggio Brain V1→V2 tramite `experiment_reframed` azzera gli ID ma **non** il saldo. Verifica inoltre `old_cash == new_cash == old_state.cash` e continuità contabile delle epoche.

**Prova su copie offline del backup post-arresto:**
- Falco run 8: cash/margine e 59 chiusure + 6 aperte: **BOOK_CASH_PASS=True**, 348 chiusure su 7 run compatibili.
- Toro run 7: cash/margine e 23 chiusure + 2 aperte: **BOOK_CASH_PASS=True**, 186 chiusure su 7 run compatibili.
- Brain: 8.447 eventi, 182 aperture e 182 finali, 55 parziali, zero aperte: **BRAIN_BOOKS ELIGIBLE=True, CASH_PASS=True, SEGMENT_PASS=True, ENTRY_EXIT_PAIRING=True, ISSUES=NONE**; migrazione V1→V2 senza top-up contabile rilevato.
- Workflow audit reali (nessun file modificato sulla VPS): https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41497955027 (SUCCESS).
- Unit test isolati: **49 PASS Python 3.10 e 49 PASS Python 3.11**, https://github.com/alexiptv82/SuperBot-Trading/actions/runs/41497835752 (SUCCESS).

**Non estendere queste conclusioni:** non abbiamo calcolato il P&L non realizzato con prezzi correnti e né verificato commissioni/funding reali dell'exchange, né la causalità e l'aspettativa economica delle strategie. La V3 non ha ancora importato permanentemente i registri L0: per questo servono snapshot esterno POST-stop certificato, codice import idempotente offline con schema versionato e replay del nuovo journal, prove di backup/ripristino e nuova revisione. 1000/1000/1000 PAPER non sono stati creati.
