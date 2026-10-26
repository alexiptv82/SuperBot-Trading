# Brain Pilot V1 — handoff a Claude, 26 ottobre 2026

Implementazione dal brief completo incollato dall'utente. Branch dedicato
`work/brain-pilot-v1` da rule-pool. Nessun merge/deploy eseguito.

## Componenti e riuso
- `backend/director/brain_pilot/pilot.py`: ciclo a chiusura 15m; riusa BarCache,
  client DeepSeek e Budget dal pilot esistente. Ordini alla successiva apertura,
  recheck gap/macro, stop/TP gestiti anche senza modello, un tentativo per barra.
- `portfolio.py`: riusa PaperAccount e il suo schema trade; conto nuovo isolato
  da 1000 USD virtuali, max 10 slot. Engine, ai_shadow, Hawk e Bull invariati.
- `prompt_builder.py`: riusa EMA/RSI/pattern di signals.py; dati chiusi validati,
  trend EMA20/50 15m/1h/4h/1d, momentum 24h, volume 15m, livelli 20h, fib dal
  range delle ultime 60 barre daily. BTC una volta sola in un blocco separato.
- `Dockerfile.brainpilot`, trigger e workflow controllo separati. Il workflow
  controlla SOLO `superbot-brain-pilot` e la cartella brain, non installa nulla.
- CI senza Secrets: test offline Python 3.10 e 3.11; nessun deploy.

## Interpretazioni dichiarate per review
`size_pct` è frazione 0..1 del budget di rischio massimo, NON percentuale di
equity da usare come margine. Rischio iniziale <= equity * 1% * size_pct *
conviction/100, inclusi fee apertura/chiusura e slippage stimato allo stop.
Funding nel motore e nel profitto netto, non prenotato nel rischio: dipende
dalla durata. Gaps oltre stop/liquidazione possono superare il rischio stimato.
Leva codice: fino a 45 BTC/XAU/XAG, 30 ETH, 25 altri, ulteriormente ridotta
secondo distanza liquidazione. Margine max 100 per posizione/1000 totale;
daily stop 12% e kill equity 450 ereditati dal pilot shadow, non da Hawk/Bull.

Profitto 25–30% interpretato come ROI NETTO sul margine residuo. Close anticipata,
save_profit, partial e hold sono proposti dal modello secondo tesi e orizzonte;
non sono uscite deterministiche obbligatorie al raggiungimento di una soglia.
Le uscite restano permesse per invalidazione anche senza profitto. Partial .50
fisso; save_profit è rifiutato se non positivo al prezzo di esecuzione stimato.

Averaging simmetrico long/short, max due aggiunte, riusa add_dca del motore:
40% e 25% del margine iniziale. Il modello non sceglie quella quantità: size_pct
e convinzione limitano il rischio TOTALE post-aggiunta, fino all'1% equity.
Questo evita moltiplicazioni nascoste del rischio. Totale margine posizione <=100;
trend 4h/1d confermato, livello deve coincidere (tolleranza .1%) con supporto o
resistenza 20h del codice, prezzo entro 1.5%, livello non violato né oltre stop.
Tutto ricontrollato all'esecuzione con barre già chiuse a quell'istante. Nessuno
stop allargato. Alcune aggiunte vengono quindi rifiutate pur se richieste dall'AI.

Pause 15–120 minuti, motivazione + condizione rientro obbligatorie; modello
richiamato ogni 15m per riesame, gestione invariata. Per evitare proroghe infinite,
lo stesso episodio può durare complessivamente max 2h; un nuovo episodio diventa
possibile dopo una nuova apertura o un nuovo realizzo in perdita. Resume può
terminarlo prima. Hold motivato rimane valido: non si forza un trade a scadenza.
Pause per budget/rischio/dati mancanti sono distinte e possono durare più di 2h.

Nessun calcolo inventato di Diamond/ABC o weekly 0.786: input non contiene weekly
né ETH/BTC. Fase accumulo/distribuzione resta ipotesi, non riconoscimento certo.
Il prompt impone ragionamento struttura → livello → invalidazione → verdetto e
dichiara esplicitamente i dati mancanti. Questa modifica non garantisce P&L.

## Persistenza e isolamento
Mount esclusivo futuro `/opt/superbot-desk-data/brain:/out`; zero mount dei bot
o di `/opt/superbot-ai-data`. Non migrare/azzerare il pilot di 5 giorni implicitamente:
questo è un braccio PAPER nuovo; storico precedente resta intatto per confronto.
`brain.sqlite3` (WAL, synchronous FULL) è autorità di stato + outbox eventi.
`journal.jsonl` e `trade_history.jsonl` sono export append-only con brain_event_id;
trade mantiene i campi nativi engine, più run_no/start_equity. Lock esclusivo
di processo. Export interrotto dopo commit DB si ripete senza duplicati.
Database corrotto, export con ultima riga spezzata o vecchi dati senza stato
NON causano reset: il runner si ferma. Recovery richiede backup e ricostruzione
esplicita degli export dall'outbox, preservando i file danneggiati in archivio.
Non è una migrazione automatica del conto vecchio.

Budget .50 USD/giorno e 12/mese da Config shadow; prima della rete riserva il
costo stimato prudente massimo (prezzo/CHARS_PER_TOKEN ereditati), senza rimborsi
automatici. Su crash non ricontatta il modello per quella barra; si preferisce
saltare la decisione a una doppia chiamata. Il listino del client non è stato
riverificato in questa sessione: Claude deve verificarlo prima del deploy.
In parallelo a shadow i budget appartengono ai due processi: costo complessivo
potenzialmente doppio. Nessuna chiamata reale effettuata in sviluppo.

## Verifiche
30 test offline locali PASS su Python 3.12.14, numpy 2.3.5. Coprono sei
comportamenti, sizing/costi/tier, max slot, dati invalidi e macro, candela
successiva/assenza di future price nel sizing, stop prioritario, pause/hold,
errori modello/budget, riavvio, idempotenza export, dati corrotti e doppio writer.
CI separata predisposta per Python 3.10/3.11 e numpy 2.2.6. Docker non disponibile
nell'ambiente locale: build e avvio container non testati qui. Nessun replay
storico con DeepSeek reale né prova di miglioramento economico.

## Review e futuro deploy (solo Claude Code dopo nuovo OK utente)
1. Review del contratto JSON, delle interpretazioni sizing/ROI/averaging/pausa,
   della persistenza e delle differenze dal pilot precedente.
2. Leggere esiti CI, costruire immagine dal commit esatto con Dockerfile.brainpilot.
3. Decidere se tenere entrambi i pilot: non fermare/migrare quello vecchio senza
   decisione utente. Verificare budget totale e risorse del VPS.
4. Solo dopo OK: container nuovo `superbot-brain-pilot`, immagine identificata
   dallo SHA, DESK_MODE=paper, chiave DEEPSEEK_API_KEY dai GitHub Secrets;
   read-only root, tmpfs /tmp, cap-drop ALL, no-new-privileges, nessuna porta,
   unico mount /brain:/out, limiti CPU/RAM. Nessuna chiave exchange/Telegram.
5. Backup verificato della cartella brain se già esiste; niente reset. Rollback:
   fermare SOLO nuovo container e conservare tutti i dati. Non ripristinare su
   Hawk/Bull o sul vecchio pilot. Verificare heartbeat, paper e writer singolo.
6. Confronto PAPER fuori campione: P&L netto, drawdown, rischio, slot, motivazioni,
   distribuzione long/short condizionata al regime. Non usare il solo win rate.

Il workflow controllo richiede approved=yes per azioni con effetto; il trigger
iniziale report/approved=no non avvia il container. Nessun installer incluso:
deploy resta compito di Claude Code secondo il brief e con OK esplicito.
