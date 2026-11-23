# 2026-11-23 — Decisione grafica: Brain Unico con layout Classici

## Richiesta proprietario, dopo verifica reale da smartphone
- Il proprietario ha confermato da screenshot 07:43-07:44 che la nuova dashboard `/brain-unico` è pubblicata, legge equity PAPER 2000 USDT, PnL 0 e stato `In attesa del mandato dell'utente`. Anche `/classic` è visibile.
- **Preferenza esplicita:** prima di attivare DeepSeek e le 72 ore PAPER, rendere `/brain-unico` graficamente uguale o molto simile a `/classic`, perché più bella, leggibile e intuitiva.
- Non modificare le strategie, il motore, i dati, il mandato (`approved:false`), le unità o la configurazione di rischio; ancora nessuna apertura PAPER autorizzata.

## Codice esistente verificato
- Layout Classici in `frontend/src/pages/Dashboard.js` e `frontend/src/components/BrainPortfolioSection.js`: header PAPER, equity hero grande e centrata, PnL percentuale, cassa/margine/PnL aperto/oggi, tre KPI aperte/chiuse/budget, card stato, comandi, lista posizioni.
- `/brain-unico` in `frontend/src/pages/BrainUnico.js`: già riceve `/api/v3/overview`, `/api/v3/brain/status`, `/api/v3/brain/trades?limit=20`, `/api/v3/brain/memory`, aggiorna ogni 30s, mostra dati reali, memoria, operazioni e controlli `BrainCloseControls`.
- `BrainCloseControls`/`PortfolioTradeFields` in `frontend/src/components/OverviewCloseControls.js`: chiusura manuale singola PAPER con conferma, dettaglio posizione; rispettare `brain_single_close_allowed` e non introdurre chiusura di massa.
- Non riutilizzare nella pagina Brain testi o stati globali dei Classici quali `Falco/Toro non risponde`; la pagina deve mostrare esclusivamente il nuovo Brain.

## Specifica grafica minima
1. Header riconoscibile 'Trade non reale / PAPER' e '🧠 Brain', badge stato veritiero (mandato in attesa, fermo, running, pause, dati non disponibili). Evitare confusione 'Mercato Live' con ordini REAL: quotazioni live, trade simulati.
2. HERO equity centrale grande stile Classici, PnL realizzato e percentuale calcolata solo se disponibile, riga Cassa/Margine/PnL aperto/Oggi (senza inventare valori; usare — per campi sconosciuti).
3. Tre KPI su una riga mobile: Aperte/limite, Chiuse, Budget AI oggi/tetto con valori reali (0.75 USD/die solo se dall'API).
4. Card stato Brain DeepSeek/profilo B e motivi di fermo; blocco daily loss e stato delle uscite se già esposti.
5. Comandi grandi stile Classici: non fingere che Avvia/Pausa siano collegati se le API non li supportano. Mantenere disabilitati con testo esplicativo oppure implementare SOLO con nuova autorizzazione distinta (fuori scope estetico).
6. Posizioni aperte ordinate e complete: simbolo, LONG/SHORT, leva, entry, mark, margine, SL, TP, PnL/ROI; pulsante Chiudi singola con conferma e risultato reale. Niente Chiudi tutte o REAL.
7. Statistiche PnL/win rate/trade chiusi e memoria/decisioni AI in pannelli secondari leggibili/collassabili; preservare distinzioni tra chiusure manuali e strategie apprese.
8. Mobile first sul Samsung, font leggibili, card 3 KPI non troncate, barra navigazione fissa senza sovrapporsi; PWA stessa.

## Criteri di consegna
- Cambiare preferibilmente solo UI React/CSS e relativi test componenti; riusare stile/componenti esistenti senza duplicare intera Dashboard Classici o alterare le sue funzioni.
- Test mirati: stati pausa/running, dati mancanti, zero posizioni, dati posizioni, close con readOnly vero/falso; nessuna regressione `/classic`, `/overview`.
- Preparare preview o deploy con rollback e consenso. Non pubblicare su VPS né avviare trading automaticamente.
- Il proprietario prova la UI sul telefono e solo dopo autorizza mandato e 72h PAPER.

## Stato operativo di partenza
- Pre-collaudo e deploy: entrambi PASS; servizi nuova run pronti, exit sano, runner halted perché `approved:false`; dashboard pubblicata in produzione commit `9b153278`, ma grafica da allineare.
- Nessun lavoro su backup Android/PC o analisi estese richiesto.