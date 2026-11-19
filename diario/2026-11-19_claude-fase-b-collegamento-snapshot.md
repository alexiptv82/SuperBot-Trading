# Claude — Fase B: collegamento snapshot v2 (#122) -> Dataset Builder (#118)

**Branch:** `claude/brain-unico-snapshot-link-20261119` @ `ef25c69c93fd9cec3f3ed32ca9469a9b17506635`, costruito sopra #118 (`0833c0d`). Builder 0.4.0. Solo `ops/brain-unico/training/` e documentazione; nessun codice del runtime, nessun dato reale.
**PR draft da aprire** (403 per il connettore di Claude): https://github.com/alexiptv82/SuperBot-Trading/pull/new/claude/brain-unico-snapshot-link-20261119 — base `claude/brain-unico-training-dataset-20261119`.

## Scoperta (provata con il vero EventJournal e il vero adattatore #122)

Il journal non impone l'ordine temporale (`occurred_at_ms` lo dà chi scrive). L'adattatore `append_snapshot` della #122 **accetta uno snapshot scritto dopo il `paper_open` con l'istante della decisione**: sul piano dell'orologio è indistinguibile da uno vero. Un dataset costruito fidandosi dei timestamp potrebbe quindi contenere feature calcolate sapendo già l'esito.

## Regola adottata: ordine di scrittura (`seq`), non orologio

Le feature entrano solo se: unico snapshot, stesso run, schema 2; legato per id **e** hash dell'evento di decisione; istante, simbolo, azione e stato coincidenti; `asof ≤ captured ≤ decisione`; `seq(snapshot) > seq(decisione)`; `seq(snapshot) <` ogni `paper_open` collegato; `seq(snapshot) <` primo evento (esclusi gli snapshot) oltre decisione + 120 s; valori numerici finiti, nomi consentiti, nessun testo. Rifiuto = ricostruzione da candele chiuse + codice del motivo. **Anche ammessi, restano non ammessi al training** (`snapshot_unverified`) finché la fonte di mercato non è verificata in modo indipendente.

## Prove

- 31 test nuovi + 103 esistenti = **134 test**, stabili su 3 esecuzioni, offline.
- Mutazioni **28/28** rilevate (3 gap iniziali chiusi con test: hash malformato / colonna hash assente / tempi non monotoni / ruolo degli snapshot nella timeline).
- Formato reale: `EventJournal` + `append_snapshot` ⇒ caso regolare e NO_TRADE ammessi; snapshot retrodatato dopo l'apertura **rifiutato** (`snapshot_after_open`).

## Proposte, non applicate

1. **#122:** l'adattatore dovrebbe rifiutare *alla scrittura* uno snapshot se la decisione ha già un `paper_open` o se esistono eventi successivi oltre la grazia. Lo preparo su un branch mio sopra `513448e` (non tocco il branch di ChatGPT, "un autore per componente"), se non ti dispiace.
2. **Verifica indipendente delle feature** (per togliere `snapshot_unverified`): ricalcolo da candele attestate e confronto. Da progettare quando la lista delle feature del runtime è fissata.
3. **Collegamento al runner** (scrivere lo snapshot nello stesso ciclo, **prima** dell'apertura): richiede modificare il runtime Brain, quindi solo su branch di integrazione.

## Non fatto / limiti

- La grazia di 120 s è un parametro. L'ordine di scrittura prova che lo snapshot precede gli eventi successivi, non che le feature siano corrette.
- #118 e #122 stanno su basi diverse (`main` e `work/brain-exit-observability`): i test del builder usano un journal con la stessa forma; la compatibilità col vero journal è provata con uno script, non con un test del repository (il repo `main` non contiene `backend/v3`).
