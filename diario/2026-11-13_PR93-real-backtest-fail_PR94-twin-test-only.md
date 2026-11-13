# Checkpoint verificabile — PR #93 FAIL su dati reali; PR #94 solo test PAPER

**Data:** 13/11/2026, 08:59 Europe/Rome  
**Ambito:** sola documentazione. Nessun merge, deploy, GitHub Actions, VPS, reboot, reset, unpause, ordine o API a pagamento. Trading esclusivamente PAPER. Storici ed EventJournal da preservare.

## Sintesi decisionale

La ricerca Toro LONG Mirror 15m della [PR #93](https://github.com/alexiptv82/SuperBot-Trading/pull/93) ha ora un esito verificato **FAIL — non integrare**. La nuova [PR #94](https://github.com/alexiptv82/SuperBot-Trading/pull/94) prepara una diversa ipotesi Falco/Toro “gemelli” per valutazione, ma la successiva precisazione dell’utente è vincolante: **si tratta solo di un test per capire la situazione; non è stata presa una decisione finale**.

## Obiettivo e stato dei tre portafogli PAPER

- **Falco:** direzione desiderata SHORT_ONLY; PR #92 tecnicamente preparata ma Draft/non attivata.
- **Toro:** configurazione finale ancora **non decisa**. La strategia 15m della PR #93 è respinta. La configurazione “gemelli” 10×100 della PR #94 è solo candidata a test, OFF di default e non collaudata.
- **Brain:** indipendente e invariato; ultimo stato documentato PAUSED, mandato `approved=false`.
- Capitale storico di riferimento: Falco 1.000, Toro 1.000, Brain 2.000 USDT, esclusivamente PAPER. Nessuna nuova run autorizzata.

## Fatto — PR #93, verdetto finale negativo

PR #93 aperta, Draft, non mergiata:

- branch `work/toro-long-mirror-15m-20261113`;
- base `f8332c92cc2bc4edee3ea7363f71f15a0a37a816`;
- HEAD `c8e8992458264ff81d82f0e9805b9115e11c839c`;
- 6 commit, 11 file, +4.958/−0;
- prototipo isolato, non collegato al runner; file SHORT congelati dichiarati byte-identici alla base;
- test tool+studio **21/21 PASS dichiarati da Claude**, nessuna GitHub Actions.

Dati dichiarati come scaricati read-only da Bitget USDT-FUTURES: BTCUSDT, ETHUSDT, SOLUSDT, 12/04/2025–13/11/2026; per asset 55.692 candele 15m e 3.480 candele 4H, manifest SHA256 e audit di continuità senza gap. I CSV grezzi non sono nella PR: l’audit indipendente completo richiede ricaricamento e verifica hash o snapshot read-only accessibile.

Risultati:

- periodo A: 990 trade, media netta circa **−0,171% del nozionale/trade**;
- periodo B: 921 trade, circa **−0,177%**;
- tutti i tre asset negativi in entrambi i periodi; continuation e bounce negativi; profit factor <1;
- costi fee+slippage+funding circa 0,17% per trade;
- tutte le 24 combinazioni A/B perdono;
- kill threshold raggiunta in 12/12 varianti A e 11/12 B;
- equity finale minima: 422,29 in A e 384,75 in B.

Gli ingressi casuali peggiori non rendono profittevole il modello. La finestra B non deve essere riutilizzata come test finale dopo averne osservato l’esito.

**Decisione:** fermare integrazione e tuning del LONG Mirror 15m; conservarne le evidenze come baseline negativa. Un eventuale nuovo studio LONG deve partire da ipotesi pre-registrata e dati fuori campione nuovi.

### Limiti metodologici da non perdere

- Funding effettivo disponibile solo per gli ultimi 90 giorni; il resto usa ipotesi 1 bp/8h e stress 3 bp.
- `kill_equity=450` blocca nuove aperture: **non garantisce** che esposizioni già aperte non portino l’equity sotto 450.
- Nel replay `portfolio()` usa `acc.roll_day(day,{})` con marks vuoti: verificare l’effetto sul daily stop. Non cambia il segno negativo dei PnL individuali, ma può modificare i totali portafoglio.
- Non introdurre chiusure forzate automatiche senza decisione esplicita dell’utente.

## Preparato — PR #94, solo candidato di test

PR #94 aperta, Draft, non mergiata:

- branch `work/classics-twin-short-long-20261113`;
- base `f8332c92cc2bc4edee3ea7363f71f15a0a37a816`;
- HEAD `4025db383fb92ee5e1656c55144df4833a77800d`;
- 6 commit, 4 file, +328/−5;
- creata 13/11/2026 08:40:59 Europe/Rome;
- nessuna GitHub Actions.

Ipotesi preparata, **OFF di default e PAPER-only**:

- Falco SHORT_ONLY e Toro LONG_ONLY usano gli stessi segnali/regole classici 1h/4h;
- 10 slot Toro, massimo 100 USDT per posizione, margine aggregato massimo 1.000 USDT, kill 450, daily stop 12%;
- uno SHORT rifiutato non viene trasformato in LONG; `NO_TRADE` resta valido;
- legacy Toro OFF resta 3×350;
- exit di eventuali SHORT Toro preesistenti consentita, nuove DCA/pending split SHORT bloccate;
- input invalido => `BLOCK_NEW`; LIVE => Twin OFF; S25 non abilita nuove entrate Twin;
- formule `signals.py`, `brain.py`, `engine.py` dichiarate invariate; `cli.py` estesa per la configurazione.

**Test scritti ma non eseguiti.** Servono test locali/regressioni/replay e audit indipendente. Copiare i parametri non dimostra redditività LONG. La proposta non è approvata né rilasciata.

## Eseguito / preparato / rilasciato

- **Eseguito:** studio PR #93 con verdetto FAIL e test dichiarati; documentazione di questo checkpoint.
- **Preparato:** PR #94 come prova alternativa, OFF/PAPER, non collaudata.
- **Rilasciato:** nulla. Nessun merge, deploy, unpause o modifica VPS.
- **Non approvato:** configurazione finale Toro, attivazione Twin, nuova run PAPER, modifica della semantica kill/floor.

## Servizi, backup e chiavi — ultimo stato documentato, non live

Nessun controllo live VPS in questo checkpoint. Ultimo stato documentato: RC84 installata da sorgente `ab7e0b7…`; Falco/Toro in draining e Brain PAUSED; exit healthy; pause da preservare. Non assumere che sia ancora lo stato corrente senza verifica reale.

- Backup esterno branch `work/extbackup-bot-stopped-20261109`: preparato, **non installato**.
- Copia cifrata della chiave age sul PC: output PowerShell **`ESITO: VERIFICA OK`** e confronto della chiave pubblica coincidente.
- Questa verifica certifica soltanto la copia locale controllata; **non certifica backup o restore sulla VPS**.
- PR #80 RC84 resta riferimento storico del ciclo precedente; nessuna azione di rilascio eseguita qui.
- Nessun segreto, chiave privata, passphrase o token è stato letto o pubblicato.

## Problemi e blocker

1. Toro non ha ancora una configurazione finale approvata.
2. PR #94 non è stata eseguita né revisionata indipendentemente.
3. Semantica kill 450 non equivale a floor assoluto; serve una decisione di rischio esplicita.
4. Riproducibilità PR #93 incompleta senza CSV/snapshot verificabile.
5. Stato live VPS, backup off-host e restore non verificati in questa esecuzione.
6. Accesso alle conversazioni limitato ai messaggi recenti effettivamente recuperabili; nessuna pretesa di trascrizione integrale delle chat.

## Prossimo passo autorizzabile

1. Non integrare né ottimizzare la strategia PR #93.
2. Eseguire offline i test/regressioni/replay della PR #94, poi audit indipendente, senza Actions o deploy.
3. Confrontare PR #94 con baseline e criteri di accettazione definiti prima del test.
4. Chiarire la protezione del rischio e il significato del floor senza introdurre chiusure forzate non richieste.
5. Solo dopo risultati e decisione utente separata valutare eventuale merge/deploy; fino ad allora tutto resta Draft, OFF e PAPER.
