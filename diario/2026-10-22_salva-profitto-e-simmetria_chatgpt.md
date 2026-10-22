# Salva-profitto AI e simmetria long/short — audit ChatGPT

22/10/2026. Solo lettura del repository e prove sintetiche locali.
Sorgente: rule-pool 7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e.
brain.py, cli.py, signals.py ed engine.py risultano identici fra questo HEAD
e 4aabeb8, baseline indicata dal diario. La versione realmente in esecuzione
oggi NON e' stata verificata interrogando il VPS.

## 1. Visione dell'utente, corretta e distinta dallo Step 6

Oltre il 50% di profitto sul margine, l'AI deve rivalutare attivamente la
posizione, cercando evidenze concrete di continuazione. Se sufficienti,
proporre chiusura di meta' e gestione del residuo; se insufficienti, proporre
chiusura totale. Il 50% e' un punto di attenzione/rivalutazione, NON un ordine
automatico di chiusura e NON una regola da installare senza decisione.

I due esempi sono trascrizioni fornite dall'utente, non letture indipendenti
del conto o screenshot allegati in questa sessione. Uno supera il 50%, l'altro
e' ancora sotto. Nessun simbolo, prezzo, importo o riga di trade viene copiato
in questo documento pubblico. Non deduciamo dal profitto attuale la decisione
corretta senza dati contemporanei del mercato.

Questa visione non coincide col candidato meccanico dello Step 6 (+1,5R a
barra chiusa). Step 6 resta un esperimento di riferimento draft, non una
realizzazione della gestione discrezionale AI richiesta. Non cambiarne ora
retroattivamente l'obiettivo per farlo apparire conforme alla nuova visione.
Per un futuro confronto AI servono versioni di prompt, input e decisioni
registrate al momento, senza far vedere al modello le candele future.

Prima di implementare occorre definire quale ROI si intende: lordo mostrato
in app o netto liquidabile dopo costi, margine iniziale costante o margine
residuo dopo parziali/DCA. Il denominatore non deve cambiare silenziosamente.
Il 50% sul margine non equivale a +1,5R o +2R: dipende da leva e stop iniziale.

## 2. Domanda 1 — Gestione attiva gia' presente?

SI', prevista da entrambi i prompt e implementata per close/partial_close.
Hawk chiede di valutare ogni posizione e propone un parziale del 35% a 2R;
Bull chiede parziali 35-40% al TP1 e insiste sul lasciare correre.
Non esiste pero' il requisito attuale di review AI al superamento del 50%
sul margine, con evidenza di continuazione o chiusura.

Fonte: [prompt e schema azioni](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/brain.py#L66),
[gestione Bull](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/brain.py#L145),
[ciclo e selezione delle decisioni](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/cli.py#L983).

La gestione effettiva non e' un ragionamento AI continuo:
- ciclo normalmente 30 minuti, 15 con scalp aperto;
- chiamata Claude normalmente ogni ora o per scalp da rivedere dopo 15 minuti;
- calendario, budget, chiave, errori e halt possono impedire la chiamata;
- fuori chiamata o con lista decisioni vuota intervengono le regole;
- le regole chiudono su deterioramento dei punteggi (lato proprio <35 o opposto
  >=60), ma non hanno parziale/valutazione dedicata al profitto sul margine;
- se Claude restituisce anche una sola decisione, il fallback a regole non
  completa automaticamente le posizioni omesse: non e' garantita la copertura
  di ogni posizione aperta.

Non assumere oggi calendario spento dal JSON nel repo, le cui finestre finiscono
il 18/10: il file runtime e' diverso/separato. Il report del 21/10 mostrava mode
none/allowed true. Budget o calendario odierni non verificati.

### Difetti di integrazione riprodotti

**A. score_ora non e' necessariamente il punteggio del lato della posizione.**
position_info usa r.score, cioe' il massimo fra long_score e short_score.
Prova sintetica sulla funzione estratta dall'AST reale: posizione LONG,
long_score=10, short_score=85 -> scheda posizione con score_ora=85.
Il riepilogo delle coppie riporta anche L10/S85 e SHORT, quindi l'informazione
corretta esiste altrove; la scheda sintetica e' comunque fuorviante.
Il difetto riguarda entrambi i lati, non dimostra da solo un bias anti-long.
Fonte: [position_info](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/cli.py#L698).

**B. Contesto del profitto incompleto.** La scheda fornisce PnL lordo, margine,
SL, eta' e motivo, ma non TP corrente, R, ROI netto liquidabile, MFE/giveback
e prova strutturata della continuazione. Usa pos.margin invece di total_margin:
con DCA/parziali il margine esposto puo' divergere da quello stampato.
Non basta che l'AI possa ricavare approssimativamente un rapporto dal PnL.
Fonte: [build_prompt](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/brain.py#L328).

**C. Promessa Bull di estendere TP tramite hold non realizzata.**
Il prompt suggerisce hold o aggiornamento TP quando il trend continua oltre
il target. Il ramo hold aggiorna solo last_review_ms: ignora take_profit_pct,
non estende TP e non sposta SL. Prova sul corpo AST reale: hold con nuovo TP
proposto lascia invariato il TP. Non esiste MOVE_STOP nell'interfaccia Hawk/Bull.
Parziali e DCA hanno invece rami che possono aggiornare TP.
Fonte: [ramo hold](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/cli.py#L1322).

**D. TP/SL valutati prima della decisione AI.** Coerente temporalmente: una
posizione che ha gia' raggiunto TP sulla barra chiusa viene chiusa tutta prima
della chiamata. Non puo' essere salvata da un hold successivo. Per lasciare
correre oltre il target serve un'azione precedente implementata correttamente,
non aspettare che il TP sia gia' scattato.
Fonte: [process_closed_bars prima di Claude](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/cli.py#L915).

### Apprendimento: cosa manca rispetto alla visione

Le statistiche permanenti sono aggregate per simbolo, non separano il lato.
Il coaching vede principalmente gli ultimi trade chiusi, non una sequenza
completa di evidenze/decisioni hold e controfattuali sul profitto restituito.
log_claude_call conserva conteggi delle decisioni riuscite; salva il testo
della risposta solo quando il parsing fallisce. Un hold aggiorna un timestamp,
senza un evento strutturato con tesi, alternative e condizioni di invalidazione.
Quindi esiste memoria, ma non un ciclo verificabile completo di apprendimento
della gestione del trade aperto richiesto dall'utente.

Fonti: [registro chiamate](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/cli.py#L649),
[coaching](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/brain.py#L427),
[statistiche per simbolo](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/brain.py#L496).

## 3. Domanda 2 — DeepSeek H24 e salva-profitto ombra

Tre componenti differenti, da non confondere:

| Componente | Legge le posizioni Hawk/Bull? | Puo' cambiarle nel codice esaminato? |
| --- | --- | --- |
| Claude nel ciclo desk | Si', tramite position_info/build_prompt | Si', con i rami di esecuzione validati |
| DeepSeek H24, superbot-ai | No: candele pubbliche e proprio conto virtuale | No |
| Profit sidecar, superbot-sidecar | Si', volumi dei bot montati read-only | No: registra suggerimenti, applied=false |

DeepSeek H24 non contribuisce direttamente alle aperture di Hawk/Bull per
architettura: workflow ai-shadow-install non monta i loro dati, il runner
usa un Pilot con PaperAccount proprio e cartella /opt/superbot-ai-data.
Nei sorgenti desk non c'e' un canale che ne importi le decisioni.
DeepSeek puo' aprire e gestire trade virtuali propri, anche sullo stesso
asset: coincidenza di simbolo non e' contributo alla decisione del bot.

Il suo prompt prevede CLOSE, PARTIAL_CLOSE, MOVE_STOP e HOLD sul proprio conto.
Non contiene la nuova review obbligatoria oltre il 50% sul margine; le righe
delle posizioni mostrano % di prezzo, R e MFE, non ROI netto sul margine.

Fonti: [isolamento installazione](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/.github/workflows/ai-shadow-install.yml),
[pilot](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/director/ai_shadow/pilot.py#L75),
[prompt DeepSeek](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/director/ai_shadow/prompt.py#L7).

Il sidecar ha una macchina deterministica di ricerca basata su costi/ATR e
inversione, non una consultazione DeepSeek. Le varianti ROI proposte sono
15% arming, floor iniziale 5%, giveback 5 punti, checkpoint 25%; non sono
la soglia 50% richiesta ora e non sono strategie approvate.
Il checkpoint registra CHIUDI_O_PARZIALE con inversione credibile,
altrimenti LASCIA_CORRERE: non e' il nuovo criterio di evidenza positiva
per giustificare la continuazione. In ogni caso non esegue ordini.
Feature mancanti, ciclo incoerente, prezzo vecchio o ordine DCA/parziale
ambiguo possono congelare la valutazione: essere healthy non prova che ogni
trade sia stato valutato.
Fonti: [varianti ROI](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/profit_sidecar/roi_variants.py#L24),
[runner e applied=false](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/profit_sidecar/runner.py#L105).

### Cosa e' verificato oggi e cosa no

Il file di stato disponibile nel repo e' del **21/10/2026 04:41:05 UTC**.
Mostra sidecar healthy e applied=false, con freeze storici e checkpoint.
NON attesta esecuzione, proposte o assenza di proposte sui trade del 22/10.
I trigger AI nel repo riguardano installazione/report del 21/10, non provano
attivita' del 22. Le interrogazioni accessibili alle liste Actions non hanno
fornito un report operativo odierno; una risposta vuota non prova inattivita'.

Non sono stati letti oggi:
- /opt/superbot-ai-data/ai/status.json e cycles-2026-10-22.jsonl;
- journal sidecar /opt/superbot-sidecar-data/{hawk,bull}/events-*.jsonl;
- learning_log/heartbeat/stato attuali per attribuire aperture, chiamate,
  gestione ed esclusioni al giorno corretto e alla stessa posizione.

Fonte datata: [sg-ombra-check-output](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/deploy/sg-ombra-check-output.txt).
Conclusione: nessun intervento DeepSeek/sidecar applicato a Hawk/Bull nel
disegno esaminato. Eventuali proposte ombra sui due casi specifici e trade
propri di DeepSeek oggi restano NON VERIFICATI.

## 4. Domanda 3 — Difetto tecnico long/short o regime?

L'osservazione e' sufficientemente importante per un audit tecnico. Un
comportamento presente fin dall'avvio senza memoria esclude la memoria
appresa come spiegazione necessaria; non esclude punteggi statici, mercato,
costruzione dei dati o dimensionamento. Non attribuiamo causalmente tutte
le perdite long a un prompt senza ricostruire ingressi e uscite.

**Nessuna inversione generale dei lati trovata.** I prompt consentono
open_long e open_short con le stesse soglie di confidenza. Costruzione di
SL/TP e controlli long-low/short-high nel motore hanno segni coerenti.
Due prove sintetiche speculari sul motore reale hanno chiuso a stop loss
con circa -1,14R su entrambi i lati; non sono una prova di equivalenza completa
su tutti i percorsi. Serie sintetiche crescenti selezionano long, decrescenti
short. Non e' vero che il codice riconosca ogni rialzo come short.

**La pipeline NON e' completamente simmetrica:**

1. **Stagionalita' direzionale presente anche senza memoria.** Il 22/10
   get_seasonal assegna long_bonus=0 e short_bonus=5 per BTC, 4 per ETH,
   2 per altcoin nel caso sintetico controllato. La fase e' denominata
   bear market da una tabella statica del ciclo, non da un'osservazione del
   mercato odierno. Influisce sia sul punteggio sia sul testo dato a Claude.
   Step 5 ha mostrato zero inversioni di lato nel campione revisionato,
   ma non ha misurato causalmente la perdita dei long o tutte le aperture.

2. **Uguaglianze trattate come short.** I confronti EMA 4h, EMA 1h,
   prezzo/EMA50 e trend giornaliero usano > per long, else per short.
   Con serie realmente piatta, stagionalita' disabilitata e 200 barre
   giornaliere costanti, la prova reale ha dato long_score=0,
   short_score=53 e trend 1d bear. Le medie sono uguali: non e' evidenza
   di discesa. In questo caso isolato 53 resta sotto la soglia ingresso,
   quindi non dimostra un'apertura effettiva. RSI su prezzi piatti ritorna
   100 per perdita media zero; neutralita' non gestita esplicitamente.

3. **EMA200 4h spesso non e' una EMA200.** fetch_candles richiede 1000
   barre 15m, cioe' circa 62 barre 4h complete. read_symbol calcola la lenta
   con min(200,len(c4)-1): nella prova, periodo 61 contro 50.
   Il campo si chiama ema50_200_4h ma non descrive quel confronto.
   E' una debolezza tecnica di contesto, non specificamente anti-long.
   Il fix delle vere barre giornaliere non risolve la storia insufficiente 4h.

4. **Informazioni e filtri non allineati.** score_ora della posizione non
   e' direzionale (riprodotto sopra). Il prompt Hawk chiede RR>=2, Bull
   alternativamente >=2,5 o >=2; il codice accetta >=1,5 e le regole
   propongono TP=1,8*SL. Il filtro minimo e' uguale sui due lati:
   incoerenza reale, ma non prova di danno esclusivo ai long.

5. **Esempio numerico Bull incoerente.** L'esempio leva 20x e stop 2%
   usa un rischio equivalente a leva 10x; anche il profitto associato
   al target e' dimezzato. Non e' un importo operativo. Contraddice gli
   stessi input dell'esempio, senza distinguere long/short.

6. **Funding PAPER asimmetrico.** Solo long addebitato, short zero.
   Limite noto del modello, non nuovo bug del replay o prova che spieghi
   le perdite osservate. Va quantificato in R nel campione pertinente.

Fonti: [scoring e medie](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/signals.py#L125),
[stagionalita'](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/seasonal.py),
[filtri di apertura](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/cli.py#L1196),
[esempio Bull](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/brain.py#L149),
[contabilita'](https://github.com/alexiptv82/SuperBot-Trading/blob/7a5e79536c2fb8cf9fdb930e7b7a70d5f824372e/backend/desk/engine.py#L350).

Nel diario Step 4: 9 long Hawk e 4 Bull, tutti negativi, su campione piccolo
e multiversione; non sono una nuova misura odierna. Serve distinguere fonte
rules/claude, versione, setup/trend all'ingresso, durata, stop/leva, funding
e uscita. Il fatto che all'inizio gli short funzionassero non prova che oggi
il mercato sia identico o che il dimensionamento sia irrilevante.

## 5. Esito e prossimo controllo concreto

Nessun fix funzionale, prompt, soglia, calendario o collegamento AI modificato.
Nessun deploy, merge o trigger attivato. Le prove sono sintetiche e locali;
non sono risultati di trading. Aggiornati soltanto diario e stato come richiesto.

Prima di proporre un'implementazione: concordare con Claude la specifica
della review AI del profitto, colmare i difetti di contesto/capacita' d'azione
e progettare la registrazione privata delle decisioni e degli esiti.

Per completare la verifica operativa odierna serve un audit VPS dedicato,
strettamente read-only: PAPER/identita' container prima e dopo; lettura dei
registri bot/AI/sidecar; attribuzione di aperture e proposte con stessa identita'
di posizione e orario; distinzione fra proposto ed eseguito; report pubblico
solo conteggi aggregati/hash, senza simboli, prezzi, saldi o importi.

Giorno da usare: 22/10 Europe/Rome, intervallo UTC
[2026-10-21T22:00:00Z,2026-10-22T22:00:00Z), fino all'istante osservato.
I file AI sono separati per giorno UTC: includere anche la coda del 21/10.
Verificare anche posizioni iniziate prima di mezzanotte e rivalutate oggi.

Gli strumenti disponibili non espongono un accesso diretto autenticato ai
file VPS; i workflow pertinenti partono solo cambiando un trigger. Quelli
esistenti non danno la correlazione richiesta e alcuni stampano dati grezzi.
Il vincolo dell'utente «nessuna modifica senza OK» impedisce di aggiungere
o attivare autonomamente un nuovo workflow: audit operativo da autorizzare
separatamente. Questa e' una lacuna di evidenza dichiarata, non un esito negativo.
