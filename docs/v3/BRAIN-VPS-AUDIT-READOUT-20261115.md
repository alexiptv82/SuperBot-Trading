# Brain PAPER — Lettura audit VPS 15 novembre 2026

Fonte: quattro schermate Termius inviate dall'operatore il 15/11/2026, output parziale di `v3-brain-audit-readonly-20261115.sh`. **Nessun accesso diretto alla VPS da questa revisione.** Tutte le cifre sotto sono trascritte dalle schermate; non sono state riestratte autonomamente dal journal.

## Numeri confermati dallo screenshot
- Run: `brain-v3-paper20261111`; ultimi eventi 15/11 13:01 UTC; 394 eventi, 336 `brain_decision`, 30 `paper_open`, 27 `paper_close`.
- Decisioni: 86 `NO_TRADE/DRAFT` dal modello, 1 `NO_TRADE/REJECTED/ai_unavailable`, **199** `NO_TRADE/RISK_REJECTED` e **50** `OPEN/APPROVED`. Risultano **20** approvazioni in piu' delle aperture: non attribuire la differenza al modello senza identificare errori del commit/serializzazione, pause e controlli di rischio dopo l'AI.
- Leva: tutte le 30 aperture 20x, stop relativo 0,40%–0,91%, mediana 0,74%. `leva_ridotta_dal_rischio=50`; `peer_osservati=49`.
- Chiuse totali: 27; 48% vinte; netto **+227,17 USDT**; media **+8,41 USDT**; profit factor 1,20; commissioni **254,36 USDT**. Il profitto netto comprende gia' le commissioni (non sottrarle una seconda volta).
- LONG: 2 chiusi, entrambi persi, **−137,42 USDT**.
- SHORT: 25 chiusi, 52% vinti, **+364,59 USDT**.
- Chiusure: 14 `stop`, netto **−1.111,60 USDT** (−79,40 di media); 13 `take_profit`, netto **+1.338,77 USDT** (+102,98 di media).
- Regimi SHORT: `EXPANSION` n=16, 31% vinti, **−221,20 USDT**; `TREND_DOWN` n=6, 83% vinti, **+400,69 USDT**; `RANGE` n=3, 100% vinti, **+185,11 USDT**. Su 16 SHORT in EXPANSION, circa 11 perdenti.
- Simboli: BTC SHORT n=8, 75% vinti, **+461,95**; ETH SHORT n=5, 20% vinti, **−292,80**; BNB SHORT n=4, 25% vinti, **−173,06**. Altri simboli devono essere analizzati dal journal, senza attribuire le differenze a regime/simbolo senza controllo temporale.
- Drawdown massimo su PnL **realizzato**: 364,72 USDT. Tre SHORT aperti: LINK (-18,97), BTC (-2,88), BNB (+10,64); totale flottante **−11,22** (prezzi pubblici, istantanea, non definitivo). La combinazione realizzato+flottante alla rilevazione era circa **+215,95 USDT**, prima degli eventuali costi di uscita delle posizioni aperte.
- Heartbeat runner: `running`, daily_loss_pct 8,6, daily_loss_level `ok`, errori `risk_changed_after_ai`. Exit heartbeat: `healthy`. Il sito mostra `correzione_RO_presente=0` (patch non presente nel web runtime); manca nelle schermate l'esito dei campi `lock_O_RDWR`, `lock_O_RDONLY`, `uscite_sane_viste_dal_web` e `chiusura_brain_consentita_vista_dal_web`, quindi la diagnosi definitiva del pulsante resta da completare.

## Ipotesi da testare senza modificare l'operativo

1. **Espansione ad alto rischio per SHORT:** testare un osservatore FRRD, non un veto immediato. Misurare separatamente SHORT in EXPANSION con rimbalzo locale rispetto a continuazione ribassista usando candele chiuse al momento dell'ingresso; confrontare uno stesso insieme di timestamp e simboli e un secondo campione futuro. Lo stato EXPANSION non prova da solo una inversione.
2. **Sele­zione e gestione rischio:** misurare se gli stop 0,40%–0,91% producono perdita per normale rumore rispetto all'ATR 1m/15m/1h, per simbolo e regime. Vietato ritarare stop o leva sul campione di soli 27 trade.
3. **Approvazioni non eseguite:** ricostruire 50 `OPEN/APPROVED` e collegarle per `decision_event_id` alle 30 `paper_open`, e poi cercare `risk_changed_after_ai`, `risk_rejected_after_ai` e `brain_paused` nei log. L'osservatorio proposte registra il lato pre-risk, ma non la motivazione granulare del gate.
4. **Vantaggio dell'AI:** confrontare Brain con un baseline SHORT selezionato agli **stessi timestamp, simboli, stop, margini e finestre di detenzione**; i controlli a ingresso orario del rapporto Fable non sono un confronto perfettamente appaiato.
5. **Pulsante Chiudi:** completare la porzione iniziale del report web (mount RO, file lock, flag `_brain_single_close_ready`); la presenza di `correzione_RO_presente=0` suggerisce il fix non installato, ma da sola non dimostra la causa operativa.

## Stato delle autorizzazioni

Nessun deploy, merge, riavvio o modifica al risk gate effettuati. Questo file e' solo un resoconto di un audit prodotto dall'operatore su PAPER. Nessuna prova live eseguita da GitHub. Il problema del pulsante e i rigetti post-AI vanno confermati prima di ogni installazione.
