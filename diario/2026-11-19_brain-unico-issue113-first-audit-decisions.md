# Checkpoint verificabile — Issue #113 e decisioni del primo audit Brain unico

**Data:** 19/11/2026, 08:50 Europe/Rome  
**Tipo:** delta append-only rispetto al checkpoint delle 07:47.  
**Ambito:** sola documentazione; trading esclusivamente PAPER.

## Nuove fonti verificate

- [Issue #113 — Brain Unico](https://github.com/alexiptv82/SuperBot-Trading/issues/113), aperta il 19/11/2026 alle 07:50 Europe/Rome: formalizza la roadmap senza autorizzare merge, deploy, reset, stop/avvio, cambi strategia o esposizione LIVE.
- [Primo commento decisionale su #113](https://github.com/alexiptv82/SuperBot-Trading/issues/113#issuecomment-7003083560), pubblicato alle 08:49 Europe/Rome: sintesi trasmessa dall'utente del primo audit Claude Code.
- `SuperBot_Brain_Report.pdf`, 7 pagine, presente nella Library privata del progetto e marcato **[Non verificato]**: documento tecnico/propositivo, non prova di runtime, profittabilità o test conclusi.
- Il rapporto Markdown completo indicato nel commento #113 risulta disponibile sulla VPS, ma **non è stato ispezionato da questo checkpoint**. Il percorso non viene duplicato nel repository pubblico.
- Conversazione recente: Claude Remote Control risulta attivato secondo l'utente; non costituisce prova di privilegi, accesso dati, sudo/docker o modifiche operative.

## Decisioni registrate

1. **Inventario read-only:** autorizzata soltanto la preparazione dello script, riportato come testato su fixture. Non autorizzata esecuzione privilegiata, modifica ACL/sudo/docker, lettura/esportazione di segreti o scrittura sui dati. Un passaggio separato sarà necessario per l'accesso verificato ai dati.
2. **Soglie proposte, non garanzie:** almeno 300 esempi etichettati e verificati e almeno 20 giorni per un primo modello esclusivamente shadow/offline; almeno 1000 esempi e 45 giorni per poter soltanto considerare una promozione. Servono inoltre split cronologico con embargo, baseline, calibrazione, EV netto, drawdown, sufficienza classi e approvazione esplicita. Se i dati non bastano, si continua la raccolta.
3. **Costi Claude:** zero chiamate API Claude dal Brain e zero budget aggiuntivo mentre Arena e audit iniziale proseguono. Claude Code usa l'abbonamento Pro dell'utente; ciò non autorizza API. Un eventuale pilot event-driven con cap candidato di 0,50 USD/giorno è solo proposta futura e richiede approvazione.
4. **Falco SHORT:** advisory-only, con feature/spiegazione e possibile `trend_reversal/SHORT_conflict` interno non bloccante. Nessuna apertura Falco e nessuna sovrascrittura della decisione Brain; il Risk Manager indipendente mantiene il veto.
5. **PR documentale:** autorizzabile su ramo nuovo e isolato, senza merge/deploy/modifica servizi e senza CI onerosa. Il rapporto deve essere sanitizzato; verificare i workflow prima del push perché `[skip ci]` non garantisce lo stop di tutti i trigger.
6. **Collaborazione:** Claude e ChatGPT Work coordinati tramite Issue #113 e PR separate. L'integrazione Claude riferisce 403 in scrittura; qualsiasi autenticazione alternativa richiede consenso dell'utente, permessi minimi e nessun token in chat. Nessun nuovo accesso è stato configurato qui.

## Brain unico: desiderato contro provato

- **Desiderato:** un solo Brain PAPER; DeepSeek decisore principale, Claude consulente soltanto su eventi mirati, Falco SHORT advisory. Dashboard unica e semplice; Qwen/MiniMax/Toro archivi storici dopo conclusione e archiviazione coerente della prova attiva.
- **Proposto dal rapporto:** dataset point-in-time con provenance, NO_TRADE e segnali rifiutati, MFE/MAE, funding, costi e label; modello locale addestrabile in shadow; thesis ID persistente; uscite/risk deterministici e indipendenti dall'AI; esperimenti che isolino una variabile.
- **Provato:** esistono EventJournal, trade, memoria/scoreboard e audit precedenti. Non è ancora provato che costituiscano training quantitativo reale o che migliorino le decisioni.
- **Non provato:** superiorità economica finale di DeepSeek, contenuto completo del rapporto Claude sulla VPS, stato live servizi/dataset, restore off-host, nuova architettura, nuova dashboard o training.
- Il PDF propone DeepSeek per continuità e Qwen come sfidante; esplicita che non sono disponibili risultati degli esperimenti e che il runtime resta non verificato senza journal e versione effettiva.

## Stato invariato e riscontri GitHub

- Ramo `diario` prima della scrittura: `b539e6e2f78c03bd1252fb5a52dc9af96fc27245`.
- Nessun nuovo commit sul ramo predefinito dopo il checkpoint precedente.
- PR #112: open/draft, non mergiata, HEAD `86288a356209cef9264a369d24a2e8d7914c5ec2`.
- RC84 PR #80: open/draft, non mergiata, HEAD `0e29a73a36f668643da4088178bacb8616a45ac0`.
- Backup esterno: ramo `work/extbackup-bot-stopped-20261109` a `3dc2116a08058f57fc14b695431f6e3fa1a1ca45`; preparato, non installato.
- Chiave age sul PC: `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o chiave sulla VPS.
- Runner Brain ed exit service: nessun nuovo controllo live; resta valido soltanto l'ultimo riscontro documentato.
- Arena 72h non modificata; storici, run e posizioni restano da preservare.

## Test e qualificazione delle prove

- Lo script inventario è descritto nel commento #113 come testato su fixture: prova riferita tramite sintesi utente, non riesecuzione indipendente di questo checkpoint.
- Nessuna suite applicativa/runtime è stata eseguita qui.
- Il PDF è una proposta tecnica marcata [Non verificato], non un rapporto di test superato.
- Nessuna GitHub Action avviata.

## Blocker e prossimo passo

Blocker: accesso read-only ai dati effettivi non ancora concordato; rapporto VPS completo non ispezionato; runtime/commit effettivo e dataset non inventariati; restore su copia non provato; training end-to-end assente; 403 dell'integrazione Claude in scrittura.

Prossima consegna autorizzata solo come preparazione: relazione sanitizzata delle differenze fra branch V3 e runtime, elenco dei buchi del dataset, inventario/manifest con hash e conteggi senza contenuti sensibili, e PR draft esclusivamente documentale. Nessuna modifica ai runner.

## Invarianti

- PAPER soltanto; nessun ordine LIVE.
- Storici, trade, posizioni, EventJournal, memoria, scoreboard e backup preservati.
- Nessun merge, deploy, Action, VPS, reboot, restart, reset, modifica rischio o API a pagamento.
- Nessuna chiave privata, passphrase, token, segreto, IP o dettaglio d'accesso pubblicato.
