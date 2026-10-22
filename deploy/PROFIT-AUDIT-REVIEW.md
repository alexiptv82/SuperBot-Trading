# Audit salva-profitto — proposta per Claude, non eseguita

Ramo work/profit-audit-readonly, base rule-pool 2b491cd. Nessun trigger incluso.
L'OK dell'utente autorizza la preparazione: prima della run servono review e OK
separato per merge/trigger. Contesto serale ricevuto dall'utente non sostituisce
una misura. Nessun importo o simbolo di posizioni compare nel report pubblico.

## Domande e identificabilita'

Finestra Roma 22/10: [2026-10-21T22:00Z,2026-10-22T22:00Z), tagliata all'istante
osservato. Include posizioni aperte prima di mezzanotte e file AI di entrambi i
giorni UTC. Fotografia runtime datata separatamente se letta dopo il termine.

- a: ricostruisce internamente posizioni attive, aperture, opportunita' di chiamata
  durante il loro intervallo e chiusure/parziali registrati. Il source del close
  e' il source dell'INGRESSO, non dell'uscita: mai attribuire una chiusura a Claude
  soltanto per quello. Il vecchio registro non salva le azioni riuscite per
  posizione o quelle omesse: conteggi esatti hold/omessa restano null. Un timestamp
  corrente last_review_ms abbinato a claude_call riuscita prova al massimo un
  hold minimo, non la storia completa. Non inventare decisioni dal n_decisions.
- b: verifica l'intera hash chain dei journal sidecar e correla per bot/run/id/
  symbol/open_ms (solo in memoria). Checkpoint CHIUDI_O_PARZIALE/LASCIA_CORRERE,
  ROI per fasce e ora relativa al giorno locale, applied=false. Mancanza di
  journal o ROI non e' HOLD. Non esporta chiavi posizione o identificativi grezzi.
- c: conto DeepSeek separato: conteggi cicli/chiamate/fill per lato e chiusure;
  nessuna contribuzione ai bot. Filtra anche la coda del file UTC del 21/10.
- d: aperture bot x lato x source rules/claude x code_version; istogrammi dei due
  score. Bonus non registrato numericamente: ricostruzione nominale soltanto con
  cinque versioni revisionate e sha256 di seasonal.py gia' verificato nello Step 5.
  Report distingue ricostruito, non revisionato e incremento ignoto per score
  cappato a 100. Non spaccia un valore ricostruito per misura diretta.
- e: fotografia runtime mode/calendario/budget per fasce percentuali, ultime
  chiamate registrate. Mancano eventi storici di skip per causa e log completi
  per posizione: inizio esatto del blocco e n senza review A CAUSA del budget
  sono null. La contemporaneita' fra ROI corrente >=50 e budget sotto riserva
  e' una co-occorrenza, non un nesso causale. Non dedurre blocco dal 95% soltanto.

Queste lacune non si riparano rileggendo screenshot o inventando una timeline.
Il futuro decision log (pacchetto fix/progetto ombra) serve proprio a eliminarle.
Se si esegue dopo il 22, il budget corrente non e' il budget storico del 22.

## Sicurezza e output

PAPER dal Docker env prima/dopo, identita' ID/immagine/StartedAt in trap anche su
errore; confronto YAML caricato/congelato. Checkout temporaneo separato. Docker
usa immagine Hawk esistente per ID, --network none --read-only, capability e
risorse limitate; /data, /sidecar, /ai e codice montati :ro. Nessun docker exec
nei bot, stop/restart, chiave API o accesso a Bitget. Scrive solo artifact JSON
aggregato sul runner e cartella temporanea del checkout. Non legge prompts AI
con testo libero, non usa docker.sock. Errori a codici fissi, niente traceback.

Snapshot byte-identici prima/dopo per ogni input; append durante l'audit blocca
la misura. JSONL rigoroso e symlink/canonicalita' controllati. Limiti 32 MiB per
file e 64 MiB totali: oltre limite fallisce, non tronca. Nessun writer Journal
importato/istanziato, nessuna rotazione o riparazione dei registri.

Output allowlist: conteggi, istogrammi score/ROI, hash, enum fissi, versioni
esadecimali, tempi aggregati. Niente simboli, prezzi, singoli trade, importi,
saldi o stringhe libere degli input. Unknown/null rimangono espliciti.

Test sintetici: privacy con stringhe sentinella, hash chain corrotta, timestamp,
coda UTC, bonus ricostruito, attivita' AI indipendente, assenza di decision log,
PAPER/staleness, symlink e guardie workflow. py_compile, YAML/bash prima del push.
Non sono risultati runtime. Esistenza/capienza dei journal, freschezza e
copertura della finestra restano da verificare con run autorizzata.
