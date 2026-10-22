# DeepSeek in ombra sulle posizioni Hawk/Bull — progetto, non installazione

Decisione utente 22/10/2026 21:25 Roma: osservare e registrare cosa farebbe
DeepSeek sulle posizioni vere dei bot PAPER. MAI subentrare a Claude con
esecuzione. Nessun codice d'ordine, deploy, trigger o installazione in questo ramo.

## Dipendenze e separazione

Componente director/bot_position_shadow proposto, distinto dal pilota del conto
virtuale. Legge /data/{hawk,bull} montato :ro, non monta docker.sock, non ha chiavi
Bitget o comandi di controllo dei bot. Scrive solo /out/bot-shadow nell'area AI.
Filesystem immagine read-only, tmpfs limitato, cap-drop ALL, no-new-privileges,
CPU/RAM/pid e timeout stretti. Rete necessaria solo per API modello e dati pubblici:
non promettere --network none per un componente che deve chiamare DeepSeek.
Audit/replay successivi invece offline --network none.

L'installatore futuro deve verificare PAPER e ID/immagine/StartedAt dei due bot
prima/dopo, anche su errore. Non deve fermarli, ricrearli, cambiarne mount,
ambiente, immagini o file. Può sostituire il SOLO servizio AI, con OK separato.
Distribuire il nuovo codice ombra in immagine indipendente non cambia la
code_version dei bot. Nessuna proposta e' inviata al loro esecutore.

Scheda posizione: dipende da A, con stesse formule sidecar di netto lifecycle,
reference margin iniziale+DCA non ridotto dai parziali e rischio iniziale per R.
Il riferimento aumenta in caso di nuovo DCA, non e' costante in quel caso:
serve decisione esplicita sulla definizione. Prima coorte no-DCA suggerita se
si vuole un riferimento letteralmente immutabile. Il bot esistente puo' continuare
DCA: quei trade restano osservati e contati ma fuori dal confronto primario
no-DCA predefinito. Non cambiare i bot per costruire la coorte.

Non congelare o azzerare il cervello. La condivisione di funzioni pure di lettura
non significa importare CLI/Pilot che possano scrivere o eseguire ordini.

## Cadenza, selezione e budget complessivo

Poll delle nuove barre chiuse ogni 15 minuti; decisioni in batch su tutte le
posizioni dello snapshot, massimo 16 con limiti attuali (10+6, da confermare
runtime). Una chiamata base all'ora se esistono posizioni; fino a 15 chiamate
aggiuntive per priorita' preregistrate: primo attraversamento ROI ~50%,
deterioramento strutturale con almeno due famiglie, oppure trade >=6h e ROI
>=25% non rivalutato nell'ora. Queste sono proposte da approvare, non filtri
installati. Mai aggiungere dati futuri per giustificare una review tardiva.

Massimo proposto 39 chiamate/giorno per questo braccio, massimo input 8000 token
verificato da tokenizer compatibile, massimo output 2200, thinking disabilitato,
no tool/search, nessun retry automatico dopo errori o output troncato. Ogni slot
senza chiamata registra not_scheduled/no_positions/budget/data_invalid.
Non chiamare il modello solo su vincenti senza registrare gli esclusi: rendere
visibile la selezione per ROI/durata/lato.

Listino ufficiale verificato il 22/10:
https://api-docs.deepseek.com/quick_start/pricing/
Modello deepseek-flash (versione pubblicata DeepSeek-V4.1-Flash-1017): input
cache miss 0,30 $/M e output 1,20 $/M in picco; fuori picco meta'. Stima conservativa
senza cache, tutto in picco, margine 25%:
(8000*0,30 + 2200*1,20)/1e6 *1,25 = 0,00630 $/chiamata;
39 chiamate = 0,24570 $/giorno. Non sono costi misurati di produzione.
La cache puo' ridurre il costo, non e' assunta per garantire il limite.

Ripartizione PROPOSTA: 0,25 $/giorno al nuovo braccio, 0,15 $ al conto virtuale,
resto del tetto 0,50 come riserva non automaticamente spendibile. Anche il tetto
mensile esistente 12 $ resta valido: 30 giorni a 0,39570 costano 11,871 $;
31 giorni 12,26670 e richiedono skip/riduzione per rispettare 12. Nessuna promessa
di copertura H24 completa con budget fisso. Le assegnazioni restano decisioni
utente: non ridurre in silenzio la cadenza del conto virtuale attuale.

Serve UN proprietario del budget complessivo o broker locale di prenotazioni
atomiche con lock e ledger append-only condiviso dai due bracci. L'attuale
Budget non e' un arbitro sicuro per due writer: non basta condividere spend.jsonl.
Prenotare worst-case PRIMA della chiamata; riconciliare uso effettivo; dopo crash
con risposta persa mantenere la prenotazione prudente finche' la spesa e' chiarita.
Quote per braccio + cap globale giornaliero/mensile. Su registro corrotto, prezzo
non revisionato o tokenizer incompatibile: blocco, non spesa azzerata.

Prezzi e alias possono cambiare: registrare modello risolto, listino/versione,
usage, latenze e costi nel registro privato. Modifica del provider/modello durante
la coorte invalida quella valutazione AI (non riscrive il passato). Il listino
corrente e il margine di sicurezza non garantiscono che un futuro aumento sia
rilevato automaticamente. Controllo prima dell'installazione e prima della coorte.

## Contratto decisionale online

Una riga per ogni posizione dello snapshot: HOLD, PARTIAL_CLOSE(0,5), CLOSE,
oppure stato non_decided con codice. applied=false obbligatorio. Nessuna OPEN,
DCA, MOVE_STOP o comando che modifichi le protezioni dei bot in questa versione.
Per evitare riduzioni ripetute sullo stesso trade, mantenere anche lo stato della
politica controfattuale: massimo un parziale simulato, poi hold/close del residuo.
Non fingere che la posizione osservata del bot sia stata ridotta dalla proposta.

Decisione al netto dei costi, con evidence families, tesi, invalidate_if e dati
mancanti. Con dati validi e profitto importante: chiedere prove positive di
continuazione; se insufficienti, close; se presenti, partial 0,5 e piano del
residuo. Condizione della visione utente, non una regola esecutiva installata.
Dati invalidi non equivalgono ad assenza di edge: log skip/alert, non close cieco.

Schema JSON allegato rappresenta il CONTRATTO, non un componente operativo.
Il validatore futuro deve anche controllare uguaglianza esatta fra identita'
delle posizioni input e output, nessun duplicato, cardinalita', congruenza tra
action e fraction. La sola validazione JSON Schema non prova la copertura.

Journal privato append-only e hash chain: batch_id, bot/run/position identity,
input_frozen_ms, available_at di ogni dato, market_asof_ms, requested/received_ms,
source snapshot hashes, prompt/policy/model/listino hash, scheda ROI/R e reference,
risposta originale limitata, esito parsing, una decisione per posizione (inclusi
skip/omessa), proposal e applied=false. Nessun trade ID o testo libero pubblico.
Non riscrivere il learning_log dei bot per registrare l'ombra.

Input solo informazione disponibile a input_frozen_ms. Dati ricevuti dopo quel
momento appartengono al batch successivo. Vietato rivalutare un prompt storico
con candele future o riprovare finche' arriva la risposta preferita. La risposta
arriva spesso DOPO l'apertura della barra seguente: nel replay usare la prima
apertura successiva a received_ms + latenza operativa preregistrata, non una
apertura gia' trascorsa quando il modello ha risposto. Clip al confine baseline.

## Valutazione prima dei risultati, senza peeking

Proposta iniziale solo DESCRITTIVA in shadow, nessun test o gate di promozione.
Registrare prima dell'avvio S_AI futuro, 42 giorni di ingressi e 14 di maturazione,
versione bot/configurazione e modello/prompt/policy congelati. Nessun risultato
economico fino a F_AI; prima, solo qualita', copertura e spesa. Insufficienza
alla scadenza => inconclusivo, nessuna estensione scelta dopo aver visto gli esiti.

Minimi proposti per bot: 100 posizioni pulite, 30 episodi, 200 proposte modello
(non 200 posizioni indipendenti), 50 posizioni con review ROI importante. Riportare
anche gli strati assenti: niente forzatura di long in un mercato tutto short.
I minimi sono euristiche di adeguatezza, non una dimostrazione di potenza.

Confronti appaiati sulle stesse aperture e stesso rischio iniziale: DeepSeek
contro uscite reali, decisione reale di Claude quando effettivamente registrata,
sidecar deterministico e riferimento C. Le vecchie decisioni Claude non salvate
restano non confrontabili, non vengono ricostruite da n_decisions o dal source
di ingresso. Serve il decision log di B per un confronto pieno prospettico.

Metriche: distribuzione delta R per bot/lato/durata, net R e costi R, attivazioni,
MFE/MAE di prezzo etichettati upper bound, quota di profitto restituito dai soli
snapshot netti online, copertura/skip e ritardo. Raggruppare episodi interi,
leave-one-episode-out, due meta' temporali, stress 2/4/8bp e ritardo; nessun ranking
sul migliore fra molti prompt. Un risultato descrittivo promettente autorizza
solo proposta di un nuovo test confermativo e nuova decisione utente.

Se in futuro si vogliono test confermativi paralleli a Step 6, preregistrare
l'intera famiglia e la molteplicità del programma; non aggiungere tacitamente
due test AI ai due esistenti. C resta descrittiva nel piano attuale.

## Compatibilita' con OOS e autorizzazioni residue

Conferma architetturale: un osservatore separato, senza feedback/esecuzione,
non cambia code_version o uscite dei bot, quindi non invalida DI PER SE' la
coorte Step 6. Non e' una prova che non interferisca con CPU/RAM/rete: imporre
limiti e registrare ritardi/riavvii. Preferire installazione e prova carico
prima di S; un'installazione dopo S richiede controllo della continuita' e
possibili contaminazioni operative, non un lasciapassare incondizionato.

Prima: review A e schema ROI, audit fonti e capacita' host, budget unico e
allocazione con utente, implementazione e test isolati, review del solo installer
AI. Installazione SOLO con OK esplicito al momento. Nessun esecutore di takeover.
