# 2026-11-23 — Richiesta del proprietario: interrompere test Brain Unico e rivalutare profilo troppo conservativo

## STATO (NON scambiare richiesta con esecuzione)
- Il proprietario riferisce **due posizioni aperte a leva 2×** e giudica il profilo B troppo conservativo per 2.000 USDT PAPER. Vuole bloccare nuove aperture e **chiudere da sé manualmente** le posizioni, mantenendo exit service attivo.
- ChatGPT ha indicato `sudo sh /root/brain-unico-avvio/80-paper.sh pausa`; **non esiste ancora conferma** che sia stato eseguito, né che le posizioni siano chiuse. NON dichiarare runner fermato o posizioni chiuse senza evidenza VPS.
- Il proprietario chiede una nuova strategia con opportunità LONG e SHORT, scelta libera dell'AI, fino a 4 slot se giustificati, maggior leva/rendimento ed enfasi su protezione dei profitti (difetto lamentato di Falco). PAPER soltanto, nessuna modifica o riattivazione senza OK.

## Analisi statica confermata su GitHub, branch integration/brain-unico-20261119 @ 9b153278
- `runner_config_brain_unico_paper_b.json`: capitale 2000, max_loss_fraction .01 ($20 a stop stimato), max_open_risk .04 ($80), posizione max 20% equity ($400 margine), max margine totale 50% ($1000), floor 1600, leva consentita 1–30x, roundtrip cost buffer 16bp, daily stop 4%. Con sole 8 crypto, ciclo 60m.
- `brain_f2/engine.py` `_apply_risk_gate`: se stop troppo vicino a liquidazione o rapporto rischio/margine eccessivo, tenta di abbassare la leva proposta da AI fino al minimo 1x e aggiunge `risk:leverage_adjusted`. Le 2x osservate non dimostrano che DeepSeek le abbia chieste; richiedere requested leverage, approved leverage, stop distance e quote per le due posizioni.
- `risk.py` quote: dimensione è minimo tra rischio disponibile e budget margine, stop stimato include cost buffer e non garantisce loss massimo su gap/liquidazione; semplice aumento minimo leva può bloccare i trade oppure aumentare fortemente il rischio.
- `exit_policy.json` take_profit_r=2, max_hold_hours=24, stop_slippage_bp=2; verificare se profit protection/trailing già attiva prima di richiedere implementazione, non presumere presente.
- Un esempio matematico con margine $400: 2x = $800 notional, movimento favorevole 1% -> +$8 lordi; 20x = $8000 notional, 1% -> +$80 lordi ma anche -$80 con movimento avverso 1%, prima delle fee. Quattro margini $350 a 20x sono $28.000 notional: -1% correlato -> -$280 lordi (14% di equity); pertanto occorre limite rischio aggregato/correlazioni.

## Direzione per Claude (proposta, NON parametri approvati)
1. Prima osservare e registrare stato `pausa` effettivo, verificare servizi uscite continuano e 2 posizioni; nessuna chiusura automatica o reset.
2. Lettura mirata e in sola lettura delle due operazioni (margine, leva proposta/finale, motivo downshift, stop, TP, costi, realized/open PnL, rischio aggregato): niente audit estesi. Non leggere chiavi.
3. Proporre su branch isolato profilo SCALP PAPER più aggressivo, mai sovrascrivere attuale run mentre aperte posizioni. Valutare x10–25 e fino a 30 solo se compatibile con SL e rischio; 250–350 margine slot, 400 se meno posizioni; 4 slot disponibili ma nessun riempimento forzato, rischio massimo per trade e aggregato esplicito, limite esposizioni fortemente correlate.
4. Filtri direzionali LONG e SHORT in base al regime e timeframes, senza obbligare una sola direzione; analizzare i segnali SHORT Falco come benchmark, non copiarli senza misure.
5. Esaminare profit protection dinamica fee-aware senza SL troppo stretto: trigger per profitto netto, break even/buffer e trailing basato volatilità o R, test PAPER; nessuna chiusura forzata a mezzanotte.
6. Claude main supporto esterno, DeepSeek modello principale, risk manager indipendente; mantenere journal/snapshot/scoreboard e la nuova dashboard Classici.
7. Proporre una sola revisione compatta e un piano test comparativo con metriche PnL netto fee+AI, drawdown, profit factor, win/loss, expectancy per simbolo/lato e rischio; NON riavviare senza esplicita autorizzazione.

## Continuità
- Rischio residuo: stop e TP non garantiscono esito massimo, leva elevata amplifica perdita e commissioni. Per denaro reale serve revisione aggiuntiva; attualmente sempre PAPER.