# Pre-registrazione del laboratorio P10 — tre strategie a sole candele su BTC e ETH (4 novembre 2026)

> **Scopo:** fissare **prima di vedere un solo risultato** cosa si misura, con quali valori e quando una strategia conta come «evidenza positiva». Vale **solo per il laboratorio offline**: non cambia il Brain, le sue soglie, i suoi limiti, i suoi prompt (regole 1–9 di `CLAUDE.md` invariate). Il file `backend/v3/lab/preregistration.json` è la versione eseguibile di questo documento; il suo commit precede il primo risultato (la data del commit su GitHub è la prova).
>
> **Revisione incorporata:** la revisione esterna del 4/11 (21:26) è stata valutata punto per punto; cosa è stato adottato, già soddisfatto o dichiarato come limite è nelle sezioni 7 e 8.

> **Nota di allineamento (5 novembre, PRIMA di qualunque risultato):** il classificatore di regime P8 confronta lo shock con `>` e non con `≥`; i valori numerici sono quelli di `preregistration.json`, invariati (sha256 `7e561c2131d33a4214ba973da2163e53a232fe2e6ea115b95443c109d9ab550e`). Il codice del laboratorio (P10) è la consegna di ChatGPT applicata invariata (commit `9556c9f`); i miei test indipendenti e il caricatore dei dati sono in commit separati.

## 1. Domanda

Le tre regole più semplici delle famiglie breakout (S07), inversione (S05) e trend (S02), con valori da manuale **non ottimizzati**, hanno un'aspettativa netta positiva su BTCUSDT e ETHUSDT (futures USDT-M, candele da 15 minuti, circa 540 giorni), dopo costi realistici, e il risultato **non si spiega** con la deriva del mercato o con il caso?

Un risultato negativo è un risultato: fa risparmiare la costruzione degli altri 9 rilevatori (P9b).

## 2. Dati

BTCUSDT e ETHUSDT, candele chiuse da 15 min, ultimi ~540 giorni fino al giorno prima dell'esecuzione, scaricati da Bitget tramite GitHub Actions (il sandbox non raggiunge Bitget). Le serie con buchi si **spezzano in segmenti contigui** (indicatori e regime non attraversano mai un buco); i segmenti con meno di 400 barre sono scartati. Il periodo di valutazione parte **30 giorni dopo** la prima barra (riscaldamento per regime e indicatori).

## 3. Strategie (valori fissi, non ottimizzati, non si cambiano dopo aver visto i risultati)

| id | rilevatore (P9a) | parametri |
|---|---|---|
| S07 | breakout del canale di Donchian | n = 20, filtro EMA(50) acceso |
| S05 | inversione Bollinger %B + MACD | Bollinger 20 / 2, soglie %B 0,2 e 0,8, MACD 12/26/9 |
| S02 | incrocio EMA + ADX minimo | EMA 9/21, ADX(14) ≥ 25 |

Rischio comune: ATR(14); stop = 1,5 ATR; obiettivo = 2 R (3 ATR); cooldown 3 barre. Ingresso al `close` della barra di segnale (limite dichiarato: sezione 8). Un solo orizzonte primario: **4 ore** (16 barre). Politica del tocco ambiguo nella stessa candela: **stop prima** (prudente).

Soglie del classificatore di regime (valori **del laboratorio**, non decidono nulla per il Brain): shock = TR > 3 × ATR (confronto stretto, come in P8); espansione = percentile ATR ≥ 80 su 2 880 barre; trend = ADX ≥ 25; range = ADX ≤ 20; ATR e ADX a 14.

## 4. Costi

**Primario: 12 bp** round trip (commissioni taker Bitget in ingresso e in uscita). Varianti **solo riportate** (mai usate per scegliere): **0 bp** (c'è un vantaggio lordo?) e **20 bp** (stress: commissioni più slippage). Non c'è serie storica del funding né dell'attrito reale: sono nel limite 8.

## 5. Misure (per ciascuna delle 6 coppie strategia × asset, **nessun verdetto aggregato**)

* aspettativa netta in **bp** e in **R** (media di `r_multiple`), numero di trade (candidati con orizzonte completo), giorni distinti;
* intervallo di confidenza con **bootstrap a blocchi di giorni** (metodo di P4), **confidenza 0,99** (6 confronti: approssimazione dichiarata), 5 000 ricampionamenti;
* **drawdown massimo in R** (somma cumulata di R ordinata per chiusura; non è un portafoglio);
* separato per lato (long / short);
* **walk-forward** (P6): addestramento 120 giorni, test 30, passo 30, **embargo 1 giorno**, finestre scorrevoli, finestre semiaperte per `closed_at_ms`. La funzione dell'addestramento è dichiarata: si scelgono le **celle (simbolo, lato) con stato `positive`** (limite basso dell'intervallo > 0 con confidenza 0,9, almeno 30 trade e 10 giorni) usando **solo** il train; poi si misurano nel test. Si riportano medie IS / OOS / resto e `decay_bp` (differenza assoluta IS − OOS) e il rapporto OOS/IS. Una seconda passata con celle (simbolo, lato, **regime**) è **esplorativa**, riportata ma **mai** usata nel verdetto;
* **controllo invertito:** stessi istanti d'ingresso, lato opposto, stesse distanze di stop/obiettivo (speculari); diagnostica, mai usato per scegliere;
* **controllo a scorrimento circolare** (deriva): lo stesso vettore dei segnali scorso di un numero casuale di barre ≥ 30 giorni (40 scorrimenti con seme fisso), poi ricostruiti candidati, etichette e statistiche; si riporta il **rango percentile** dell'aspettativa osservata fra le 40 nulle;
* quota di candidati **ambigui** (stop e obiettivo nella stessa candela) e aspettativa con `target_first` come **limite superiore** dell'effetto della politica;
* **scarto d'ingresso:** differenza media fra il `close` del segnale e l'apertura della barra successiva (a favore o contro), per misurare quanto cambierebbe entrare all'apertura seguente;
* conteggio delle barriere toccate (obiettivo / stop / scadenza).

## 6. Verdetti (regola fissata ora; ordine di precedenza)

Calcolati sull'aspettativa netta **a 12 bp** su tutto il periodo di valutazione (le regole sono fisse, non c'è adattamento: l'intero periodo è fuori campione per le regole; il walk-forward misura in più la stabilità nel tempo).

1. `DATI_INSUFFICIENTI` — la cella complessiva è `insufficient` (meno di 30 trade o 10 giorni).
2. `NEGATIVO` — limite alto dell'intervallo (0,99) **< 0**.
3. `EVIDENZA_POSITIVA` — **tutte** vere: **E1** media > 0 **e** limite basso (0,99) > 0; **E2** walk-forward: almeno 3 fold con selezione, almeno 100 trade OOS, media OOS > 0 **e** media OOS ≥ 0,5 × media IS; **E3** controllo invertito: media invertita < media osservata **e** ≤ 0; **E4** rango percentile nel controllo a scorrimento ≥ 95.
4. `POSITIVO_INCONCLUDENTE` — media > 0 ma non tutte le condizioni E1–E4 (si elenca quali falliscono).
5. `NULLO` — in tutti gli altri casi.

Nessun'altra lettura è ammessa: niente «quasi positivo», niente verdetti per sottoinsiemi scelti dopo, niente verdetto aggregato sulle 6 coppie.

## 7. Cosa succede dopo (decisioni prese ora)

* **Nessuna** coppia `EVIDENZA_POSITIVA` → si ferma: gli altri 9 rilevatori (P9b) **non** si costruiscono; si riferisce all'utente e si valuta con lui cosa cercare altrove (regime, sessioni, derivati, dati non-candela).
* Una o più coppie `EVIDENZA_POSITIVA` → si decide con l'utente: replica su un secondo periodo/asset, poi eventualmente P9b o il passaggio al Brain come shortlist (che richiede **decisione esplicita dell'utente**: regola 3).
* Se si volesse cambiare un parametro dopo aver visto i risultati, è una **nuova pre-registrazione** con un nuovo `run_id`; i risultati di questa restano pubblicati così come sono.

## 8. Limiti dichiarati (non sono errori)

* **Ingresso al `close` della barra di segnale**, non all'apertura successiva (P5 etichetta dalla barra successiva): lo scarto medio è misurato (sezione 5), non corretto.
* **Nessun funding e nessuno slippage separati** (non c'è la serie): il 20 bp è lo stress che li sovrasta; i costi non dipendono dalla barriera.
* **Candidati etichettati indipendentemente**, non un portafoglio: i trade si sovrappongono nel tempo e non c'è cooldown dall'uscita; il bootstrap a blocchi di giorni gestisce la dipendenza **fra** giorni, non quella dentro lo stesso giorno. Il drawdown in R è la somma in ordine di chiusura, non un conto reale.
* **Granularità 15 minuti:** un tocco ambiguo nella stessa candela non si può risolvere con dati più fini (si riporta la quota e il limite `target_first`).
* **Confronti multipli:** 6 coppie e un 0,99 (≈ 0,983 per coppia con Bonferroni, approssimazione); la selezione delle celle nel walk-forward è su pochissime celle (2 per esecuzione).
* **Periodo breve e unico regime di mercato** (~540 giorni): un risultato positivo non garantisce il futuro; uno negativo non esclude altri mercati.
* **Deriva:** il controllo a scorrimento ne misura l'effetto; non la elimina.
* I **parametri** sono da manuale, non scelti sui dati; i **540 giorni** erano già stati usati da altri laboratori (edge lab del 29/10: nessun vantaggio lordo trovato su altre strategie): possibile influenza indiretta, dichiarata.
* Funzionamento in **PAPER**; nessun importo reale; `unit_notional` = 1 000 è un'unità di conto astratta.

*Preparato da Claude Sonnet 5.5 — coordinatore tecnico — 4 novembre 2026, sera, dopo la revisione esterna delle 21:26.*
