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
