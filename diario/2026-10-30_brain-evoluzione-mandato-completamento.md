# 30 ottobre 2026 — Europe/Rome — Mandato completamento Brain e classici

L'utente autorizza completamento sviluppo e collaudi di Brain e classici, estendendo il Brain ad analisi continua, gestione posizioni e ricerca autonoma di strategie. Prima dell'avvio desidera esaminare il risultato. PAPER permanente; conservare storici e memoria; nuovo conto Brain desiderato 2000 USDT PAPER, non ancora inizializzato.

FATTO: ispezione supervisor.py nella base efc7d776 e modifiche locali di integrazione già presenti. Il ramo locale verify-service contiene modifiche precedenti: non sovrascritte. La condizione `elif healthy and scan_result['candidates']` avvia analisi solo con candidati scanner. Non esiste qui una garanzia di revisione AI periodica delle posizioni aperte senza nuovi candidati. Le protezioni account.tick vengono eseguite prima e restano indipendenti.

DA IMPLEMENTARE: revisione posizioni con contratto distinto dagli ingressi, decisioni validate per posizione/versione/prezzo corrente, gestione di risposte scadute e idempotenza; analisi tecnica multitimeframe causale; memoria esiti e ricerca di varianti con valutazione fuori campione prima della promozione; collegamento completo teaching classici; configurazione provider/budget, dashboard stato, backup/restore e collaudo operativo.

PREPARATO: mandato e problema riproducibile identificato dalla lettura del sorgente. Nessun nuovo codice o test eseguito in questa fase. RILASCIATO: nulla. Non dichiarare apprendimento autonomo o gestione AI continua già implementati.

PROSSIMO: ripartire da checkout isolato del servizio pubblicato 895b34a, leggere istruzioni e sincronizzazione complete, definire e implementare revisione posizioni separata con test senza candidati, AI lenta/errore, prezzi scaduti e doppia risposta. Preservare lavori locali preesistenti.
