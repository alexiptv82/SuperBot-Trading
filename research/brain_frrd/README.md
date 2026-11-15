# FRRD V1 — laboratorio offline Brain PAPER

Questo modulo **NON** e' collegato a Brain, Falco, Toro, `runner`, `wiring`, `engine`, `exits` o alla dashboard. Non legge chiavi API e non effettua chiamate di rete. E' uno studio per capire se Brain riconosce tempestivamente i rimbalzi prima degli SHORT perdenti in `EXPANSION`.

## Stato e limiti

- `detector.py`: osservatore **puro** su candele chiuse. Restituisce `CONTINUAZIONE_SHORT`, `RIMBALZO_LOCALE`, `INVERSIONE_CANDIDATA` o `INCERTO`, una causa leggibile e l'indicatore `advisory_only=true`.
- `offline.py`: lettore del journal SQLite Brain in **mode=ro**, collegamento dell'evento di apertura alla decisione via `decision_event_id`; produce un nuovo JSONL fuori dalla cartella dei dati operativi. L'esito `paper_close` viene collegato solo **DOPO** il calcolo del segnale.
- Non effettua trading, non modifica limiti/stop/size/leve, non rimuove rifiuti del RiskQuote e non crea automaticamente un filtro.
- Le soglie sono **ipotesi preregistrate**, NON ottimizzate né validate sui 16 SHORT del campione 11–15/11.
- I test sono scritti ma **non sono stati eseguiti** in GitHub Actions o sul VPS. Va eseguito il collaudo offline prima di qualsiasi uso analitico.

## Regole deterministiche iniziali (non operative)

- 15 minuti: due candele **chiuse** e consecutive devono confermare rottura del minimo/massimo della finestra precedente (swing 9 barre); il livello non include le due barre di conferma.
- `CONTINUAZIONE_SHORT`: rottura inferiore confermata e direzione 1h ribassista; se la 4h e' rialzista il risultato e' `INCERTO`.
- `RIMBALZO_LOCALE`: due chiusure 15m crescenti e recupero dal minimo locale almeno **0,85 ATR(14)**; il recupero non equivale a inversione del trend maggiore.
- `INVERSIONE_CANDIDATA`: rottura superiore 15m confermata, direzione 1h rialzista rispetto a EMA(12) e nessun contesto 4h ribassista.
- Altrimenti `INCERTO`. Mancanza, gap, prezzi invalidi, serie stale oppure ATR non disponibile producono `INCERTO`.
- Nessun *look-ahead*: l'osservatore taglia ogni serie all'istante `as_of_ms` delle candele **gia' chiuse**, poi verifica la continuita' degli ultimi 64 periodi al massimo.
- La doppia conferma attua un **debounce temporale minimo**, non una memoria di stato persistente; l'eventuale vero modulo con hysteresis/state machine richiede ricerca separata.

## Input CSV offline

Servono CSV storici **separati per simbolo e timeframe** nel formato gia' prodotto da `backend.v3.lab_tools.fetch_candles`:

```text
/archivio/candele/BTCUSDT/15m.csv
/archivio/candele/BTCUSDT/1h.csv
/archivio/candele/BTCUSDT/4h.csv    # facoltativo, ma consigliato
/archivio/candele/ETHUSDT/15m.csv
/archivio/candele/ETHUSDT/1h.csv
...
```

Intestazione esatta:

```csv
open_time_ms,open,high,low,close,volume
```

Prezzi `Decimal` a partire dalle stringhe; nessuna interpolazione, nessuna candela 15m/1h/4h in formazione. Per un segnale servono almeno 24 barre 15m, 14 barre 1h, 14 barre 4h se passate, e storia recente fino al suo istante decisionale. **Non risampionare** candele 1m della ricerca Fable senza una fase separata e convalidata.

## Avvio esclusivamente offline

Da checkout isolato del ramo `work/brain-frrd-shadow-research-20261115`, in un ambiente di ricerca **diverso dal runtime del bot**:

```bash
python -m pytest -q research/brain_frrd/test_detector.py research/brain_frrd/test_offline.py

python -m research.brain_frrd.offline \
  --journal /archivio/sola-lettura/journal.db \
  --run-id brain-v3-paper20261111 \
  --candles-dir /archivio/candele \
  --out /tmp/brain-frrd-ricerca.jsonl
```

Il programma rifiuta di scrivere dentro la cartella del journal o dei CSV e **non sovrascrive** output esistenti. Non richiede accesso a Bitget o VPS in rete; il journal e i CSV devono gia' esistere sul computer isolato. Lo script non copia né estrae dati dal server.

In ogni riga JSONL:
- `decision_link`: `verified`, `missing_or_inconsistent` oppure `unlinked`; regime Brain originale solo con link verificato.
- `signal_ts_ms`: timestamp della **decisione** se link verificato, altrimenti timestamp apertura con `observation_time_basis=paper_open_fallback`.
- `frrd`: stato, motivazione, trend, ATR e `advisory_only=true`.
- `outcome_after_entry`: chiusura/PnL del trade quando disponibile, solo per confronto *ex post*; NON fa parte dell'input del rilevatore.

## Condizione per una possibile evoluzione

Servono dati reali di ingresso e candele storiche complete, un campione di **validazione successivo** a questa definizione, e analisi dei falsi segnali (SHORT vincenti sconsigliati). L'attuale campione di 27 chiusure puo' servire a studiare il problema, non a provare un nuovo vantaggio statistico. Ogni futura integrazione con DeepSeek/risk gate richiede autorizzazione distinta dell'operatore.

**Nessun deploy, merge o GitHub Actions eseguito da questo laboratorio.**
