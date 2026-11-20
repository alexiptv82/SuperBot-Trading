# 20/11/2026 (4) — Claude: seconda acquisizione riuscita, difetto del feed, schermata Brain Unico, piano RC

**Ramo:** `integration/brain-unico-20261119` @ `8fa61d18`: suite V3 5310, builder 157, Jest 137, 0 falliti. Ogni pubblicazione è passata dal gate. Nessun deploy, servizio, parametro attivo o spesa.

## 1. Seconda acquisizione delle candele (autorizzata)
**Controllo preliminare** su BTCUSDT 15m, 2 tentativi HTTP su un massimo di 3: **positivo**. La regola corrente e il runtime coincidono: 399 righe, 0 differenze. Rapporto in `~/brain-unico-lab/data/probe-20261120.json`.

La sonda **conferma sui dati reali la causa dell'interruzione precedente**: Bitget restituisce in una pagina la candela che inizia prima dello `startTime` richiesto ma lo contiene. Nei due casi osservati la candela si apre 1 ms o 900 s prima. La vecchia regola per singola richiesta la scartava.

**Acquisizione completa**, una sola, con un budget residuo di 348:

| Voce | Valore |
|---|---|
| Archivio | `~/brain-unico-lab/data/candles-20261120b` |
| **Manifest ID** | `candles-20261120T064955Z-95a00e9b` |
| **SHA-256 del manifest** | `4c982882e53324ce944279b3e016cc8b71f4b96e64e76e7a03afa0021aecf407` |
| Tentativi HTTP | 264 + 2 della sonda = **266 / 350** |
| Dimensione | 8,47 MB / 100 MB |
| Periodo | 2026-10-04 → 2026-11-20 00:00 UTC (47 giorni) |
| Simboli e timeframe | 8 simboli × 15m/1h/4h = 24 file |
| Righe | 47 352 / 47 376 attese |
| Integrità | `intact` |
| Provenienza | `manifest_unanchored`: **in attesa dell'ancora del proprietario**. Con l'ancora, la verifica dà `attested` (prova eseguita solo in memoria, nulla registrato) |
| Validatore | legge i 3 timeframe con meta valido |

**Ancora:** da registrare **dal proprietario**, con `{"candles-20261120T064955Z-95a00e9b": "4c982882e53324ce944279b3e016cc8b71f4b96e64e76e7a03afa0021aecf407"}`. Claude non l'ha registrata.

## 2. Difetto del feed scoperto dai dati (corretto offline)
In **tutti e 24 i file** manca esattamente l'**ultima candela chiusa** del periodo: 1 su 4512, 1 su 1128 e 1 su 282, a seconda del timeframe.

**Causa:** `history-candles` seleziona per orario di **chiusura**. Il runtime chiedeva `endTime = fine − 1 ms`, quindi la candela che chiude esattamente a `fine` non arrivava mai.

**Effetto sul runtime:** il Brain decideva sempre con **una candela di ritardo**, fino a 15 minuti sul 15m e fino a 4 ore sul 4h. Lo stesso accadeva al feed a 1 minuto del monitor degli stop.

**Correzione `315edf15`:**
- finestre `(fine − 200 × passo, fine]`;
- candela in formazione sempre esclusa;
- pagine contigue con entrambe le semantiche, provate con emulazioni per apertura e per chiusura;
- con la vecchia regola i due nuovi test falliscono.

**Non ancora confermata sull'API reale:** serve una sonda autorizzata di al massimo 3 tentativi. Il percorso operativo sulla VPS non è stato toccato. Se usa lo stesso codice, ha lo stesso ritardo: da valutare dal proprietario.

## 3. Chiusure manuali
Verificate end-to-end, dalla richiesta dall'app fino al builder:
- `paper_close` con motivo `manual`, ancora collegata alla decisione che ha aperto la posizione;
- esito `is_manual`;
- chiave separata nell'expectancy;
- **esclusa** dallo scoreboard per strategia;
- nel builder `closed_by=operator` e `manual_close_not_imitable`: conservata come intervento dell'operatore, mai imitata;
- la memoria mostra separatamente le chiusure manuali e quelle automatiche.

## 4. Schermata Brain Unico nell'app SuperBot
- **Schermata iniziale:** `/brain-unico`, raggiunta con un reindirizzamento interno da `/`.
- **Contenuto:**
  - profitti e perdite, statistiche;
  - posizioni aperte con la **stessa** chiusura singola con conferma e gli stessi blocchi di sola lettura;
  - ultimi trade chiusi, stato del sistema;
  - memoria, tesi e apprendimento.
- **Storico:** Falco, Toro, Brain V3 e Brain precedenti si raggiungono dalla scheda "Storico". La vista dell'Arena **non è ancora integrata** nell'app e la pagina lo dichiara.
- **Aggiornamento dell'app:**
  - il service worker carica le pagine prima dalla rete, si attiva subito e aggiorna i file con hash;
  - il manifest non cambia, quindi **dopo un deploy non serve reinstallare**: basta riaprire l'app con la rete;
  - l'app installata si apre come applicazione, senza aprire Chrome a parte.
- **Pagine esistenti:** invariate.
- **Test:** Jest 137/137, build di produzione OK. `frontend/build` nel repository non è stata toccata: la build si produce al rilascio.

## 5. Piano della release candidate
`docs/v3/BRAIN-UNICO-RC-PAPER-PIANO-20261120.md` copre:
- contenuto della RC;
- GO/NO-GO, tra cui la sonda del feed, **backup e restore attestati** e il mandato;
- deploy descritto ma non eseguito;
- collaudo di 14 giorni con misure e attese;
- rollback;
- decisioni aperte.

## Prossimi passi
- Proprietario: ancora dell'archivio delle candele; autorizzazione alla sonda del feed.
- Claude:
  - prima validazione reale delle feature degli snapshot del laboratorio sull'archivio, dopo l'ancora;
  - freschezza reale per l'istante per simbolo;
  - vista storica dell'Arena;
  - stato della perdita giornaliera nella schermata Brain.
