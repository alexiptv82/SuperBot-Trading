# SuperBot V3 — RC76, analisi ARB e sicurezza stop durante pausa

Data: 2026-11-07 19:40 CET circa. Audit **READ ONLY** sulla VPS via GitHub Actions. Nessun trade, deploy, reset, merge, apertura, close, restart, modifica di file VPS.

## Evidenza RC76
- Ramo isolato: `work/v3-rc76-arb-forensic-readonly-20261107`, commit `36a054bfe875f83a331acb642991c0aed550772a`.
- Action riuscita: https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42402452564. Primo run RC76 su branch fallito per escape involontario della espressione secret nel secondo step; corretto immediatamente e run successivo PASS. Nessun effetto VPS.
- Falco ARB PAPER aperta: id 62, SHORT `side=-1`, `source=rules`, ingresso `0.160507892`, leva 25x, margine 100 USDT, quantità 15575.5581164819, stop `0.16257485714285713`, TP `0.1568764772`, livello liq simulato `0.16612566821999997`, confidence 74, no DCA, scalp.
- Toro ARB PAPER aperta: id 19, SHORT `side=-1`, `source=rules`, ingresso identico `0.160507892`, leva 25x, margine 185 USDT, quantità 28814.782515491515, SL/TP/liquidazione identici, confidence 74, no DCA, scalp.
- Entrambe aperte allo stesso tick circa, con ragione identica: `trend 4h (+20); trend 1h (+15); prezzo vs EMA50 (+8)`; anzianità 131,75 ore al rilevamento. Questo prova correlazione e concentrazione di rischio su ARB in due wallet; NON prova che la logica del segnale fosse errata.
- Stop da ingresso: +1,287765% avverso per SHORT. Perdita **teorica lorda** in caso di esecuzione ESATTA al livello SL: Falco circa 32,1941 USDT; Toro 59,5592 USDT. Sono scenari, NON perdita realizzata né valori correnti. Prezzo liq simulato a +3,5% dall'ingresso; non assumere che liquidazione o stop siano avvenuti. Il ticker pubblico Bitget consultato in read-only non ha prodotto una quotazione fresca verificabile nel run, perciò mark-to-market e SL-cross non attestati.
- Le 6 chiusure manuali vincenti il 7/11 erano tutti SHORT su NEAR, ATOM, LINK, TIA, SUI (LINK anche Toro), e molte riportano lo stesso motivo trend4h/1h+EMA50. Lo storico contiene anche vecchie chiusure negative ARB, quindi non trattare questa come eccezione provata da un solo campione.
- Fonte codice rilasciato: `backend/desk/exit_only.py` sulla PR #73. Il worker temporary **ONLY** consuma `close_position.flag` o `reset.flag`, esegue manual close e non invoca loop/strategie; vecchi worker legacy `superbot-desk-hawk/bull` stoppati. Quindi, con l'attuale assetto di manutenzione, gli stop automatici delle vecchie posizioni **non vengono monitorati da questo servizio**. Gap operativo P0 da correggere prima del restart, NON abilitare implicitamente ingressi, non riaccendere legacy.
- RC75 18:03 CET: Falco 5 manual close netti +628,9169, Toro 1 manual close +154,0444, totale PAPER +782,9613 USDT; non è equity e non include ARB. Nuovo RC76 ancora 1 ARB per wallet.

## Richiesta utente / decisione di prodotto
Creare una funzione *Post-Trade Review* read-only per Falco, Toro e Brain che segnali, con prove:
1. contesto dell'ingresso (LONG/SHORT, leva, size, scelta AI/regole, ragione e timestamp, solo dati registrati al momento del trade);
2. rischio previsto, stop configurato, stato del monitor di protezione nel tempo, reale violazione dello stop se dimostrabile, MAE/MFE quando feed storico affidabile disponibile, regime di mercato e eventuale cambio di trend;
3. confronto con operazioni coeve o con segnale identico su altre crypto e rischio aggregato dello stesso simbolo su wallet indipendenti; evidenziare posizione duplicata/rischio concentrato;
4. P&L lordo/netto, commissioni, funding se conservato, slippage se verificabile; confrontare piano originario vs esito effettivo;
5. verdict `problema_ingresso`, `problema_gestione`, `movimento_sfavorevole` o `evidenza_insufficiente` **solo se supportato da dati**; no causa inventata. Salvare note append-only, tracce e provenienza, distinguendo decisioni manuali da efficacia provata di una strategia.

**Regola di sicurezza:** il reviewer non apre/chiude trade, non modifica risk o strategie, non promuove automaticamente lezioni; analisi ex-post e allarmi separati. Dopo evidenza sufficiente, proposta validata in PAPER e autorizzazione separata per cambi strategici. Per Brain usare journal V3 e run_id, per classici storici legacy in sola lettura, capitali sempre isolati.

## Blocco per i prossimi passi
L'utente ha dichiarato che chiuderà **lui personalmente** entrambe le ARB con `Chiudi ora` in app. Aspettare conferma/nuovo audit READ-ONLY prima di dichiarare chiuse. NON eseguire close via assistente. L'autorizzazione data al backup riguarda snapshot nuovo **dopo** queste chiusure: usare nuovo nome, non sovrascrivere RC69, controllo file hash/restore isolato, nessun restart. Backup esterno off-host ancora FAILED, non certificato. Non creare nuova run PAPER/reset finché mancano gate.

## Seconda verifica RC76 — deduplica chiusure parziali, 19:48 CET circa

- [Audit RC76 #42403056386](https://github.com/alexiptv82/SuperBot-Trading/actions/runs/42403056386) SUCCESS; HEAD branch `12e199ad092f7200cca3c1f95b234456386e14a2`; ancora 1 ARB aperta Falco e 1 Toro; ticker fresco non attestato; nessun ordine/modifica VPS.
- **Falco:** 8 trade storici ARB distinti già chiusi, **2 positivi e 6 negativi**, risultato netto aggregato **-163,3066 USDT PAPER**, inclusa una chiusura di ARB associata a DeepSeek; gli altri in prevalenza `source=rules`.
- **Toro:** 5 eventi di chiusura ARB corrispondono a **solo 2 trade distinti**: una posizione `id=5` con 4 chiusure parziali e netto aggregato **+60,6742 USDT**, una posizione `id=2` negativa **-76,6340 USDT**, totale **-15,9598 USDT PAPER**. Per analisi/training aggregare per (`portfolio`, `run`, `position_id`/`open_ms`) e separare fill parziali.
- Totale ARB storico *realizzato* delle due run legacy **-179,2664 USDT**, esclusi i due ARB ancora aperti. Questo è un segnale di fragilità locale della strategia/timing ARB, non una prova sufficiente per cambiare le regole. Le due posizioni aperte hanno lo stesso segnale, leva e prezzo: doppia esposizione direzionale su uno stesso asset, pur con wallet indipendenti.
- Il fatto che i trade manualmente chiusi in profitto il 7/11 fossero tutti SHORT, con ragione tecnica spesso identica, non dimostra che ARB avrebbe dovuto vincere: occorre analisi causale dei dati **disponibili al momento dell'ingresso**, del prezzo e della protezione SL nel tempo. Evitare deduzioni da soli trend attuali.

**Stato feature:** sola specifica/audit; nessuna pagina post-mortem integrata o diagnosi AI in produzione. Backup post-close ancora da effettuare solo dopo clic e nuova verifica utente.
