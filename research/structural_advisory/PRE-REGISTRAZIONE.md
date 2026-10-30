# Protocollo di verifica futura — struttura v1
Fissato30/10/2026 prima di leggere esiti del nuovo algoritmo. Non è un backtest già eseguito.

Periodo di sviluppo già visto16–23ottobre: non holdout. I dati di replay60giorni precedenti non sono automaticamente fuori campione.
Holdout futuro fissato:1novembre2026 00:00UTC ->1dicembre2026 00:00UTC escluso; warmup20ottobre->1novembre, senza esiti holdout oggi disponibili. BTC/ETH/SOL/DOGE Bitget USDT-FUTURES,15m,1h,4h causali. Nessun download programmato o rilascio autorizzato da questo documento.
Congelare hash codice/dati e definizioni, non scegliere retroattivamente simboli/date/parametri. Eventuali modifiche prima del test sono una nuova versione con protocollo distinto.
Evento avviso: ingresso in UP_REASSESSMENT o DOWN_REASSESSMENT; ripetizioni stesso lato entro4h non nuovi avvisi. Contare sia osservazioni sia eventi deduplicati; non chiamare miglioramento una mera riduzione di frequenza.
Riferimento strutturale: su1h, due chiusure oltre estremi delle20barre precedenti le due chiusure, dopo contesto opposto EMA12/24 confermato nei24h precedenti; buffer0,25 ATR14 preconferma. Conferma resa disponibile SOLO alla chiusura della seconda barra. Definizione fissa e simmetrica.
Misure: eventi confermati entro12h dall'avviso (stesso lato), anticipo mediano/quartili rispetto all'istante causalmente disponibile della conferma; falsi allarmi a12h, inversioni non precedute da avviso entro12h, avvisi/giorno e copertura/warmup; risultati1h e contesto4h separati. Match uno-a-uno cronologico; ogni avviso può coprire una sola conferma e viceversa, duplicati dichiarati. Censurare ultime12h e non chiamarle falsi allarmi.
Confronto con v1.1 congelata e con semplice incrocio EMA9/21 15m, stessi dati/copertura/orizzonte e definizioni. Misurare precisione e richiamo insieme. Il benchmark1h è un criterio operativo, NON verità assoluta di tutti i trend.
Stratificare descrittivamente per simbolo, UP/DOWN, contesto1h/4h e volatilitàATR/prezzo. Nessun tuning su sottogruppi. Incertezza con bootstrap a blocchi giornalieri mantenendo insieme i simboli correlati, non binomiale ingenua sugli avvisi.
Nessun criterio P&L implicito, nessuna promozione automatica. Anche eventuali esiti migliori non autorizzano gate, aumento leva o ordini. Rapporto finale deve riportare null finding, dati mancanti e tutte le versioni provate.

