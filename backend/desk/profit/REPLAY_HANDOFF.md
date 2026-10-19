# Sequenza concordata il 19 ottobre, pomeriggio

Il messaggio utente delle 17:27 Europe/Zurich sostituisce le indicazioni precedenti.
Ombra futura su Hawk E Bull. +25/30% e un checkpoint di valutazione, non uscita
obbligatoria. Nessuna attivazione, nuova run o deploy in questa consegna.
L'utente richiede OK esplicito al momento dell'avvio, backup fresco verificato,
assenza posizioni aperte, vecchie run e memoria conservate. Claude prepara il
deploy dopo revisione. ChatGPT sviluppa sul ramo work/profit-manager.

## Prima consegna da revisionare: estrazione delle prove

`backend/desk/extract_replay_input.py` va revisionato PRIMA di usarlo sui dati
reali. Test eseguiti solo con fixture sintetiche. Legge una copia offline
verificata del cervello, non il filesystem del bot in esecuzione. Non modifica
la copia originale. Quattro file obbligatori: state_v2.json, trade_history.jsonl,
learning_log.jsonl, heartbeat.json. Manifesto esterno JSON: mappa esatta dei
quattro nomi agli SHA-256 gia verificati del backup, non autocertificazione di
un'origine arbitraria. L'estrattore controlla i byte, non prova da solo che il
backup sia stato creato a fine ciclo: usare la procedura backup esistente.

Esempio (percorsi privati, fuori dal checkout; non contiene credenziali):

```
PYTHONPATH=backend python -m desk.extract_replay_input \
  --source /private/verified-backup/hawk \
  --expected-manifest /private/hawk-source-hashes.json \
  --output /private/hawk-run3-evidence \
  --portfolio hawk --run 3
```

Per Bull: portfolio bull, run 2, percorsi separati. Output esclusivo, directory
0700 e file 0600. stdout contiene solo esito e replay_ready=false. Non usare
upload di artifact pubblici, commit di output o il workflow sg-bots-check per
trasportare i registri privati. Non esiste un automatismo di trasferimento in
questa consegna. Il pacchetto contiene raw evidence e COVERAGE.json con hash.

Perche non genera input.json: nel codice ispezionato gli eventi open non
registrano qty/fee_open completi e non esiste uno snapshot contabile ad ogni
ciclo. Posizioni finali e chiusure non dimostrano il percorso intermedio.
L'estrattore segnala questo limite, non inventa una ricostruzione. Una successiva
ricostruzione puo coprire un sottoinsieme dimostrabile, con esclusioni motivate;
non richiedere un finto campione completo per soddisfare il formato del runner.

## Input aggiuntivi da concordare con Claude

1. Backup verificato, manifesto e collocazione privata accessibile per l'analisi.
2. OHLC 15m originali con semantica timestamp, copertura warmup e almeno due ore
   dopo il checkpoint. Se disponibili, prezzi piu frequenti per simulare i fill.
3. Eventi delle modifiche (DCA, split, parziali), regole/versioni di fee e funding,
   e orari effettivi dei cicli. b4709d1 dichiarato non prova tutti gli SHA storici.
4. Per ogni campo ricostruito, fonte/assunzione; gli ignoti restano ignoti.

## Protocollo del confronto da implementare dopo verifica della copertura

Stessi ingressi e costi, quattro varianti indipendenti:
- ATR: preset research-1 esistente, nessuna modifica silenziosa.
- A: protezione dinamica in ROI netto, armamento proposto 15%, pavimento iniziale
  5%, give-back massimo 5 punti di ROI; valori da rivedere con Claude.
- B: stessa A con uscita a 25%, solo benchmark, non filosofia scelta dall'utente.
- Checkpoint: a 25% rivaluta trend/inversione; tiene con spinta, propone uscita
  con due famiglie concordi, variante di proposta parziale da confrontare.

Parziali Hawk restano disabilitati nella policy corrente. La variante di ricerca
non deve rimuovere questa guardia operativa di nascosto; frazione esplicita,
versionata e con contabilità separata del residuo. Nessun reversal automatico
long/short, rientri vincolati ai segnali originali e ai limiti del portafoglio.

Decisioni solo su barre chiuse disponibili al ciclo: campionamento 30m con fase
temporale reale se disponibile, altrimenti scenari dichiarati. Fill successivo
alla decisione con spread, slippage e fee; gap non riempiti al floor. Per dati
15m si dichiara l'incertezza intrabar, non si inventa ordine high/low.

Misure per trade: checkpoint netto >=25%, attraversamento in perdita entro 2h
(distinguere entro 2h da valore esattamente a 2h), P&L netto, costi, give-back,
movimento favorevole successivo perso. Trade senza due ore di copertura sono
censurati, non successi. Deduplicare checkpoint per posizione o dichiarare la
regola. La traiettoria ipotetica dopo uscita baseline richiede modello esplicito.
Parziali: il profitto realizzato e sommato al residuo, senza duplicare fee/funding.
Niente equivalenza tra somma dei trade indipendenti e performance portafoglio:
liberare slot cambia gli ingressi, serve simulazione di portafoglio separata.

## Passi seguenti, non ancora implementati

Adapter storico validato e confronto esecutivo; writer append-only con dedup e
retention senza cancellazione non approvata; aggancio ombra isolato dal conto;
vista app; copertura backup del nuovo registro e prove conto invariato. Claude
rivede ogni modifica prima del merge. A-D restano fuori da questi cambiamenti.
Confronto a tre dopo qualche giorno: checkpoint informativo, non promozione
automatica ad attivo.
