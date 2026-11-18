# Brain storico: perché perde, cosa lo migliora davvero, policy di rischio comune per l'Arena (18/11/2026)

Etichette: **VERIFICATO** (misurato qui su codice o candele reali), **RIPORTATO** (readout VPS del 15/11 o screenshot
dell'utente), **IPOTESI** (da confermare con il journal). Nessun accesso alla VPS da questa sessione, nessun servizio
toccato, nessun credito AI usato.

## 0. Cosa NON è stato possibile fare

* **Codice e config realmente in esecuzione: non letti.** Il readout del 15/11 riporta uno stage VPS `e029a73a` **con
  4 file modificati localmente**: il codice vivo non coincide con nessun commit del repository finché non si legge il
  diff sul VPS.
* **Journal del 15–18/11: non disponibile.** Nessuna esportazione nel repository dopo il readout del 15/11 alle 13:01 UTC.
  Nessun numero di questo documento descrive le operazioni del 16–18/11.
* **La confidenza del modello non è registrata nel journal** (`brain_decision` salva tipo, stato, codice, simbolo,
  regime e strategia, VERIFICATO in `engine.py::_append_durable`). Un filtro sulla confidenza **non è valutabile** sui
  dati storici: per l'Arena va prima registrata.

Strumento pronto per colmare la lacuna, in sola lettura: §5.

## 1. Cosa si sa del peggioramento

* RIPORTATO 15/11 13:01 UTC: 27 chiuse, 48% vinte, netto **+227,17 USDT**, PF 1,20, commissioni 254,36. Stop 14,
  media −79,40; take profit 13, media +102,98. 25 SHORT su 27. Tutte a 20×, stop fra 0,40% e 0,91% (mediana 0,74%).
* RIPORTATO 18/11 06:00 (dashboard): storico DeepSeek **−238,85 USDT**. Differenza circa **−466 USDT in ~2,7 giorni**.
  Non è noto se la cifra della dashboard includa il flottante.
* VERIFICATO (aritmetica sulla config del 15/11 e sul replay): con margine 20% a 20× **il vincolo è sempre il margine**,
  non il rischio. Ogni posizione vale 8.000 USDT di nozionale, cioè 4 volte l'equity. Con lo stop mediano: uno stop costa
  circa **−70 USDT**, un take profit vale circa **+109**. Corrisponde alle medie riportate (−79,40 e +102,98, con stop
  un po' più larghi della mediana). Quindi **sei stop netti in più dei take profit bastano a perdere 466 USDT**: il calo
  non richiede un cambio di codice per essere spiegato. Se lo richieda davvero si sa solo dal journal.
* VERIFICATO: il 48% di vincenti su 27 contro il 34% degli ingressi casuali con le stesse regole ha **p = 0,09**. È un
  vantaggio debole e non dimostrato: un periodo negativo successivo è del tutto compatibile.

**Profitto perso nella singola operazione e drawdown del portafoglio sono due cose diverse.** La prima (operazione
arrivata a +1R e poi chiusa in perdita) si misura per trade con il MFE. La seconda è la discesa dell'equity dal suo
massimo, causata qui soprattutto dalla **dimensione** (4× l'equity per posizione, fino a circa 2,7 posizioni insieme)
e dall'assenza di un freno: lo stop giornaliero della config è al 50%.

## 2. Esperimento preregistrato su candele reali (VERIFICATO)

Strumento: `research/brain_guardian/` (replay isolato, mai importato dal runtime).

* **Regole del replay**: candela da 1 minuto successiva all'ingresso; stop prima del target nella stessa candela;
  apertura oltre lo stop = uscita all'apertura; 2 bp di slippage sugli stop; 6 bp di commissione per lato;
  breakeven/trailing attivi solo dalla candela dopo; dimensionamento e margini del Brain.
* **Fedeltà**: sugli stessi ingressi e sulle stesse candele il replay della variante A riproduce motivo d'uscita, PnL
  netto e candela d'uscita del servizio uscite reale (test `test_replay_reproduces_the_real_exit_engine_on_the_same_bars`).
* **Dati**: Bitget 1m, 8 simboli del Brain, 01/10–18/11/2026, 69.549 minuti per simbolo, SHA-256 in
  `research/brain_guardian/results/`.
* **Ingressi di controllo**: ogni ora su ogni simbolo, lato casuale, stop uniforme 0,40–0,91%, 5 semi. Non hanno
  vantaggio per costruzione: misurano cosa fanno le **regole**, non il segnale.
* **Calibrazione** su ottobre, **verifica** su 1–18 novembre. Varianti fissate prima di eseguire.

Medie dei 5 semi, periodo di **verifica** (novembre):

| Variante | Operazioni | Vincenti | Netto USDT | Val. atteso (R) | PF | Drawdown max | +1R poi perse |
|---|---|---|---|---|---|---|---|
| A originale 2R/24h | 333 | 34% | −1.290 | −0,190 | 0,75 | 74% | 48 |
| B1 breakeven a 1R | 420 | **49%** | **−1.737** | −0,213 | 0,62 | 88% | **0** |
| B2 trailing da 1R | 426 | 39% | −1.742 | −0,224 | 0,60 | 88% | 41 |
| B3 parziale 50% a 1R | 335 | 35% | −1.435 | −0,207 | 0,67 | 76% | 46 |
| C1 stop ≥ 4× costi | 267 | 35% | −1.101 | −0,133 | 0,81 | 67% | 40 |
| C2 stop ≥ 1,5× ATR15 | 164 | 33% | −784 | −0,187 | 0,78 | 58% | 24 |
| D1 cooldown 4 h dopo stop | 319 | 34% | −1.587 | −0,188 | 0,71 | 82% | 51 |
| D2 max 2 nello stesso verso | 322 | 34% | −1.419 | −0,200 | 0,74 | 74% | 45 |
| D3 freni equity (−10% dal massimo, −5% al giorno) | 15 | 24% | −218 | −0,478 | 0,47 | **15%** | 3 |

In calibrazione (ottobre) l'ordine è lo stesso, tranne C1 e C2, che **non** migliorano (C1 −0,216R, C2 −0,250R
contro −0,206R). Combinazione scelta solo su ottobre: cambia a ogni seme per uscite e filtri (rumore); D3 viene scelto
da tutti e 5 i semi.

Controllo del dimensionamento, **aggiunto dopo** la preregistrazione (effetto meccanico):

| Novembre, media di 5 semi | Netto | Val. atteso (R) | Drawdown max | Operazione peggiore |
|---|---|---|---|---|
| Brain attuale (nozionale 4× equity) | −1.290 | −0,190 | 74% | −81 |
| Nozionale 1× equity (margine 5%, totale 15%) | −563 | −0,192 | 33% | −21 |
| 1× + stop ≥ 4× costi + freni equity | −147 | −0,174 | **11%** | −22 |

### Cosa migliora davvero e cosa no

1. **Dimensione della posizione: migliora, verificato.** A parità di segnale, perdite e drawdown scendono in
   proporzione; il valore atteso per R non cambia. È la causa principale della velocità con cui il Brain restituisce
   i profitti.
2. **Freni sull'equity di portafoglio: migliorano il drawdown, verificato.** Con nuove aperture bloccate a −10% dal
   massimo o −5% nella giornata, il drawdown scende dal 74% al 15%. Le uscite continuano sempre. Limite: frena anche il
   rialzo di una strategia con vantaggio, ed è un freno, non una fonte di profitto.
3. **Protezione del profitto aperto (breakeven, trailing, parziale): NON migliora senza un segnale con slancio.** Il
   breakeven azzera i trade "arrivati a +1R e poi persi" e porta i vincenti al 49%, ma il netto **peggiora**: il
   profitto restituito diventa una serie di uscite in pari che pagano commissioni. Vale la pena **solo** se gli
   ingressi veri del Brain mostrano continuazione dopo +1R. Va misurato sul journal (§5), non assunto.
4. **Stop minimo rispetto ai costi o alla volatilità: non dimostrato.** Migliora a novembre, non a ottobre. Il
   meccanismo è sensato (16 bp pesano circa 0,25R su stop da 0,65%), ma il dato non basta per imporlo come regola.
5. **Cooldown dopo lo stop e tetto di correlazione: nessun effetto utile con ingressi casuali.** Per costruzione qui gli
   ingressi sono indipendenti: vanno valutati sui rientri e sui gruppi correlati **veri** del journal.

**Soglia di pareggio** (VERIFICATO sul replay): con i costi attuali e stop di circa 0,65% il valore atteso senza
vantaggio è circa −0,2R per operazione. Al target 2R servono almeno circa il **41% di vincenti** per stare in pari. Il
Brain al 15/11 era al 48%, sopra la soglia ma di poco e su un campione minimo.

## 3. Policy di rischio comune proposta per DeepSeek, Qwen e MiniMax (decisione dell'utente)

Stesso hash di rischio per le tre AI. Nessuna config è stata modificata.

| Voce | Oggi (config Arena 2000) | Proposta | Motivo |
|---|---|---|---|
| Nozionale per posizione | 8.000 (margine 20% × 20×) | **≤ 2.000 = 1× equity** (margine 5% a 20×) | perdita per stop circa 1% equity invece del 4%; drawdown proporzionale (§2) |
| Nozionale totale | ~11.000 (margine 55%) | **≤ 3× equity** (margine 15%) | stesso motivo, meno stop simultanei |
| Freno giornaliero | 50% | **nuove aperture ferme a −5% del giorno** | §2, D3 |
| Freno dal massimo | assente | **nuove aperture ferme a −10% dal massimo** (uscite sempre attive; ripresa solo con decisione umana) | §2, D3 |
| Uscite | 2R, 24 h, stop prima del target | **invariate** | nessuna variante B migliora senza prove sugli ingressi veri |
| Stop minimo | nessuno (0,40% ammesso) | da decidere dopo il journal; candidato ≥ 4× costi (0,64%) | non dimostrato (§2, punto 4) |
| Registrazione | confidenza assente | **registrare confidenza e proposta pre-rischio** (lato, stop, leva) | rende misurabili i filtri futuri |

Con nozionale 1× la soglia di stop massima per la leva minima 20× resta invariata (0,91%). Il nozionale si riduce con il
margine, non con la leva. Il valore atteso per R delle tre AI resta confrontabile; la gara misura la qualità degli
ingressi con una perdita massima tollerabile.

## 4. Cosa resta da misurare sul Brain vero (con il journal)

1. Codice vivo: SHA, i 4 file modificati, config ed exit policy effettive.
2. Per giorno, 7 giorni e run completa: vincenti, media netta vinta e persa, valore atteso, PF, commissioni, drawdown
   realizzato.
3. Per operazione: MFE e MAE su candele 1m (operazioni arrivate a +1R e poi perse); uscite tardive
   (`close_delay_min > 0`); stop simultanei; rientri dopo uno stop e loro esito; regime, simbolo e lato.
4. Replay delle varianti sugli **ingressi veri**, separando calibrazione e verifica nel tempo.

## 5. Raccolta dei dati (sola lettura, da eseguire su Termius con l'OK dell'utente)

```
curl -fsSL https://raw.githubusercontent.com/alexiptv82/SuperBot-Trading/<SHA>/deploy/scripts/brain-audit-export-readonly-20261118.sh -o /tmp/brain-export.sh
sudo bash /tmp/brain-export.sh --sha <SHA>
```

Produce `/root/brain-audit-<ora>.tar.gz` (permessi 0600), che si scarica e si carica nella sessione. Contiene:

* unità e processi vivi (cwd, riga di comando, `PYTHONPATH`, nomi delle variabili; valori solo per le variabili
  `V3_*`/modalità, mai chiavi);
* SHA, file modificati e diff (oscurato) delle cartelle di codice usate dai processi;
* config ed exit policy effettive;
* `journal-export.json`: aperture, chiusure con commissioni e motivo, decisione collegata, decisioni per ora,
  heartbeat, spesa AI. Nessun testo del modello.

Non ferma, non riavvia e non modifica nulla. Unica traccia nella run: l'indice `-shm` del database in WAL, aggiornato
da qualunque lettore. Poi, qui:

```
python -m research.brain_guardian.experiment brain --bars <candele 1m> --export journal-export.json --out brain.json
```

produce fedeltà (motivo e PnL reali contro replay), uscite tardive e tutte le varianti sugli ingressi veri.
