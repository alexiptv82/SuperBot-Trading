# Brain — nuova dashboard leggibile (PAPER) · 30 ottobre 2026

## Obiettivo UI confermato dall'utente
Un portafoglio Brain unico, con la chiarezza della dashboard classici Falco/Toro. Da mobile: capitale disponibile, margine impiegato, equity, P&L complessivo, slot; sotto le posizioni aperte con prezzi di entrata/attuale, lato LONG/SHORT, leva, margine, stima netta, ROI sul margine, stop/target, durata. Sezioni dedicate: aperti, storico, statistiche e piani in attesa.

## Implementato offline su work/brain-simple-dashboard-20261030
- `frontend/src/pages/BrainScalpDashboard.js`: nuova vista responsive stile classici; pagina unica per wallet Brain, layout a cards, tab rapide; resta *read-only*.
- `frontend/src/components/NavBar.js`: tab Brain porta alla nuova pagina; archivio precedente accessibile da link.
- `backend/brain_scalp_snapshot_view.py`: controllo opzionale dei nuovi campi prezzo e P&L, rifiuto di snapshot contraffatti/malfomati e quote non fresche.
- Ramo produttore separato `work/brain-single-integration-20261030`: `snapshot.py` pubblica price mark solo su quote fresche (massimo 10s), P&L stimato di chiusura includendo commissioni di ingresso/uscita, slippage e funding; elenco delle ultime 50 chiusure persistite in SQLite, win/loss recenti, totale chiusure. Supervisore passa esplicitamente le quote al publisher. Il conteggio delle chiusure NON è ottenuto da un elenco sintetico.
- Se la quota è assente/scaduta, la posizione mostra `—` come prezzo corrente e P&L. Se snapshot o heartbeat è vecchio, la UI mostra avviso di storico e nasconde il P&L *di posizione* come corrente. Nessuna cifra finanziaria fittizia.
- **Storico** è per adesso limitato alle ultime 50 chiusure; per consultare tutti i trade precedenti servirà in futuro una API paginata autenticata e read-only. Il totale è calcolato sul database. Win rate recente ha ambito dichiarato.

## CI
- `41039334417`: SUCCESS, 13 React test / 2 suite, build compilata; Python 23 test lettore +3 test fonte, tutti superati.
- `41039340769`: SUCCESS Python3.10 e 3.11 sull'intero motore Brain (175 test unit di regressione per versione e test di integrazione aggiuntivi).
- Test senza API pagate, senza token, nessuna operazione su exchange o database dei bot attivi.

## Stato e vincoli
- App e produttore sono su rami Git distinti e non sono stati uniti né distribuiti. Per visualizzare P&L e storico serve pubblicare *entrambi* i lati del contratto nello stesso rilascio dopo backup, collaudo, autorizzazione.
- Il Brain resta uno solo. Nessun reset o migrazione dei classici; nessun nuovo ordine e nessun lettore Telegram.
- Nessuna modifica ai parametri del capitale, rischio, scelta AI, strategia LONG o soglie di apertura.
- Quando il Brain operativo sarà validato, valutare la navigazione diretta a "Brain" e l'API storica paginata, senza appesantire la schermata principale.

AI: chatgpt (chat normale)
