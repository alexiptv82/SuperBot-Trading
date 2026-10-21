# Primo confronto A/B: stagionalita (21 ottobre 2026)

Stato: preparato per revisione. Nessun deploy, trigger o modifica operativa.
Base codice: e7866bf. Autore: ChatGPT. work/director-chatgpt intatto.

## Obiettivo della prima fase
Misurare l'effetto diretto del bonus sui punteggi REGISTRATI, non il profitto,
non il numero di ordini che un portafoglio avrebbe realmente eseguito.
A = lettura registrata. B = stessa lettura senza bonus stagionale.
Soglia esplicita per scenario: non ricostruita automaticamente dalla data.
Non combinare stagionalita, trend giornaliero, leva o simmetria.

## Dati e prerequisiti
Usare una copia PAPER verificata, immutabile, del learning_log.jsonl, fuori dal
repository pubblico. Il comando richiede SHA256 atteso e conferma PAPER
(quest'ultima e' attestazione dell'operatore, non prova ottenuta dal log).
Prima di ammettere una code_version verificare nella storia git che formule,
ordine delle penalita e saturazione coincidano con signals.py/seasonal.py usati.
Il report include hash del contenuto di input e della formula stagionale.
Nessun record grezzo, simbolo, prezzo, saldo o messaggio originale in output.

Il logger registra proposte open/candidate, non tutto il mercato; smette di
registrare candidate oltre MAX_BYTES_CANDIDATES. Non stimare copertura totale
senza un inventario separato per ciclo. Il risultato e' condizionato alle letture
registrate; gli eventi di origine AI non diventano ordini rules controfattuali.

## Ambiguita esplicite
- Punteggio 100 con bonus positivo: escluso (saturazione non invertibile).
- Versione non revisionata/campi mancanti/non finiti: esclusione contata.
- Chiave lettura bot/run/ts/symbol: duplicati identici contati una volta;
  letture discordanti sulla stessa chiave fermano l'analisi.
- Pareggio long/short: direzione zero, non eleggibile.
- Non si inferisce profitto, trade_type, leva, confidenza AI o margine.

## Come eseguire offline (non ancora sui dati operativi)
python deploy/scripts/seasonality_audit.py --snapshot /percorso/copia.jsonl \
  --sha256 HASH_VERIFICATO --threshold 60 --reviewed-code-version VERSIONE \
  --paper-confirmed
Ripetere eventuali scenari di soglia solo se dichiarati prima; non selezionare
quello col risultato piu' favorevole. Output aggregato su stdout, input read-only.
Il doppio controllo del file rileva variazioni durante la lettura ma non sostituisce
il backup coerente. Nessuna modifica dei file bot e nessun accesso di rete.

## Fase successiva, non implementata qui
Prima: inventario e riconciliazione di tutte le posizioni, comprese quelle escluse
dal replay semplice. Poi esiti per regime (definito prima dell'ingresso), lato,
versione e rischio in dollari. Il replay A/B delle uscite deterministiche non deve
essere presentato come replica dello storico contenente interventi AI.
Una simulazione di portafoglio richiede configurazioni storiche, ordine effettivo,
slot, cooldown e disponibilita di margine; non assumere FIFO o slot attuali.

Valutazione economica futura: confronto su periodo comune, netto/capitale,
esposizione e drawdown, piu' R per trade come metrica secondaria. Bootstrap per
blocchi comuni tra A/B, non candidati indipendenti. Nove giorni sono esplorativi;
nessuna promozione automatica. Soglia economica e numerosita/potenza da fissare
prima di una nuova raccolta, dopo inventario dei dati, non ottimizzare sui 151 trade.

## Replay PM: intervento circoscritto
complete_window corregge il difetto dimostrato: richiede barre continue dal warmup
fino alla barra che contiene il timestamp di uscita (inclusa quella che inizia
esattamente all'uscita). E' conservativo: l'ultima barra deve essere disponibile.
Non cambia le regole PM o i bot. Restano aperti: input rigorosi/backup congelato,
riconciliazione dei costi, MFE intrabar e successo ingannevole del workflow.
Non usare questa sola correzione come via libera al replay conclusivo.
