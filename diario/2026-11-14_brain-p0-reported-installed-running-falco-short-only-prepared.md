# Checkpoint verificabile — 14/11/2026 01:55 Europe/Rome

## Esito

Sono emerse novità dopo il checkpoint delle 00:51. Questo documento distingue rigorosamente tra riscontri GitHub, decisioni utente recuperate dalle conversazioni recenti e risultati VPS riportati solo in riepiloghi conversazionali. Non è una trascrizione integrale delle chat e non attesta stato VPS continuativo.

## Stato consolidato essenziale

- Modalità obbligatoria: **solo PAPER**. Storici ed EventJournal devono restare preservati.
- Portafogli:
  - **Brain**: una conversazione recente riporta installazione P0 e successiva riattivazione PAPER riuscite; il dato è puntuale e non è stato ricontrollato via SSH in questo checkpoint.
  - **Falco**: resta in pausa per decisione utente; la strategia SHORT esistente non va modificata. È preparata, ma non installata, una guardia Falco SHORT-only che blocca aperture LONG.
  - **Toro**: resta in pausa; PR #99 rimane NO-GO strategico e non va promossa.
- Nessun merge, deploy, GitHub Actions, reset, reboot, ordine, wallet o API a pagamento è stato eseguito da questo checkpoint.

## Brain — fatto, preparato, rilasciato

### Riscontri GitHub

Il ramo `work/brain-exit-observability-20261113` è avanzato rispetto a `1bbdd6e217d230ecbefd96b2207d7dc26a2a1004` di due commit:

1. [`e951339f83bbf3efbb25fc8c8272b8fa04cb6225`](https://github.com/alexiptv82/SuperBot-Trading/commit/e951339f83bbf3efbb25fc8c8272b8fa04cb6225) — script guarded per togliere la pausa Brain PAPER dopo verifica dei file P0.
2. [`33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`](https://github.com/alexiptv82/SuperBot-Trading/commit/33a0de73a9903ba1ff76326aa4cb7c688a1e4aca) — corregge il controllo post-avvio per cicli AI sincroni lunghi, evitando una re-pausa prematura.

HEAD verificato del ramo: `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`. Non risulta una PR nuova per questo ramo.

### Risultati VPS riportati nelle conversazioni accessibili

Un riepilogo conversazionale recente riporta:

- `BRAIN_P0_INSTALL RESULT=PASS`;
- installazione dei due file P0 Brain già testati 192/192;
- backup conservato, pausa preservata durante l'installazione, runner/exit riavviati e controllati, zero posizioni al controllo;
- primo tentativo di riattivazione non valido perché l'output atteso fu incollato come comando, quindi non costituiva prova;
- primo script effettivo terminato con `BRAIN_RESUME RESULT=REPAUSED reason=post_start_check_failed`;
- secondo script corretto terminato con `BRAIN_RESUME RESULT=PASS`, Brain PAPER `RUNNING`, exit `HEALTHY`, pausa assente.

**Limite probatorio:** in questa esecuzione non sono disponibili la trascrizione utente integrale né un controllo SSH. Gli esiti sopra sono quindi conservati come output riportati da riepiloghi di chat accessibili, non come attestazione live indipendente. Non dedurre che Brain sia ancora RUNNING al momento della lettura, né redditività, corretta gestione di trade reali simulati o continuità dei servizi.

## Falco — patch SHORT-only preparata, non installata

Ramo verificato: `work/falco-short-only-20261114`, HEAD [`154f5535396551265592fe6605c00e2cffc18f49`](https://github.com/alexiptv82/SuperBot-Trading/commit/154f5535396551265592fe6605c00e2cffc18f49).

Sequenza verificata:

1. [`728a8d962a177b797bd0a8b81674b76fa30d713d`](https://github.com/alexiptv82/SuperBot-Trading/commit/728a8d962a177b797bd0a8b81674b76fa30d713d) — guardia finale account-level PAPER: rifiuta LONG quando il portafoglio è Falco.
2. [`b5e1c153310a634f6d21a38a4b303db8d802b311`](https://github.com/alexiptv82/SuperBot-Trading/commit/b5e1c153310a634f6d21a38a4b303db8d802b311) — sopprime decisioni/open LONG e percorso S25 LONG per Falco, preservando SHORT e uscite.
3. [`154f5535396551265592fe6605c00e2cffc18f49`](https://github.com/alexiptv82/SuperBot-Trading/commit/154f5535396551265592fe6605c00e2cffc18f49) — aggiunge quattro regressioni offline.

I quattro test sono presenti e verificabili staticamente nel commit, ma non è disponibile un output di esecuzione: **non dichiarare 4/4 PASS**. Nessuna PR, installazione, deploy, riavvio o riattivazione Falco risulta autorizzata o provata. Falco resta in pausa.

## Decisioni utente e roadmap

Decisione utente recuperata da una conversazione recente:

- Brain **non** deve diventare supervisore o autorizzatore di Falco/Toro.
- Brain può osservare decisioni, risultati e motivazioni dei due bot per capire differenze di comportamento e usare tali dati come contesto.
- I segnali Telegram sono informazioni aggiuntive da elaborare, non istruzioni né copy-trading letterale; un segnale LONG può essere valutato da Toro e uno SHORT da Falco.
- Nessuna modifica allo SHORT di Falco è approvata.
- Falco e Toro restano in pausa durante la notte.

Stato implementativo: questa è una decisione di architettura/roadmap. Non risultano schema, feed, contratto read-only, branch o test che colleghino Brain ai dati dei classici o ai segnali Telegram. Prima di codice operativo servono contratto minimo, provenienza, deduplica, limiti temporali, test offline e garanzia che nessun input esterno autorizzi ordini.

## Configurazioni e rischio: desiderato vs implementato

- **Desiderato:** Brain indipendente, arricchito da osservazioni read-only; Falco SHORT-only senza alterare la logica SHORT; Toro LONG autonomo; Telegram advisory-only.
- **Implementato/provato:** patch Brain P0 riportata come installata e Brain riportato come riattivato in un punto temporale; patch Falco SHORT-only solo su ramo, non installata; nessun collegamento Brain↔classici/Telegram.
- **Non approvato:** merge/deploy Falco, riattivazione Falco/Toro, promozione PR #99, copy-trading Telegram, supervisione/autorizzazione di Brain sugli altri bot, modifica rischio/capitale, LIVE.

## Test, problemi e blocker

- Brain P0: resta valido il precedente test isolato **192/192 PASS in 4,92 s** sul commit `4efd1a31051dd023480d4d9a327016ae9a6f9a0e`.
- Il primo resume ha evidenziato che un ciclo AI sincrono può superare il controllo breve; il commit `33a0de73…` modifica il post-check per non interpretare automaticamente un heartbeat ancora vecchio come fallimento.
- Il PASS di resume è una fotografia riportata, non certificazione continua né prova di edge/PnL.
- Falco SHORT-only: test presenti ma non eseguiti con output verificato.
- Toro: PR #99 NO-GO resta blocker strategico.
- Backup esterno su `work/extbackup-bot-stopped-20261109` resta preparato e **non installato**.
- Verifica locale PC della copia cifrata age: output PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; **non certifica** presenza, restore o backup sulla VPS.
- RC84 PR #80 resta storico Draft/non mergiato; non confondere la sua telemetria con lo stato live corrente.

## Prossimo passo sicuro

1. Non modificare Brain in questa fase: osservare soltanto heartbeat/journal e, se disponibili, un ciclo completo senza forzare trade.
2. Lasciare Falco/Toro in pausa.
3. Eseguire offline, su SHA esatto, i quattro test Falco SHORT-only e regressioni pertinenti prima di qualunque proposta di installazione; nessun deploy senza consenso separato.
4. Formalizzare un contratto read-only per dati Falco/Toro e segnali Telegram, senza autorità esecutiva e senza segreti.
5. Conservare backup P0, storici ed EventJournal; extbackup/restore richiedono mandato separato.

## Istruzioni di ripresa

- Leggere per primi questo checkpoint, `STATO.md` sul ramo `diario` e la versione corrente di `ULTIMO-STATO-SUPERBOT.md`.
- Ricontrollare i branch e gli SHA indicati prima di dedurre avanzamenti.
- Se non si dispone di output utente originale o accesso VPS, qualificare sempre gli stati runtime come “riportati” e puntuali.
- Nessuna azione operativa implicita: solo PAPER, nessun merge/deploy/Action/VPS/restart/reset/ordine/API a pagamento.
