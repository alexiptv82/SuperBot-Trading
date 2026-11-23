# Schermata Brain con Falco Evoluto e Brain Scalp (PAPER)

Stato: prima versione (`845537f3`) **installata** dal proprietario; **seconda versione con i selettori (`34c3529b`) preparata, NON installata** (serve l'OK del proprietario). Ramo `claude/schermata-bot-paper-20261123`.

## Seconda versione (34c3529b): schede superiori come selettori
- Le due schede del riepilogo (sempre visibili: nome, stato RUNNING/PAUSA/FERMO, equity, %) sono **pulsanti**: toccando Falco Evoluto o Brain Scalp, sotto compaiono i dettagli del **solo** bot scelto (tutte le informazioni di prima: capitale, equity, P&L, Guardian, decisioni, posizioni, chiusura manuale singola).
- Scelta evidenziata (bordo viola, «▼ dettagli sotto»); all'apertura è scelto Falco Evoluto; la scelta resta durante l'aggiornamento ogni 30 s; se un bot sparisse dai dati si torna al primo.
- Stesso schema del selettore di portafoglio della vecchia app: `<button>` nativo con `aria-pressed`, quindi tocco Android/PWA, Tab + Invio/Spazio e lettori di schermo.
- Lo stato dell'altro bot non si nasconde mai: un FERMO resta nella sua scheda anche quando l'altro è selezionato.
- Verifica su Chromium headless (Playwright, solo nella cartella temporanea dell'agente; dati simulati): 360×780 e 412×915 con tocco, nessuno scorrimento orizzontale, schede 160×115 / 186×115 px, un solo pannello di dettaglio, nessun errore JavaScript; tastiera: Tab raggiunge le schede con anello di focus visibile, Invio e Spazio selezionano.
- Jest 196 test (erano 191); mutazione: con il selettore disattivato 5 test falliscono.

Candidata: `/home/superbot-agent/brain-unico-lab/rilascio/ui-34c3529b` (bundle `main.3dd759b4.js`, index `ea3b5a87…`, manifesto `5a8b5a8b…`); stessi file della build servita, cambia solo il bundle; manifest e service worker identici. Prova generale in copia della radice web attuale: `SUCCESS_UI_BRAIN_UNICO`, poi rollback → `RESTORED_PREVIOUS_UI` con la build identica a quella servita ora (`main.df0611d8.js`).

```
sudo bash /root/falco-scalp-rilascio/70-interfaccia.sh --activate --candidate /home/superbot-agent/brain-unico-lab/rilascio/ui-34c3529b --manifest-sha 5a8b5a8bb1dae9edf0d2bd7a11ab9eba8d1310c69b39633447bad6a410b793e1
```
Rollback (torna alla prima versione, quella in uso ora): `sudo bash /root/falco-scalp-rilascio/70-interfaccia.sh --rollback`.

## Brain Scalp FERMO (diagnosi separata, nessuna modifica)
Il runner di Brain Scalp registra `halted:daily_loss` dalle 17:43 UTC del 23/11 (`superbot-ops log scalp-runner`): è il **freno di perdita giornaliera** (P0 #124, stop al 50 % del capitale di inizio giornata UTC, realizzato + non realizzato). Agganciato fino a mezzanotte UTC; uscite, stop e chiusura manuale proseguono (uscite SANE). La dashboard mostra FERMO correttamente: non è un errore grafico.
Con posizioni dimensionate a ~4 % di perdita allo stop e nessuna chiusura, una perdita reale del 50 % è poco plausibile: va distinto tra blocco `loss` (perdita calcolata ≥ 50 %) e blocco `unverified` (ricostruzione della giornata non riuscita, es. candele mancanti). L'agente non può leggere i file della run (root 0700). Comando root in sola lettura, solo frazioni, nessun importo:
```
sudo sh -c 'cd /opt/superbot-v3-paper-runs/brain-v3-brain-scalp-p1 && python3 -c "import json; h=json.load(open(\"heartbeat.json\")); print({k: h.get(k) for k in (\"state\",\"last_error\",\"daily_loss_level\",\"daily_loss_pct\",\"ts_ms\")}); d=json.load(open(\"daily_loss.json\")); print({k: d.get(k) for k in (\"halt_latched\",\"latch_reason\",\"day_start_ms\",\"checked_through_ms\",\"audit_from_ms\")})"'
```


## Il problema
`/brain-unico` rendeva ancora Brain RC1; il confronto Falco Evoluto / Brain Scalp era solo un link dentro il fold «Storico».

## Cosa cambia (solo interfaccia, file statici)
| Indirizzo | Prima | Dopo |
|---|---|---|
| `/` e `/brain-unico` (tab **Brain**) | Brain RC1 | **Falco Evoluto e Brain Scalp**, uno sotto l'altro |
| `/brain-unico/rc1` | non esisteva | **Brain RC1 integro** (stessa schermata di prima, stessi dati e chiusura manuale) |
| `/compare` | confronto affiancato | invariato |
| `/overview` (tab **Storico**), `/classic`, `/brain/archive`, `/arena` | invariati | invariati; il tab Storico resta acceso anche su RC1 e Confronto |

Per ciascun bot: badge **RUNNING / PAUSA / FERMO** (con «ultimo giro N min fa»), capitale, equity a mercato (Guardian) e contabile, P&L chiuso / aperto / sessione / dopo costi AI, posizioni aperte, KPI (aperte, chiuse, budget AI), Smart Profit Guardian (stato, motivi, picco, giveback, floor, rischio residuo, tetto di apertura), ultime decisioni, **chiusura manuale singola con conferma** (verso la run del bot a cui appartiene la posizione; mai «chiudi tutte»).

Dallo **Storico** della schermata Brain restano raggiungibili: Brain RC1, Falco classico · Toro · Brain V3, Confronto affiancato, Dashboard classica, Brain precedenti, Arena.

## Cosa NON cambia
Backend, runner, strategie, mandati, pause, servizi di trading, journal, web container, bridge, nginx, manifest e service worker della PWA. Nessuna nuova API: la schermata usa solo `GET /api/v3/compare` (già in produzione, backend `246a3a92` invariato per queste rotte).

## Onestà dei dati
- **RUNNING** richiede che il runner dichiari `running` **e** che un giro del Brain sia stato registrato di recente (limite: 2 cicli + 5 minuti). Altrimenti il badge resta RUNNING ma ambra, con «Nessun giro recente: ultimo giro …». `PAUSA` prevale sempre; `halted` → FERMO.
- Equity «a mercato» = valutazione del Guardian all'ultimo giro (commissioni di chiusura incluse), con l'età mostrata; in sua assenza si mostra quella contabile (solo trade chiusi). Nessun valore dedotto.
- Prezzo e P&L per singola posizione **non** sono nella risposta del confronto: la schermata lo dichiara e mostra il P&L aperto complessivo (Guardian).
- Nessun comando di avvio, pausa o approvazione del mandato: restano un intervento del proprietario sul server.

## Verifiche eseguite
- Jest completo: 23 file, 191 test (erano 170): modello (stati, equity, Guardian), pagina (due bot, Storico sempre raggiungibile anche con errore, chiusura singola per run, nessun «Chiudi tutte»), **routing dell'App reale** (provato con mutazione: ripristinando il vecchio instradamento il test fallisce).
- Build pulita dal commit (`git archive`, `REACT_APP_BACKEND_URL=`, senza source map): `main.df0611d8.js`; solo `index.html`, `asset-manifest.json` e il bundle differiscono dalla build servita (`ui-393b38f6`); manifest e service worker identici a quelli online.
- Prova generale **in copia isolata** dello script reale `70-interfaccia.sh`: attivazione con backup verificato, PWA preservata, `RESULT=SUCCESS_UI_BRAIN_UNICO`; rollback → `RESTORED_PREVIOUS_UI` con `index.html` identico all'originale.
- Limite dichiarato: nessun browser sulla VPS, la resa a 360 px non è stata vista su schermo (verificata per struttura: larghezza massima 600, `flex-wrap`, `overflow-wrap`).

## Installazione (root, un solo comando, solo file statici)
Candidata: `/home/superbot-agent/brain-unico-lab/rilascio/ui-845537f3` (12 file, manifesto `e6e6358b…`).

```
sudo bash /root/falco-scalp-rilascio/70-interfaccia.sh --activate --candidate /home/superbot-agent/brain-unico-lab/rilascio/ui-845537f3 --manifest-sha e6e6358b9e790e6fd41e1039d9b9ecf1f8a5062d3b73a02a04eb6834e773669b
```
Lo script: verifica manifesto e impronte di ogni file, rifiuta file non elencati, controlla che le unità RC1 e il backend siano sani, fa una **copia di sicurezza verificata** della build in uso, conserva manifest/service worker/icone, scambia la cartella e ricontrolla il sito; se un controllo fallisce **ripristina da solo** la versione precedente. Non riavvia nginx, container né servizi di trading.

Esito atteso: `BRAIN_UI_RESULT=SUCCESS_UI_BRAIN_UNICO`.

## Rollback (root, secondi)
```
sudo bash /root/falco-scalp-rilascio/70-interfaccia.sh --rollback
```
Esito atteso: `BRAIN_UI_RESULT=RESTORED_PREVIOUS_UI`. La build rifiutata è conservata, mai cancellata. Copia di sicurezza anche in `/opt/superbot-v3-backups/brain-unico-webui-before-<data>`.

## Sul telefono
La PWA carica `index.html` **prima dalla rete** (service worker network-first): dopo l'installazione la schermata nuova compare al prossimo avvio, senza reinstallare l'app. Se si vedesse ancora il vecchio Brain: chiudere e riaprire l'app. La sessione è per scheda: può richiedere un nuovo login.
