# 2026-11-02 — Proposta SuperBot V3 Cognitive Trading System (IDEA DA VALUTARE)

L'utente ha proposto una nuova architettura per la ristrutturazione SuperBot: un cervello centrale strategico con DeepSeek analista H24 e Claude revisore selettivo, una schermata app unica e tre portafogli PAPER distinti: Falco 1000 USDT, Toro 1000 USDT, Brain 2000 USDT.

## Design desiderato
- Falco e Toro: esecutori per regole meccaniche, consulenza AI facoltativa; restano indipendenti e producono dati di decisione, trade, segnali, contesto, errori e risultati.
- Brain portfolio: esecutore governato dal cervello AI, capace di scegliere fra strategie validate (o NO_TRADE) in base a regime, volatilità, trend, volume, funding, OI, notizie e contesto; non deve perseverare in una strategia inappropriata, ma non deve inseguire ogni rumore o cambiare solo dopo una perdita.
- Brain osserva i due classici in sola lettura e la cronologia delle decisioni manuali del proprietario, inclusi take-profit per liberare slot. Il cervello unifica la memoria ma non modifica silenziosamente le regole dei classici né mescola portafogli.
- App unica: tre wallet, equity, posizioni, margin, PnL netto e storico; per ognuno pausa/riprendi, apertura PAPER manuale, chiusura singola/parziale, livelli protettivi con ricevute e conferme; pannello motivazioni AI, regime, esperimenti, performance confrontate e costi modelli.
- Memoria verificabile: eventi append-only con provenienza e timestamp (osservato vs inferito vs ipotesi), lezioni personali, casi di perdita in regime simile, controfattuali; distinguere correlazione da causalità, test walk-forward e fuori campione, costi reali simulati e calibrazione dei risultati. Non chiamare tutto questo riaddestramento del modello.
- Rischio NON delegato al modello: modalità PAPER; limiti per trade, posizione, portafoglio, esposizione correlata e concentrazione su ADA ecc; protezione minima 450 USDT dei classici salvaguardata; stop, kill-switch, limiti operativi; NO_TRADE valido, nessuna strategia non provata promossa automaticamente.
- Confronto Brain vs classici: stessa finestra dati, costi, regime e rischio parametrizzato, metriche comparabili (return sul capitale, max drawdown, profit factor, fee, exposure, risultati per regime); il Brain può osservare i classici ma non considerare loro esiti come verità automatica.
- Continuità storica: fermare bot PAPER dopo messa in sicurezza, backup tutto, nuove run contabili 1000/1000/2000 solo a collaudo e OK; vecchie run e dati immutati.

## Riuso esistente verificato su GitHub
- `backend/desk/learning.py` log append-only, `backend/desk/brain.py` appunti periodici condizionati.
- `backend/director/brain_free/prompt_builder.py` include ultimi 10 trade e non riaddestra il modello; `backend/director/brain_free/reports.py` già espone confronti classici descrittivi e read-only, **non un input operativo**.
- PR #26 LONG shadow app/read-only DRAFT e PR #27 chiusura manuale per ID DRAFT, non mergiate.
- `work/classics-teaching-completion-20261031` registra manual teaching consultivo, training_applied=False.
- `work/brain-completion-20261031` motore Free V2 con valutazione AI e vincoli execution.
- Tutto ciò NON è attualmente un cervello condiviso completo né apprendimento autonomo comprovato.

## Stato e mandato
Questa è una **proposta in discussione**, non ancora autorizzazione a fare deploy/merge/reset/restart/ordini. Priorità sicurezza dati storici e ricerca post-mortem. Pool già stop e backup. Nuova architettura da definire e collaudare separatamente.
