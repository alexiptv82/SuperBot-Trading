# 2026-11-02 — Decisione utente: SuperBot V3, fermare tutto in sicurezza e ripartire con PAPER pulito

## Mandato dal titolare
Richiesta di ristrutturazione completa: sospendere tutti i bot operativi Falco, Toro, Brain, Pool e componenti shadow durante lo sviluppo, ordinare le strategie e i servizi, integrare nuove ricerche LONG/SHORT, Brain AI governato da regole, gestione dei rischi e controllo delle chiusure. Ripartire **solo dopo test e successivo OK esplicito**, con portafogli PAPER azzerati contabilmente a **Falco 1000 USDT, Toro 1000 USDT, Brain 2000 USDT**, preservando INTEGRALMENTE trade storici, decisioni, errori, costi, memorie, segnali e configurazioni passate in storico separato/nuova run. No eliminazione database, log o teaching.

## Sicurezza nell'arresto
- **Non fare docker stop indiscriminato.** Le protezioni SL/TP possono risiedere nel loop locale. Prima impedire ingressi e DCA, verificare esposizioni PAPER e, separatamente, LIVE/exchange, tenere attiva la gestione protettiva finché tutte le posizioni che la richiedono sono chiuse o esplicitamente protette fuori dal processo.
- Il codice `backend/desk/cli.py` su `rule-pool` prevede `pause.flag` in ciascuna cartella dati per bloccare nuovi ingressi/DCA senza chiudere forzatamente le posizioni. La modalità `draining` può continuare a usare Claude per gestire le aperte; non promettere zero consumi AI immediati se esistono posizioni. Verificare runtime effettivamente installato e monitorare `pause_requested`, `open_positions` e `heartbeat` prima dello stop completo.
- Pool `superbot-pool` già fermato e backup verificato `/opt/superbot-pool-backups/20261102T125929Z`; storico 291 closed + 1 OPEN simulato. Non riavviarlo né eseguire PR #28 implicitamente.
- Vecchio Brain Free, Pilot, AI Shadow: pause già documentate; verificare che siano ancora persistenti, e nessun loop AI separato sia attivo. Non creare reset, non cambiare wallet.
- App/dashboard può rimanere consultabile in manutenzione, senza ordini, finché test e audit non terminano.

## Sequenza successiva
1. Read-only inventory di container, mount, modalità PAPER/LIVE, posizioni aperte e protezioni.
2. Attivare solo pause sicure e verificarle, senza docker stop con posizioni aperte; concordare come liquidare le residue (naturale SL/TP o chiusura manuale esplicita).
3. Quando flat, stop mirato di tutti i worker trader/AI; backup consistente e test restore di ciascuno, inventario versioni/rollback; preservare protezione 450 USDT tra limiti non derogabili fino a decisione nuova.
4. Analisi perdite e correlazione Falco/Toro su stesso asset, ricerca LONG, short, Brain AI sotto regole, apprendimento misurabile fuori campione; nessuna promozione delle strategie Pool negative.
5. Nuove run PAPER con capitale iniziale richiesto e ledger precedente archiviato, nuovo deployment solo dopo OK.
AI: ChatGPT. Stato: decisione di progetto registrata; STOP completo Falco/Toro/Brain non ancora attestato nella chat.
