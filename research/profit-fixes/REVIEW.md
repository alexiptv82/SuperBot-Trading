# Pacchetto fix — proposte A con patch e test, B solo specifiche

Base rule-pool 2b491cd. Nessun merge, trigger o deploy. NON approvazione delle
modifiche operative. I file A modificati sono patch di prova sul ramo work/.
Anche una correzione di dati modifica gli score/input dell'LLM e puo' cambiare
le decisioni: classe A non significa comportamento invariato o deploy libero.

## A — correttezza, implementata solo su questo ramo di proposta

| Punto | Patch di prova | Verifica |
| --- | --- | --- |
| EMA lenta 4h | Fetch nativo 4H/300, cache per bucket 4h, solo barre chiuse/regolari; confronto EMA50/EMA200 solo con >=200 vere barre. Altrimenti nd, niente EMA61 chiamata EMA200. | Test su storia insufficiente, gap, duplicati, barra aperta, granularita' cache. |
| Altri indicatori nella stessa finestra | 1000x15m danno circa 250 barre 1h: EMA20/50 1h, RSI/ATR14, ROC24 e breakout20 hanno storia sufficiente; contesto 1d usa cache separata >=200 giorni, fallback 10 giorni non valido per EMA200. | Ispezione finestre, nessuna promessa di indipendenza o convergenza infinita EMA. |
| score_ora | Punteggio del lato della posizione e score opposto separati; mancante=None. | Long con score L10/S85 mostra 10, non 85. |
| Scheda posizione | TP, total_margin, ROI lifecycle netto, R sul rischio iniziale, MFE/giveback di PREZZO etichettati upper bound. | Confronto con liquidazione di un clone dopo parziale; niente API. |
| Uguaglianze | EMA, prezzo/EMA, trend giornaliero neutrali; RSI=50 non assegna punti; candela senza direzione non assegna volume a long. | Serie piatta senza bonus: L0/S0, lato neutro. |
| RSI piatto | Nessun guadagno/perdita =>50, non 100. | Test regressione. |
| Esempio Bull | Aritmetica leva/stop/target corretta, senza modificare istruzioni RR o filtri. | Assert esempio e rapporto. |

Scheda comune in desk/position_card.py, funzione pura. ROI = (netto realizzato
parziali + netto liquidabile del residuo) / (margine iniziale effettivo + DCA
versati). Come il sidecar, il riferimento non diminuisce con i parziali e non
oscilla col prezzo; aumenta quando si versa NUOVO margine DCA. Non e' quindi
letteralmente costante attraverso un DCA. Questa distinzione va approvata:
se si vuole un denominatore immutabile dall'apertura, limitare prima coorte a
trade senza DCA oppure cambiare insieme definizione del sidecar e dei confronti.
Non scegliere silenziosamente il denominatore che fa superare il 50%.

R netto usa risk_plan_usd iniziale costante. MFE/giveback di prezzo dalle
candele possono includere movimenti non eseguibili; non equivalgono a un picco
NETTO online dopo costi/parziali. observed_peak_net_roi e giveback_net_roi sono
null finche' non esiste un journal prospettico di valutazioni. Non inventarli.

## B — cambi di comportamento, NON implementati

- Bonus stagionale statico: proporre mantenimento/rimozione solo dopo diagnosi;
  il ramo non lo rimuove. Speculare on/off e' diagnostica, non scelta vincente.
- Hold con nuovo TP/stop: nuove azioni esplicite e validate, per evitare che hold
  modifichi protezioni implicitamente. Nessun allargamento stop. Non implementato.
- Review AI del profitto: specifica sotto, nessun trigger automatico a 50 installato.
- Copertura: una riga di decisione per ogni posizione dello snapshot, inclusi
  hold/skip e motivo; validatore di copertura e gestione prima delle nuove aperture.
  Una decisione su un asset non deve nascondere omissioni sugli altri. Non implementato.
- RR: scegliere un contratto unico per portafoglio e validarlo nello stesso punto;
  oggi codice 1,5, Hawk 2, Bull 2/2,5. Nessuna soglia modificata da questa proposta.
- Prompt di INGRESSO: non riscritto prima della diagnosi. Solo esempio numerico
  e scheda dati corretti in A; le istruzioni di selezione restano quelle esistenti.

## Specifica da concordare: review discrezionale del profitto

Circa +50% di ROI e lunga durata fanno salire la priorita' della review, non
emettono un ordine. Registrare soglia e policy approvate prima della raccolta.
Il modello deve spiegare se esistono evidenze contemporanee di continuazione:
struttura/prezzo su supporti/resistenze, trend su TF validi, momentum e volume;
almeno due famiglie distinte proposte, con qualita'/eta' dei dati dichiarate.
Lo score o il profitto gia' ottenuto, da soli, non bastano.

Con dati validi: se evidenze insufficienti, proposta close totale; se sufficienti,
proposta partial 0,5 e tesi/condizione di invalidazione per il residuo. Non
trasformare evidenza mancante per guasto/staleness in una chiusura cieca:
proporre status data_invalid con alert e protezioni esistenti, da decidere
esplicitamente con l'utente. Dopo il parziale massimo una riduzione per trade
nella prima versione proposta; eventuale seconda richiede regola preregistrata.
Fee e slippage per quantita' effettiva: spezzare la stessa quantita' non raddoppia
automaticamente una fee proporzionale, ma tempi/prezzi/costi possono cambiare.

Decision log privato append-only per OGNI posizione e ogni slot di valutazione:
schema, review_id, bot/run/position identity, timestamp e available_at,
input hash, code/prompt/policy hash, ROI/R e denominatori, data quality,
action, fraction, evidence families, thesis, invalidate_if, confidence,
coverage status, source/model, budget decision/skip reason, proposal/applied,
execution receipt separato. Nessun testo libero pubblico. Registrare anche
omessa/invalida/non richiesta; distinguere risposta modello, accettazione ed
esecuzione. Non cancellare o riscrivere il cervello per introdurlo.

Budget esaurito: proporre riserva preventiva per gestione, batch e priorita'
vs nuove aperture; log esplicito skipped_budget e alert. Nessun subentro
esecutivo DeepSeek, nessun aumento budget o chiusura automatica per assenza
LLM autorizzati qui. Restano TP/SL e fallback esistenti fino a decisione.

Apprendimento verificabile: valutare MFE/MAE per lato, setup all'ingresso,
netto alla review e traiettoria successiva, distinguendo errore d'ingresso
ed errore d'uscita. A/B futuro contro +1,5R e C, con decisioni AI solo online;
nessun LLM che rilegge il passato vedendo gia' l'esito.

## Mirror-pair: risultati ottenuti, limiti e riproduzione

Tool deploy/scripts/mirror_pair_audit.py. Trasformazione p'=1/p, high/low
scambiati, volumi e timestamp invariati. Stagionalita' on/off, vecchio sorgente
contro patch. Nessuna chiamata LLM o chiave API. Sorgenti/ingresso identificati
con SHA-256 in mirror-results.json; nessun dato OHLC grezzo nel repo.

Acquisizione pubblica Bitget /api/v2/mix/market/candles; quattro serie di mercato,
16 finestre reali molto sovrapposte e 12 sintetiche (trend, piatto, oscillante).
La sorgente 1D di questo endpoint ha meno di 200 giorni: il contesto giornaliero
reale non viene attivato. Il recupero storico 1D del bot e' un'altra procedura.
Le candele pubbliche sono input di diagnostica, non i trade del conto.

| Sorgente / serie | Bonus | Differenza assoluta media score speculari | Max | Long originali sopra soglia | Short originali sopra soglia |
| --- | --- | --- | --- | --- | --- |
| Baseline / reali | off | 1,25 | 12 | 0% | 12,5% |
| Proposta / reali | off | 1,25 | 12 | 0% | 0% |
| Baseline / reali | on | 4,50 | 14 | 0% | 12,5% |
| Proposta / reali | on | 4,50 | 14 | 0% | 0% |
| Baseline / sintetiche | off | 10,375 | 50 | 33,33% | 25% |
| Proposta / sintetiche | off | 0 | 0 | 33,33% | 25% |
| Baseline / sintetiche | on | 12,375 | 52 | 33,33% | 25% |
| Proposta / sintetiche | on | 2 | 2 | 33,33% | 25% |

Risultati completi incluse soglie della serie invertita e McNemar in JSON.
McNemar sulle decisioni selezionate long originale vs short speculare e viceversa:
conteggi b/c e p esatto NOMINALE, solo descrittivo. Le finestre si sovrappongono,
non sono coppie indipendenti; non interpretare p come conferma di simmetria
strategica, ne' il non-rifiuto come equivalenza. EMA aritmetiche, ATR e rendimenti
percentuali non sono invarianti a 1/p: una differenza residua non e' di per se'
un errore. Le medie su vero 4h cambiano gli ingressi potenziali; nessuna stima
qui dimostra miglioramento economico. Il JSON e' il riferimento numerico.

Riproduzione: input OHLC resta in snapshot privato con hash riportato. Fornire
lo stesso --input e un --baseline-source estratto dal commit base, poi eseguire
con PYTHONPATH=backend. Il runner di diagnostica non scarica dati.
Verifiche: 9 nuove prove unittest, 4 test preesistenti sulla riga CONTO richiamati
direttamente (pytest non disponibile), py_compile e diff check. Non e' una
suite completa del motore o una verifica CI Python 3.11.

## Sequenza prima di Step 6

1. Review audit e diagnosi prima di cambiare il prompt d'ingresso; review A/B e
   decisione utente sui singoli comportamenti e sulla definizione ROI.
2. Completare i fix approvati, test regressioni e un solo commit/insieme congelato.
3. Un SOLO deploy dei bot, separatamente autorizzato, PRIMA di S; backup del
   cervello e controllo PAPER/identita'/versione con procedure esistenti.
4. Confermare nuova code_version runtime e config fingerprint; aggiornare
   baseline_version e reviewed_versions nel piano draft, verificare OHLC,
   ledger di continuita' e snapshot, approvare/registrare commit completo.
5. Fissare S futuro dopo registrazione e dopo deploy verificato. Nessun cambio
   bot fra S e F. Qualunque cambio versione invalida quella coorte, non si
   scartano selettivamente solo i trade modificati. Ombra separata non cambia
   uscite/code_version, ma monitorare interferenza di risorse e latenza.
