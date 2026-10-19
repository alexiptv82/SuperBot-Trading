# Profit Manager — ricerca offline, fase 1

Nessun collegamento a engine, cli, server, exchange o file operativi. Nessun
deploy. Le policy `research-1` sono esempi da simulare, **non soglie approvate**.
Revisore: Claude. Attivazione, rischio e fasi successive: decisione dell'utente
dopo confronto a tre. Hawk resta a 10 slot, Bull a 3.

## Contratti dei componenti

* `liquidable`: vista immutabile di gambe **residue**, quantità e fee residue;
  funding positivo = costo, negativo = credito. `realized_net` include già tutte
  le commissioni/funding delle frazioni chiuse. `reference_margin` è un riferimento
  costante della posizione, non il margine residuo. Floor e picco sono in USD sul
  totale del ciclo di vita; ROI solo descrittivo. PaperAccount resta la verità.
* `features`: close_ms UTC esclusivo, barra utilizzabile se close_ms <= asof_ms.
  Finestra 16 barre per periodo 14, ATR medio semplice (non Wilder), RSI semplice,
  EMA inizializzata sul primo close della finestra; formule esplicite e versionate,
  non sostituzioni silenziose di signals.py. Warmup, buchi o ritardo congelano.
  Regime euristico locale, non modello AI calibrato. OI/L/S assenti, mai finti zero.
* `reversal`: EMA+RSI costituiscono UNA famiglia; rottura della struttura è la
  seconda. Score 0/.5/1 **non è probabilità**; niente Brier prima di calibrazione.
* `machine`: conferme su barre distinte; stato terminale USCITA emesso una volta;
  floor totale USD monotono, nuovo livello valido dalla barra successiva.
  CONGELATO conserva floor/picco e riprende alla prima nuova barra valida.
  Le protezioni preesistenti dell'engine non vengono gestite da questo modulo.
  PARZIALE è solo proposta (disabilitata nei preset), non simulazione di un fill.
* `slot_value`: confronto strettamente maggiore; caller certifica orizzonte e
  valuta confrontabili. Costi di sostituzione solo incrementali non già negli EV.
* `policy_hawk`, `policy_bull`: configurazioni indipendenti e hash canonico.
* `ledger`: eventi deterministici serializzabili, mode=ombra/applied=false;
  nessuna scrittura. Writer append-only, deduplica, retention e backup restano
  a Claude nella futura integrazione. Outcome distinto e successivo all'evento.

## Replay dei dati reali

`PYTHONPATH=backend python -m desk.profit_replay_v1 input.json nuovo-report.json`

Il runner legge soltanto input, crea output esclusivamente se inesistente e
registra SHA-256 dell'input e hash policy. Non invoca gli altri script operativi.
Formato JSON richiesto (nessun dato privato va committato nel repository pubblico):

```
schema: 1
mode: "paper"
run_no: 3 per hawk, 2 per bull
code_version: SHA del motore all'origine dei dati
policy: tutti i campi di dataclasses.asdict(research_policy()), scelti esplicitamente
costs: {fee_rate, spread_fraction, slippage_fraction}
interval_ms: 900000
max_age_ms: tolleranza esplicita
positions: [
  {position_key, opened_ms, side: 1 oppure -1, reference_margin,
   baseline_net_usd: opzionale, descrittivo e mai feature,
   bars: [{close_ms, open, high, low, close}, ...],
   snapshots: [{asof_ms, legs: [{entry, qty, open_fee}, ...],
                funding_paid, realized_net}, ...]}
]
```

Snapshot strettamente cronologici, dati contabili conosciuti a `asof_ms`;
warmup può precedere l'apertura. Includere provenienza e verificare separatamente
che run/posizioni/eventi siano coerenti. Il runner non può dimostrare che uno
snapshot fornito dal produttore non contenga già informazioni future.

**Limite dichiarato:** questo è replay delle decisioni, non backtest esecutivo.
Il netto al segnale NON è un prezzo di esecuzione. Non calcola rendimenti PM,
fill della barra successiva, PM-A, impatto A-D, bootstrap o promozione. Il runner
PM-A preesistente resta intatto. Il confronto esecutivo richiede dati validati,
cronologia completa delle modifiche e un adapter revisionato con Claude; non
si ricostruiscono DCA/parziali passati dallo stato finale. Nessun risultato su
Hawk run 3/Bull run 2 dichiarato finché gli input non sono disponibili.

## Verifica e rollback

`cd backend && python -m unittest desk.test_profit_v1 -v`

Test su contabilità long/short, costi e credito funding, DCA/partials, immutabilità,
look-ahead (anche mutazione intenzionalmente errata), transizioni, isteresi,
monotonia randomizzata, congelamento, registro, replay e isolamento I/O.
I test non costituiscono validazione della redditività o dell'integrazione live.
Rollback di questa fase: scartare il ramo; nessun servizio o dato da ripristinare.
Prima della futura integrazione serviranno backup verificati e autorizzazione.
