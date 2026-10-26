# Director contracts v1 — interfaccia condivisa ChatGPT / Claude

**Stato: schema implementato e testato localmente, non integrato nel runtime Claude.** Package Python puro `director.contracts`: nessun import di `desk.cli`, rete, API exchange o esecuzione ordini.

## Quattro contratti versionati

- **MarketFrame**: quadro causale di un simbolo, barra *completamente chiusa* e prezzo corrente con timestamp separati, regime e livelli confermati, qualità esplicita. Il validatore rifiuta barre e livelli nel futuro. La qualità OK non ammette buchi.
- **Candidate**: una opportunità di una strategia/versione e un lato LONG oppure SHORT. I due lati non vengono fusi. Timestamp del segnale e prima entrata possibile; stop obbligatorio sul lato sfavorevole; target opzionale, evidenze e costi di giro. `estimated_net_r` e `calibrated_win_prob` sono null prima di evidenza sufficiente; il punteggio soggettivo AI non è una probabilità di profitto.
- **DirectorAdvice**: opinione dell'AI su una opportunità o una posizione. `hold_conviction_0_100` è una convinzione soggettiva sulla continuazione della tesi, richiesta per HOLD/REASSESS e **non** una probabilità calibrata. `review_after_bars` richiede `review_timeframe_ms` e propone solo quando rivalutare, senza sospendere gli stop, il kill switch o il ciclo di sicurezza. Ha `thesis`, `counterthesis` e `invalidate_if` obbligatori; NO_TRADE ha una ragione esplicita. Non è mai un ordine.
- **PortfolioSnapshot**: limite capitale/margine/slot e posizioni reali di Hawk/Bull oppure dei conti Director isolati. È una *fotografia*: se una run legacy supera limiti nuovi il documento la rappresenta, non blocca la lettura. L'arbitro determina se aprire è permesso.

## Convenzioni condivise di esito: una sola fonte

Fixture obbligatoria `fixtures/outcome_cases_v1.json` (8 casi: long/short, TP, stop e TP sulla stessa barra, gap avversi, uscita a tempo e osservazione irrisolta). La funzione pura `outcomes.evaluate_path` le supera. Etichettatore di Claude e replay di ChatGPT devono usare questa stessa funzione, oppure provare esplicitamente la stessa fixture *senza scarti*.

Ingresso alla OPEN della barra successiva al segnale; stop prima dell'obiettivo se entrambi toccati; gap oltre stop al prezzo d'apertura peggiore; TP al prezzo target anche in gap favorevole; TIME solo a orizzonte chiuso e UNRESOLVED se mancano barre. No interpolazioni. Costi `cost_bp_roundtrip` in bp del nozionale, compresi commissioni e slippage: sottrarli una sola volta. Funding baseline 1 bp ogni 8 ore solo long, come nel modello del desk; per funding reale bidirezionale servono dati e versione separata.

`net_r = net_bp / initial_stop_distance_bp`; `gross_bp` e `net_bp` sono prezzi/nozionale, non ROI su margine. MFE e MAE da OHLC includono potenzialmente estremi successivi all'uscita nella stessa candela: indicare sempre il limite dei dati, non inventare un ordine tick.

**Non sostituire la strategia Turbo reale**: il backtest Turbo richiesto usa esattamente `desk.turbo_scalp.strategy.step`; questa convenzione è un riferimento per *etichettare opportunità*, non una riscrittura dello step né un clone di PaperAccount. Nel pilot il conto è soggetto ai limiti PaperAccount, agli slot e al margine disponibili.

## Ownership, compatibilità e sicurezza

ChatGPT possiede `backend/director/contracts/**` e `backend/director/research/**`. Claude può importare v1 per i moduli `runtime`, `labeler`, `arbiter`, `providers` e `pilot` e deve chiedere prima di cambiare semantica. Nessun `backend/director/__init__.py` in questa fase per evitare conflitti sul package condiviso; l'integrazione decide. Cambi semanticamente incompatibili -> v2 e nuove fixture. Nessuna modifica attuale a `desk/cli.py`, `engine.py`, `brain.py`, `strategy_lab.py`, `rule_pool`, frontend, workflow o deploy.

**Test ripetibili:** `PYTHONPATH=backend python -B -m unittest discover -s backend/tests -p 'test_director_contracts_v1.py' -v`. Nessuna dipendenza esterna o chiave.
