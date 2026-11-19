# Checkpoint SuperBot — Brain storico fermo; lacuna universo Arena top 25

**Data:** 19/11/2026, 05:46 Europe/Rome  
**Ambito:** sola documentazione; trading esclusivamente PAPER; storici ed EventJournal da preservare.

## Novità verificata dopo il checkpoint delle 21:43

### 1. App classica: Brain storico fermo, con posizioni PAPER ancora aperte

Uno screenshot Samsung creato alle 04:55 Europe/Rome mostra:

- Falco: `non risponde`;
- Toro: `non risponde`;
- Brain: `pausa / fermo` e scheda `Brain - Fermo`;
- Brain PAPER: capitale iniziale 2.000 USDT, P&L realizzato **−78,13 USDT (−3,91%)**, saldo contabile **1.921,87 USDT** escluso P&L aperto;
- **2 posizioni aperte**, **96 chiuse**, margine mostrato **696 USDT**, P&L aperto **−55,92 USDT**, P&L del giorno **−66,65 USDT**;
- equity dichiarata non verificabile in assenza di prezzi/dati affidabili;
- la UI consente soltanto la chiusura manuale singola PAPER; nuove aperture e pausa/ripresa risultano bloccate.

La schermata espone almeno `DOGEUSDT SHORT 20x`, strategia S05, con P&L non realizzato negativo. Questo prova lo stato mostrato dall'app alle 04:55, **non** lo stato dei processi VPS: nessun controllo SSH live è disponibile in questo checkpoint.

### 2. Arena AI: osservazione utente e lacuna di configurazione verificata nel codice

Nella stessa conversazione l'utente riferisce che la gara AI Arena continua a funzionare, ma osserva:

- simboli ripetuti;
- criptovalute oltre la posizione 25 per capitalizzazione;
- un portafoglio in positivo e gli altri due in perdita.

Questi valori Arena sono un'osservazione dell'utente; lo screenshot disponibile in questo checkpoint mostra la scheda Brain classica, non la pagina Arena, quindi non certifica simboli, conteggi o PnL correnti di DeepSeek/Qwen/MiniMax.

È però verificata una differenza tra requisito desiderato e semantica implementata nel ramo della gara:

- **desiderato dall'utente:** criptovalute nelle posizioni assolute 1–25 della classifica, più oro/argento se realmente disponibili;
- **implementato nel codice** `backend/v3/arena/universe.py` del ramo `work/arena-72h-18usd-budget-20261118`: `crypto_target=25`; il codice scorre la classifica, esclude asset non idonei e continua finché ottiene **25 crypto idonee**. Di conseguenza può includere asset con rank originario superiore a 25;
- oro e argento (`XAUUSDT`, `XAGUSDT`) entrano solo se contratto e probe superano i controlli;
- ramo gara verificato: `work/arena-72h-18usd-budget-20261118` a `6a88857ac2ff117bd7711958c63604700f113cb0`;
- ramo storico/preparato sull'universo: `work/brain-arena-top23-metals-universe-20261116` a `dde80584f1664f5784a7739ac7275e4402d6f80e`.

Non è stato letto il file snapshot realmente usato dalla run VPS: non dichiarare ancora una violazione della run. La causa più probabile dell'apparente scostamento è la semantica “prime 25 idonee”, ma va verificata sullo snapshot prima di qualsiasi correzione.

## Stato consolidato per la ripresa

- **Classici:** Falco/Toro ritirati o non rispondenti nella schermata; non riattivarli e non alterare i loro storici. Preservare anche lo storico SHORT Falco.
- **Brain storico:** schermata `Fermo`, 2 posizioni PAPER aperte e 96 chiuse. Nessun restart/reset o chiusura automatica autorizzati.
- **Arena PAPER:** DeepSeek/Qwen/MiniMax restano una gara separata. Ultimo dato consolidato precedente: T0 `1795021392344` (18/11/2026 18:03:12.344 Europe/Rome), stop nuove inferenze/aperture previsto 21/11/2026 18:03:12; uscite ed EventJournal da preservare.
- **PR #112:** open/draft, non mergiata, HEAD `86288a356209cef9264a369d24a2e8d7914c5ec2`; nessun nuovo commento dopo 18/11/2026 19:57 Europe/Rome.
- **RC84 PR #80:** open/draft, non mergiata, HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`.
- **Backup/chiavi:** la copia cifrata age sul PC ha dato `ESITO: VERIFICA OK` e chiave pubblica coincidente; ciò non certifica il backup o restore sulla VPS. `work/extbackup-bot-stopped-20261109` resta preparato e non installato.
- **Servizi:** nessuna verifica SSH live in questa esecuzione. Le etichette UI `running`, `fermo` o `non risponde` sono evidenze dell'app, non prova indipendente dei processi.

## Fatto / preparato / rilasciato / non approvato

- **Fatto e verificato:** acquisito screenshot Samsung delle 04:55; verificata la semantica del codice universo e gli SHA dei rami.
- **Preparato ma non installato:** backup esterno su `work/extbackup-bot-stopped-20261109`.
- **Rilasciato in precedenza:** backend/dashboard Arena read-only; nessuna nuova release in questo checkpoint.
- **Non approvato e non eseguito:** modifica dell'universo, merge, deploy, GitHub Actions, VPS, restart, reset, chiusure/ordini, cambio rischio o API a pagamento.

## Problemi / blocker

1. Brain storico appare fermo con 2 posizioni ancora aperte; manca riscontro read-only su runner/exit/heartbeat VPS.
2. Il requisito “rank assoluto 1–25” non coincide con il codice “prime 25 crypto idonee”.
3. Manca lo snapshot universo effettivo della run: senza di esso non è possibile certificare quali rank/simboli siano stati usati.
4. Nessuna prova aggiornata di avanzamento timestamp/trade dei tre portafogli Arena.

## Prossimo passo sicuro

Eseguire soltanto controlli read-only:

1. confrontare timestamp/eventi/trade di DeepSeek, Qwen e MiniMax;
2. leggere lo snapshot universo pinned della run e riportare per ogni simbolo rank originario, esclusioni e presenza di XAU/XAG;
3. verificare heartbeat/runner/exit Arena e Brain storico senza restart;
4. confermare che T0, journal, budget e posizioni non siano stati modificati.

Solo dopo questa evidenza decidere se preparare, su ramo separato, una correzione dell'universo a **rank assoluto 1–25 + metalli idonei**. Nessuna modifica operativa è autorizzata.

## Limiti delle fonti

- Screenshot Samsung puntuale delle 04:55 e messaggio utente accessibile.
- GitHub verificato per rami/PR/codice.
- Nessuna trascrizione integrale di chat eliminate, nessun SSH live indipendente e nessun accesso allo snapshot universo della run VPS.
