# Checkpoint verificabile SuperBot-Trading — 25/11/2026 20:48 Europe/Rome

## Esito sintetico

Dal checkpoint delle 14:52 è emersa una novità verificabile sui servizi PAPER del Brain: una schermata della dashboard ha mostrato il runner fermo e il Guardian in protezione; una successiva lettura Termius ha riportato il runner in stato `halted` con motivo `exit_service_unhealthy`. Un controllo immediatamente successivo ha però mostrato il servizio uscite attivo e sano, con heartbeat recente, mentre l'heartbeat del Brain era vecchio di circa 9.358 secondi. La causa non è ancora dimostrata: può trattarsi di un arresto precedente rimasto registrato, di un latch non rientrato o di un problema del runner, ma nessuna di queste ipotesi va presentata come conclusione.

La dashboard osservata riportava equity PAPER 2.249,64 USDT (+12,48%), netto sessione 195,86 USDT, zero posizioni e un valore “trade chiusi” 2.393,80 USDT non coerente con l'equity. Anche questa discordanza è un'anomalia da diagnosticare, non una prova di profitto o perdita aggiuntiva.

Questo checkpoint è esclusivamente documentale. Non esegue codice operativo, merge, deploy, GitHub Actions, accessi o modifiche VPS, riavvii, reset, ordini o API a pagamento.

## Obiettivi e decisioni consolidate

- Trading esclusivamente PAPER; nessun LIVE.
- Storici ed EventJournal append-only da preservare; nessun reset o riscrittura.
- Tre patrimoni distinti: Falco, Toro e Brain.
- Falco/Toro classici restano conservati, `semantic_not_certified`, esclusi dal training automatico.
- Brain Unico/V2 resta la linea operativa prioritaria; `NO_TRADE` e slot vuoti sono risultati validi.
- Nessun cambio strategico, rischio, merge, deploy, riavvio o nuova sessione senza consenso specifico.
- Evolution X e Signal Lab restano attività separate: i loro commit, dataset e backtest non provano modifiche al repository originale o ai servizi PAPER.

## Portafogli PAPER: desiderato contro implementato

| Portafoglio | Desiderato/decisione | Implementato o osservato | Limiti della prova |
|---|---|---|---|
| Falco | preservare strategia SHORT e storici | classici conservati; Falco Evoluto installato il 23/11 e poi archiviato/disattivato nella nuova sessione | nessuna nuova verifica live |
| Toro | preservare l'archivio; non è la linea operativa corrente | storico conservato, `semantic_not_certified`; non presente tra i bot attuali della dashboard V2 | nessuna nuova certificazione semantica |
| Brain | sessione PAPER da 2.000 USDT, DeepSeek principale, Claude revisore, memoria collegata | run `brain-scalp-paper-p1`, 27 strumenti, 10 slot; vecchia run archiviata con 539 eventi e tre sessioni collegate in sola lettura | alle 20:33–20:42 del 25/11 il runner risultava fermo/halted; stato successivo non verificato |

## Configurazione e rischio: desiderato contro implementato

- Il profilo B precedente ha ricevuto il tetto esplicito di quattro posizioni e la contabilità del rischio aperto comprensiva dei costi; integrazione documentata da `c11e6d7d…` e piano `302e94d2…`.
- Issue #124 è stata corretta con `0f71d0be…`, integrata con `5f110379…` e chiusa il 22/11. Il latch blocca nuove aperture e non deve impedire le uscite.
- La successiva Brain V2 usa un profilo diverso e più aggressivo, documentato come installato: ciclo 30 minuti; leva dinamica 15–50×; margine massimo 400 USDT per trade; margine totale 55%; rischio per trade 4,3%; rischio aperto 12%; stop giornaliero 25%; 27 strumenti e 10 slot.
- DeepSeek: confidenza minima 0,56. Claude mantiene il veto. Il fallback senza Claude a rischio dimezzato è disattivato. I LONG richiedono trend 1h+4h. Costi e slippage proposti non devono superare il 30% di 1R.
- Nessuna nuova modifica del profilo V2 è approvata dopo l'avvio.

## Nuova evidenza operativa puntuale e limiti

1. Dashboard osservata intorno alle 20:33 Europe/Rome:
   - equity PAPER 2.249,64 USDT (+12,48%);
   - netto sessione 195,86 USDT;
   - runner “FERMO”, Guardian “PROTEZIONE”, zero posizioni;
   - “trade chiusi” 2.393,80 USDT, non coerente con l'equity.
2. Lettura Termius intorno alle 20:40:
   - runner `state=halted`;
   - motivo registrato `halted:exit_service_unhealthy`;
   - ciclo 42;
   - perdita giornaliera indicata 0%.
3. Controllo successivo intorno alle 20:42:
   - servizio uscite attivo/healthy;
   - controllo stop recente, circa 49 secondi;
   - heartbeat uscite recente, circa 4 secondi;
   - heartbeat Brain vecchio, circa 9.358 secondi;
   - runner ancora HALTED con il motivo precedente.

Conclusione ammessa: il runner Brain risultava fermo e richiede diagnosi read-only del servizio runner e del journal. Non è dimostrato che il servizio uscite fosse ancora guasto al momento del secondo controllo, né che il Guardian abbia chiuso posizioni, né che il problema sia stato risolto. Nessun riavvio è stato eseguito o autorizzato da questo checkpoint.

## Dashboard, apprendimento e Live Evolution

- La sola web corretta il 25/11 alle 06:35 aveva prodotto `APP_PAPER_INSTALLATA_E_VERIFICATA` e `WEB_EXIT_CODE=0`, senza riavviare runner, uscite o bridge.
- Correzione conteggi `work/brain-v2-web-counts-20261125` @ `6e305ed027e6aca132b0b3c1f27f42933ef902cd`: arrotondamento corretto per `paper_reduce` nella web; uso corretto nel runner/memoria non ancora certificato.
- Live Evolution è documentato come implementato/installato e la simulazione V2→V3 con posizione aperta è passata; la prova operativa completa resta pendente.
- Signal Lab è separato e non risulta integrato nel repository originale.

## Backup, chiavi e restore senza dati sensibili

- `claude/extbackup-storici-20261121` @ `1588c95af8411b48616d73203d5d10211d38e246`.
- Il 22/11 il proprietario ha eseguito il backup definitivo: componenti indispensabili e storici cifrati, inviati al repository privato dei backup e verificati da clone nuovo. Gli indispensabili risultano tecnicamente certificati; gli storici risultano integri, ma Falco/Toro restano non certificati semanticamente.
- Restore dei nuovi archivi sul PC Windows ancora incompleto. Procedura Android/Termux e copia aggiuntiva degli indispensabili preparate ma non eseguite.
- Ramo storico `work/extbackup-bot-stopped-20261109` @ `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`: artefatto preparato, non installato o certificato; preservato.
- Copia cifrata della chiave age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica derivata coincidente. È prova locale; non certifica presenza, backup o restore sulla VPS.
- Nessuna chiave privata, passphrase, token o segreto è stato letto o pubblicato.

## Branch, PR, issue e SHA verificati

- `diario` prima di questa scrittura: `e0ec9430df009a40f83f496b5a62f654fc9f7157`.
- `main`: `a1e9722a1a9af32ee045ebf61d7e43858c9a1d5e`.
- `integration/brain-unico-20261119`: `f50f7ae40c78e7994f33d0dabf40f91d57d7873f`.
- `claude/tetto-posizioni-20261121`: `887fc9616b5eedc2b4441357618fd5469ab5977d`.
- `claude/extbackup-storici-20261121`: `1588c95af8411b48616d73203d5d10211d38e246`.
- `claude/live-evolution-20261124`: `d1bc0628bb0fea6f1f5012ede6148cb1d93c0ccd`.
- `work/brain-v2-web-counts-20261125`: `6e305ed027e6aca132b0b3c1f27f42933ef902cd`.
- `claude/brain-unico-2000-20261124`: `c5d05f3f3a31e8b0cfe51949fa06fa4ec04c398b`.
- `claude/ingresso-unico-20261124`: `612f6b4b868bb0828a23792f0f46e5946c7ddf6d`.
- RC84 PR #80: open/draft, non unita, head `0e29a73a36f668643da4088178bacb8616a45ac0`, ultimo aggiornamento 09/11/2026; la PR dichiara test scritti ma non eseguiti indipendentemente.
- Issue #124: closed/completed il 22/11/2026.

## Test con fonte

- Tetto/rischio: ramo `887fc961…`; integrazione `c11e6d7d…`, piano `302e94d2…`.
- #124: correzione multiprocesso `0f71d0be…`, quattro test dedicati, tre rossi sulla versione precedente; suite V3 5.414 dichiarata; integrazione `5f110379…`.
- Brain V2 `6a96e599…`: gate dichiarato V3 5.588, Dataset Builder 158, Jest 212; ripartenza 13/13 e simulatore 2/2.
- App PAPER/integration `f50f7ae4…`: V3 5.500 (1 saltato), Builder 158, Jest 210; controlli Android 126/126 dichiarati.
- Correzione conteggi `6e305ed0…`: regressione sul produttore reale e record alterato rifiutato.
- Questo checkpoint non ha rilanciato suite né GitHub Actions. Le schermate operative non sostituiscono test del codice.

## Eseguito, preparato, non approvato

**Eseguito/verificato**

- Tetto quattro posizioni e rischio aperto con costi integrati.
- Issue #124 corretta, integrata e chiusa.
- Backup esterno cifrato inviato e verificato da clone nuovo; restore PC escluso.
- Brain V2 avviato in nuova sessione e web aggiornata in precedenza.
- Nuova osservazione puntuale: runner Brain halted/heartbeat obsoleto, uscite successivamente healthy.

**Preparato o parzialmente dimostrato**

- Live Evolution installato e simulazione passata; prova operativa completa mancante.
- Correzione arrotondamento applicata alla web; runner/memoria da verificare.
- Copia Android/Termux e restore preparati, non eseguiti.
- Signal Lab/Evolution X separati, non integrati nel Brain originale.

**Non approvato/non eseguito**

- Riavvio del runner, reset, nuova sessione, merge, deploy, cambio strategia/rischio, ordini, LIVE, API a pagamento.
- Correzione dei contatori o dei dati storici senza diagnosi.
- Certificazione semantica Falco/Toro e completamento restore.

## Blocker e prossime attività

1. Diagnosi read-only del servizio runner e relativo journal: determinare l'evento che ha impostato `exit_service_unhealthy`, verificare se la condizione è rientrata e perché il runner è rimasto halted.
2. Confermare senza mutazioni heartbeat Brain, stato Guardian, zero posizioni e salute delle uscite.
3. Riconciliare in sola lettura equity 2.249,64, netto sessione 195,86 e valore trade chiusi 2.393,80; non riscrivere dati.
4. Verificare se runner/memoria acquisiscono correttamente i due `paper_reduce`.
5. Non rilanciare `--nuova-sessione` e non riavviare finché causa e posizioni sono verificate.
6. Completare in futuro la prova controllata Live Evolution e il restore degli archivi, con autorizzazioni separate.

## Istruzioni di ripresa per un'altra AI

1. Leggere `STATO.md`, questo checkpoint e la sezione più recente di `ULTIMO-STATO-SUPERBOT.md`.
2. Verificare nuovamente HEAD, PR #80 e Issue #124.
3. Trattare la finestra 20:33–20:42 come osservazione puntuale: runner halted, uscite poi healthy, Brain heartbeat vecchio. Non presentarla come stato corrente.
4. Riprendere dalla diagnosi read-only del runner/journal e dalla riconciliazione dei contatori; nessun riavvio o correzione dati senza prova.
5. Usare `6a96e599…` come riferimento Brain V2 e `6e305ed0…` per la correzione web.
6. Preservare PAPER, storici ed EventJournal; nessun segreto pubblico, reset o chiusura forzata.

## Fonti consultate

- GitHub `alexiptv82/SuperBot-Trading`: `STATO.md`, checkpoint 14:52, branch/SHA indicati, PR #80 e Issue #124.
- ChatGPT Library `/SuperBot-Ripresa/ULTIMO-STATO-SUPERBOT.md`, versione 147 prima della scrittura.
- Conversazione recente effettivamente accessibile “Ripresa diagnosi Brain Evolution”: schermate dashboard e output Termius della finestra 20:33–20:42. Nessuna pretesa di trascrizioni perse o stato live successivo.

Checkpoint esclusivamente documentale; storici ed EventJournal preservati.

