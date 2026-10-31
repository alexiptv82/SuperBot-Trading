# Backup e ripristino coordinato Brain PAPER

Questo pacchetto e' preparazione offline. Non ferma, installa, inizializza o avvia
alcun servizio. Non sostituisce il backup dei classici e non cambia strategie,
mandato, provider o rischi. Base servizio c23a0699ead68420d03d8c7d3399fc6766884f66;
app compatibile fissata a 3ce2f9915c75e7cb76b60e97575d578af7db14d5;
classici aff1191968723bfdeb54dd968dbd18bcc21c5036, da distribuire separatamente.

## Topologia da fissare nel pacchetto operativo

| Componente | Fonte | Ripristino isolato |
|---|---|---|
| Conto, eventi, budget prenotato AI, memoria episodica | BRAIN_SINGLE_DATA_DIR/brain/brain_scalp.sqlite3 | brain/brain_scalp.sqlite3 |
| Registro chiusure manuali, apprendimento consultivo, lezioni | stessa directory brain/ | file invariati |
| Deduplica comandi Telegram | brain/brain_operator_updates.jsonl | file invariato |
| Storico notifiche provider | BRAIN_SINGLE_DATA_DIR/brain.notifications.sqlite3 | stesso nome |
| Conferme app | BRAIN_OPERATOR_INBOX_PATH, anche esterno | control/operator.sqlite3 |

Il parametro --inbox deve corrispondere all'effettivo BRAIN_OPERATOR_INBOX_PATH.
Se le conferme sono disabilitate si omette --inbox. Non e' possibile dedurre la
configurazione di una inbox esterna da una cartella dati: il chiamante deve
fissare questa topologia. File durevoli non riconosciuti nella cartella dati
fanno fallire il backup, anziche' essere omessi. Snapshot e gruppi review
pubblicati restano fuori dalla cartella privata: sono proiezioni da rigenerare,
non autorita' finanziarie da ripubblicare come fresche.

## Creare e verificare il backup

I comandi seguenti sono modelli da eseguire nell'ambiente isolato appropriato,
con percorsi effettivi. Le variabili devono essere gia' definite. Non eseguono
un arresto implicito: se un owner e' attivo il backup viene rifiutato.

```bash
PYTHONPATH=backend python -m director.brain_scalp.recovery_bundle backup \
  --data-dir "$BRAIN_SINGLE_DATA_DIR" --inbox "$BRAIN_OPERATOR_INBOX_PATH" \
  --destination "$BRAIN_RECOVERY_BUNDLE"
PYTHONPATH=backend python -m director.brain_scalp.recovery_bundle verify \
  --bundle "$BRAIN_RECOVERY_BUNDLE"
PYTHONPATH=backend python -m director.brain_scalp.recovery_bundle restore \
  --bundle "$BRAIN_RECOVERY_BUNDLE" --destination "$BRAIN_RECOVERY_STAGE"
```

Il backup prende i lock esclusivi del wallet, teaching, comandi e notifiche e
blocca contemporaneamente i writer SQLite di tutte le code configurate. I dati
WAL committati vengono copiati con l'API SQLite backup, non con copia del file
attivo. Le copie sono ricondotte a journal DELETE e le connessioni chiuse prima
di verificarne inventario, integrita', identita', dimensioni e SHA256.
Non modificare o consumare le code sorgenti. Nessun corpo provider o segreto
va aggiunto al manifesto. Il bundle contiene dati privati PAPER: non committarlo
nel repository pubblico. Il manifesto protegge da corruzione accidentale, non
autentica un archivio sostituito insieme ai suoi hash.

Destinazione nuova ed esterna all'origine, directory 0700, file 0600. Il manifesto
viene pubblicato per ultimo. Una pubblicazione interrotta puo' lasciare una
directory incompleta, che deve essere scartata dopo verifica; non viene
sovrascritta automaticamente. Conservare il backup precedente verificato.

## Ripristino di un backup vecchio: nessun reinvio implicito

Un evento pending nel backup potrebbe essere stato completato dopo il backup.
Per questo il ripristino conserva gli ID, gli esiti storici, i tentativi e tutto
il conto; cambia solo gli stati delle operazioni accodate:

| Stato nel backup | Stato nella copia ripristinata |
|---|---|
| Notifica pending o inflight | uncertain |
| Conferma pending o processing | needs_reconciliation |
| Esiti definitivi e gia' incerti | invariati |

Le operazioni incerte vanno riconciliate fuori dal comando di restore. Non sono
rispedite automaticamente. Il file RESTORE.json riporta i conteggi e
ready_to_start=false. Il conto mantiene identita', versione, eventi e contenuti
delle memorie. I lock sono ricreati dai proprietari: copiare il loro contenuto
non conserverebbe un lock di processo.

L'API app va fermata/scollegata dal vecchio percorso prima di ricollegarla alla
nuova inbox: nessun doppio consumer. La nuova BRAIN_OPERATOR_INBOX_PATH sara'
<stage>/control/operator.sqlite3; il data-dir sara' <stage>. Aggiornare anche
il percorso nell'app, con la stessa origine HTTPS autenticata. Non riusare
snapshot/review vecchi come se fossero correnti. Nessuna nuova istanza va
avviata con il vecchio owner ancora attivo.

## Ultime condizioni operative

Il backup finanziario di BrainService.backup resta invariato: questo comando
aggiunge il pacchetto coordinato separato. Non dichiarare che il vecchio
workflow backup esterno includa automaticamente le nuove code. Installazione,
retention esterna cifrata e collegamento ai workflow richiedono il piano
operativo definitivo; nessun trigger o servizio esistente e' modificato qui.

Prima di un avvio dopo restore: riconciliare azioni e costo AI successivi al
backup (il budget persistito e' un limite conservativo storico, non il credito
reale); verificare mandato completo, provider/modelli/prezzi/budget,
destinazione Telegram e relativi permessi. Credito residuo non deducibile dalle
fixture. Collaudo PWA autenticata/feed/Telegram e OK al rilascio restano aperti.
La qualita' economica, il ricercatore autonomo e la validazione fuori campione
non sono dimostrati dal restore. Il LONG resta affidato all'altra AI.

## Verifiche riproducibili offline

```bash
PYTHONPATH=backend python -m pytest -q backend/tests/test_brain_recovery_bundle.py
```

I test usano un vero conto PAPER temporaneo con apertura, chiusura manuale
profittevole, conferma e memoria; confronto integrale di stato/eventi dopo
restore, deduplica e mancato reinvio delle vecchie code, WAL committato con
writer ancora aperto, blocco di tutti gli owner, inbox impegnata, manomissioni,
file mancanti/extra, symlink, traversal, destinazioni esistenti, notifiche
disabilitate e inbox interna. Nessuna chiamata esterna o conto operativo.
