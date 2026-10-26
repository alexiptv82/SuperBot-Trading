# Brain upgrades — contratto approvato, 26 ottobre 2026

Base rule-pool33427f596edcbf80a7f73e94fdeffb39fac81ddd. Branch richiesto
work/brain-pilot-v1 avanzato fast-forward alla base (vecchia punta già integrata,
nessuna riscrittura o perdita). Solo sviluppo/review: NESSUN deploy autorizzato
per questi upgrade. Runtime documentato resta2c977c46.

## 1 → 2: confronto e tesi verificabile
Prompt e parser richiedono bull_scenario, bear_scenario e verdict, stringhe non
vuote, per aperture e averaging. Il confronto è una singola chiamata allo stesso
modello, non due agenti indipendenti. Nessuna quota di LONG/SHORT imposta.
Invalidation è oggetto con description non vuota, level JSON numerico finito e
positivo (bool/stringhe/NaN/Inf rifiutati), timeframe15m/1h/4h/1d, condition
close_below/close_above. Chiusure protettive, parziali e move_stop NON richiedono
questi campi d'ingresso. Il parser non verifica semanticamente la qualità delle
due tesi: il beneficio va misurato, non presunto.

## 4: ATR e conservazione rischio
ATR14(1h) dal helper desk.signals.atr: media dei14 true range precedenti su barre
chiuse (stessa convenzione del repo, non smoothing Wilder). Prompt riceve ATR
assoluto, riferimento1.5ATR/prezzo e minimo.8ATR/prezzo. Stop strutturali più
ampi ammessi entro cap8% già esistente. Minimo percentuale fisso.25% sostituito
dal pavimento ATR per i nuovi ingressi. ATR nullo/non valido impedisce esposizione.
Parser porta stop iniziale troppo stretto al minimo; ricalcola R/R, senza spostare
automaticamente il TP. Dimensionamento a rischio costante, costi inclusi, riduce
notional/quantità in proporzione al nuovo rischio per unità (non aumenta rischio
capitale). Entry ripete il controllo con ATR da barre chiuse all'esecuzione e
riverifica liquidazione/RR. Journal open riporta stop richiesto/applicato e flag.
Averaging non può allargare lo stop esistente: se non soddisfa.8ATR, è rifiutato.

## 3: dati pubblici opzionali e persistenti
context.py usa endpoint pubblici Bitget v2 current-fund-rate, history-fund-rate,
open-interest; Alternative.me/fng. Nessuna key di trading né nuova dipendenza.
- funding_recent_samples:3 osservazioni correnti distinte a bucket15m, ts_ms e
  kind=observed_current; funding_settled:3 regolamenti effettivi con fundingTime
  e kind=settled_payment. Non confondere i due orizzonti.
- Tre campioni >.0005 (0.05%) indicano pressione di pagamento LONG persistente,
  non inversione certa. Interpretazione simmetrica negativa; non è un veto.
- OI confronta quantità in asset base, non USD influenzati dal prezzo. Storico
  locale fino8h, riferimento più vicino a4h con tolleranza15m; pubblica timestamp
  effettivo e oi_elapsed_ms. Manca base? oi_change_4h_pct=null, non zero.
- Fear&Greed una sola volta nel blocco btc_macro, fonte/attribuzione Alternative.me
  esplicita. Nessun valore per altcoin/oro/argento. Cache fino al prossimo update,
  timestamp originale e osservazione; dato >48h non disponibile.
- Snapshot cache in state.market_context, stesso commit SQLite dello stato Brain;
  nessuna lettura/scrittura degli storici dei bot. Sampling deduplicato ai restart.
  Timeout2s per richiesta, budget avvio richieste10s/ciclo, rotazione simboli se
  budget esaurito. L'ultima richiesta può aggiungere fino2s. Record stale esclusi
  dalla vista; errori API non impediscono gestione o decisione con dati tecnici.

## 5: decisione esplicita utente DAILY STOP20%, non12%
Portfolio migra anche Limits ripristinati dal DB a.20; non basta il costruttore.
Metadata brain_daily (policy_version2) conservati nel medesimo snapshot atomico:
UTC day, start_equity, stopped, stop_logged. Alla prima migrazione conserva il
day_start_equity già salvato se è dello stesso giorno, senza reset conto/storico.
Equity mark-to-market include posizioni aperte secondo PaperAccount (costi
apertura già detratti; funding/fee uscita effettivi entrano al realizzo).
Equity <=80% del riferimento fa scattare latch; recupero intraday o restart
non sbloccano. Giorno UTC successivo nuova base sul capitale rimasto. Clock che
arretra non sblocca. Dati posizioni mancanti bloccano nuove esposizioni e rinviano
il rollover; management continua. La protezione assoluta450 rimane invariata.
Journal daily_stop emesso una volta per giornata nello stesso commit del latch.
Stop controllato prima di esecuzioni, dopo ogni barra e prima di nuove proposte;
nessuna apertura/averaging oltre soglia, chiusure/stop/TP e AI management attivi.

## Compatibilità e rollout da revisionare
State version1 rimane leggibile; nuove chiavi additive, nessun reset o riscrittura
del trade_history. Invalidation delle vecchie posizioni può rimanere stringa come
memoria: non causa liquidazioni. Pending legacy di nuova esposizione privi del
nuovo contratto vengono annullati e registrati (legacy_pending_exposure_rejected);
pending protettivi conservati. Confronti storici devono distinguere prompt_version
brain-pilot-v1-upgrades-v1 e policy daily20% dal precedente12%.

Dockerfile aggiunge smoke import/policy check, mantiene numpy e standard library.
CI offline Python3.10/3.11 e build Docker su3.11, smoke container senza rete/key.
Il workflow di PRIMA installazione non sostituisce un container esistente; il
workflow repair daily ha allowlist/flat-only e NON va riutilizzato per upgrade.
Prima di un futuro deploy con posizioni: review Claude, backup verificato e
percorso upgrade specifico che preservi DB/outbox/budget e pianifichi rollback
compatibile con nuovo latch. Trigger rimangono invariati/disarmati su questo ramo.
Nessun cambiamento Hawk/Bull, vecchio pilot, credenziali, limiti API budget o leva.
