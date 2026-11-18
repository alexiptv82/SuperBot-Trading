# Checkpoint verificabile — SuperBot-Trading

**Data:** 18/11/2026, 14:48 Europe/Rome  
**Tipo:** delta append-only rispetto al checkpoint delle 13:53. Solo documentazione e PAPER.

## Novità verificata

Un nuovo commento sulla PR draft [#110](https://github.com/alexiptv82/SuperBot-Trading/pull/110#issuecomment-6979645646), pubblicato alle 14:15 circa Europe/Rome e basato su screenshot Termius delle 14:13, documenta un inventario read-only del container web:

- container `superbot` sull'immagine `superbot:brain-close-ro-candidate-20261115`;
- `Config.User=""`, quindi utente predefinito root; `RestartPolicy=always`;
- label Docker Compose vuote: non è provato che il container sia gestito da Compose; potrebbe derivare da `docker run`, script o unità separata;
- risultavano `active` il bridge Arena, il runner Brain storico e l'exit Brain storico;
- resta confermato il probe precedente `CHANNEL_NOT_OK`: il socket Arena host non è montato nel container, sono presenti solo il vecchio mount close e flag Arena non abilitati.

Questa è una prova puntuale riportata tramite screenshot e commento GitHub, non un controllo SSH indipendente e non una certificazione dello stato live successivo.

## Stato consolidato per la ripresa

- **Falco/Toro/Brain storici:** Falco e Toro ritirati/archiviati ma non cancellati; logica SHORT Falco, trade, storici ed EventJournal obbligatoriamente preservati. Brain storico separato dall'Arena; nessun intervento autorizzato.
- **AI Arena PAPER:** DeepSeek, Qwen e MiniMax; 27 mercati, stessa baseline/risk policy, primo screening 72 ore. T0 assente, mandati non approvati e runner decisionali Arena inattivi secondo le ultime prove disponibili.
- **Budget desiderato:** 2 USD/giorno e 6 USD cumulativi per AI, 18 USD complessivi desiderati. Per DeepSeek il gate è interno con margine, non un tetto assoluto lato fornitore; non ridurre il saldo condiviso con il Brain storico.
- **App/manual close:** codice e journal append-only preparati, ma il percorso Samsung/web→bridge non è operativo. La nuova evidenza conferma che servono mount/flag e una procedura di ricreazione sicura; non prova ancora GET autenticato, chiusura reale o apprendimento dalla chiusura.
- **Memoria:** le tre corsie restano indipendenti durante la prova; memoria finale/condivisa che apprende da tutti i trade e dalle motivazioni umane non ancora dimostrata operativa.
- **Backup:** backup Arena locale sulla stessa VPS verificato nel checkpoint precedente; nessuna nuova prova di copia esterna. Age PC `ESITO: VERIFICA OK` e chiave pubblica coincidente non certificano backup/restore VPS. Ramo `work/extbackup-bot-stopped-20261109` preparato, non installato.
- **GitHub:** PR #110 resta draft a `3dd6aa588339c6136d52e9ff027c91e5e3f80377`; 1.028 test locali riportati PASS e 2 fallimenti di base, non rilanciati in questo checkpoint. RC84 PR #80 invariata a `0e29a73a36f668643da4088178bacb8616a45ac0`.
- **Ricerca post-T0:** Issue #111 resta SHADOW e non deve modificare o ritardare la gara.

## Fatto / preparato / rilasciato

- **Fatto:** inventario read-only puntuale del container e conferma dei tre servizi sopra; nessuna nuova anomalia di trading osservata nello screenshot.
- **Preparato:** correzioni #110 per hard stop 72h, budget, feed, recovery e probe; non installate.
- **Rilasciato:** nulla di nuovo. Nessun merge, deploy, Action, modifica container/VPS, T0, ordine o credito AI da questo checkpoint.
- **Non approvato:** `docker rm/run`, cambio immagine, mount/flag Arena, ricreazione container, sostituzione run, avvio gara o modifica di saldo/chiavi.

## Blocker e prossimo passo

1. Proseguire solo con inventario read-only di mount, reti, porte e gestore reale, senza leggere o stampare env/segreti.
2. Preparare una patch/rollback atomici che preservino immagine, login/impronta PWA, porte, reti e vecchio bridge; nessuna ricreazione prima della revisione.
3. Verificare in staging autenticazione negativa/positiva, GET Arena e canale socket; la chiusura manuale reale richiede consenso separato.
4. Restano inoltre gate trainer/gestione, budget DeepSeek, sostituzione auditabile delle run e preflight finale prima del T0.

## Istruzioni di ripresa e limiti

Leggere prima il checkpoint completo delle 13:53, poi questo delta, `STATO.md` e gli ultimi commenti della PR #110. Non interpretare `active` come prova di corretto funzionamento end-to-end. Accesso conversazioni solo parziale/indicizzato; nessuna trascrizione integrale di chat eliminate e nessun SSH live in questa esecuzione.
