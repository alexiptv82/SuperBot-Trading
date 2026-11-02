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
