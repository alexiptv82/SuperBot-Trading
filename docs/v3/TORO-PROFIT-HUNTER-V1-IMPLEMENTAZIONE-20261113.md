# Toro LONG Profit Hunter V1 — studio implementato, non distribuito

Data: 13 novembre 2026.
L'utente ha autorizzato lo sviluppo della nuova strategia Toro e vuole successivamente riaccendere Falco SHORT e Toro LONG a fianco di Brain in PAPER.

## Stato
Codice algoritmo aggiunto in backend/desk/toro_profit_hunter.py, con test in backend/tests/test_toro_profit_hunter_v1.py. Il modulo è indipendente: non viene ancora chiamato dal runner e non può aprire trade. Non vi è alcuna modifica alla VPS, ai portafogli, a Falco, a Brain o alle regole SHORT. Non dichiarare il rilascio completo o il backtest positivo.

## Politica del candidato
- TORO LONG only; 1.000 USDT PAPER; massimo 5 slot; margine massimo 200 USDT/trade, massimo aggregato 800 e 200 riserva; DCA OFF.
- Rischio previsto 16 USDT/trade, 40 USDT aggregato, 30 USDT di perdita giornaliera per blocco nuovi ingressi; drawdown 15% dal picco come gate di nuove aperture; non chiudere forzatamente tutto il portafoglio senza nuova decisione.
- Ingresso su 1H chiusa: BB100(2), almeno un tocco nei precedenti 3 periodi, rientro confermato, veto forte ribasso 4H con EMA50 in discesa, prezzo sotto EMA200 e ADX >=25; stop tecnico da minimo della preparazione -0.25 ATR; distanza 0.8–2 ATR; gate rischio/rendimento netto >=1.3.
- Dimensionamento N = rischio_usdt / (distanza_stop + commissioni e slippage stimati), leva intera calcolata e <=20, rispettando limite per asset. Non richiedere leva minima. NO_TRADE valido.
- Maker limit simulato con attraversamento successivo da sopra, expiry 15m, no fill se marketable, stop protettivo taker.
- Profit Guardian usa netto realizzabile, massimo raggiunto e pavimento crescente; momentum 5m solo chiuso; incasso completo anticipato preferito salvo forza confermata, un partial massimo, scadenze 12/24h. Gli output sono advisory, non ancora esecutivi.
- Commissioni nominali maker 0.02%, taker 0.06%, slippage stop 0.02%, funding separato, da verificare sul conto.

## Blocchi tecnici veri prima del rilascio
1. Il codice cli.py presente nello stage VPS Brain (base 0e29a73 con due hotfix local) scarica 1000 candele 15m, ossia 250 ore. Non bastano per 750 barre 1H e 240 barre 4H e non fornisce la nuova gestione uscita al minuto. Va implementato un fetch nativo paginato per Toro, senza interferire con Brain.
2. PaperAccount utilizza fee taker e slippage standard e non simula ordini post-only pendenti; partial_close non sposta SL. Occorrono nuovo adapter di esecuzione e contabile verificato, solo Toro.
3. La stessa baseline VPS non contiene il flag Falco SHORT_ONLY aggiunto in PR #92: accertare cosa gira sulle vere unità classiche prima dell'unpause, perché riavviare il Falco della vecchia versione potrebbe consentire LONG. Non modificare i suoi segnali SHORT.
4. Protezione equity 450 blocca nuove aperture, non limita matematicamente la perdita di posizioni già esistenti. Va validato il rischio aggregato.
5. Brain sta già lavorando in PAPER. Non riavviare Brain, non fare checkout/merge/reset globale della cartella stage condivisa e non sovrascrivere i due hotfix installati.

## Validazione
- Eseguire i test unitari appena creati e la suite di regressione classici. Non sono ancora stati eseguiti da questo ambiente.
- Pre-registrare Passo 0 del rapporto Claude: backtest Bitget dell'ingresso soltanto, uscite 4/8/12h, 0 costi e costi realistici, confronti random appaiati per simbolo/regime/periodo. Nessuna scelta soglie su periodo out-of-sample già visto.
- In caso di vantaggio lordo credibile, integrare un runner Toro PAPER con feed storico completo, ordini maker simulati, stop prioritari, Profit Guardian 1m, persistenza e chiusura manuale compatibile; altrimenti NON attivare Toro con una strategia non convalidata.
- Falco SHORT invariato, ma controllare la reale versione installata e il gate SHORT-only prima di qualsiasi ripartenza.
- Solo dopo test, backup e audit VPS distribuire in PAPER. Gli altri portafogli restano inalterati.

Il file sorgente allegato dal cliente TORO-LONG-PROFIT-HUNTER-rapporto-indipendente.md sezioni C-I è il riferimento del progetto. I numeri sono ipotesi iniziali e non risultati di trading.
