# Checkpoint verificabile — Brain PAPER unpaused; primo ciclo completo non ancora attestato; Toro Profit Hunter approvato solo come sviluppo

**Data:** 13/11/2026 15:47 Europe/Rome  
**Ambito di questo checkpoint:** sola documentazione. Nessun accesso SSH autonomo, merge, deploy, Action, reset, ordine o modifica operativa eseguiti da questa automazione.

## Sintesi per la ripresa

Dopo il checkpoint delle 14:44 l'utente ha autorizzato separatamente l'avvio del solo Brain PAPER con i parametri correnti. L'utente ha poi eseguito via Termius lo script guarded preparato sul ramo dedicato: il preflight e la rimozione della sola pausa Brain risultano PASS.

**Stato verificato alle 15:10 Europe/Rome:** Brain PAPER unpaused, runner attivo, exit healthy, mandato approvato, rischio invariato, capitale iniziale 2.000 USDT e zero posizioni prima dell'avvio. Non è ancora attestato il primo ciclo produttivo completo su tutti gli otto mercati, né un'apertura, una chiusura o il PnL.

In una conversazione recente accessibile l'utente ha inoltre deciso di procedere con la versione corretta della proposta **Toro LONG Profit Hunter**, e solo dopo valutare la riaccensione di Falco e Toro accanto a Brain. Questa è una decisione di roadmap/sviluppo: non esistono ancora branch, commit, test, PR, deploy o riavvio verificati per tale nuova strategia.

## Fonti verificabili e limiti

- [Issue #95 — Brain PAPER](https://github.com/alexiptv82/SuperBot-Trading/issues/95), commento del 13/11/2026 ore 15:10 Europe/Rome con output Termius.
- Ramo `work/brain-rc84-market-data-hotfix-20261113`, HEAD [`9b1abcc33533d1ac216892630ff5904351385987`](https://github.com/alexiptv82/SuperBot-Trading/commit/9b1abcc33533d1ac216892630ff5904351385987).
- Documento Library `TORO-LONG-PROFIT-HUNTER-rapporto-indipendente.md`, creato il 13/11/2026: analisi indipendente, nessuna implementazione.
- Conversazioni recenti: accesso parziale; il messaggio decisionale Toro è visibile nel contesto disponibile, ma non si presume accesso a trascrizioni integrali o chat eliminate.
- Nessun controllo live continuo della VPS. Lo stato deriva dagli output/screenshot Termius registrati nell'Issue.

## Brain PAPER — avvio guarded eseguito

### Preparato

- Script `deploy/scripts/v3-brain-paper-unpause-guarded-20261113.sh`.
- Commit pinned `9b1abcc…`, figlio dell'installer hotfix `e9f7710…`.
- Verifiche fail-closed: stage e due soli fix dati previsti, modalità PAPER, runner/exit Brain, run-id/config, mandato, pausa presente, journal e budget integri, exit healthy, zero posizioni, heartbeat paused recente.
- Rollback previsto tramite ripristino della pausa Brain.

### Eseguito e attestato

Output registrato in Issue #95:

- preflight PASS;
- policy approvata, modello `deepseek-flash`;
- capitale iniziale 2.000 USDT e rischio invariato;
- journal chain OK, exit healthy, zero posizioni iniziali;
- rimossa esclusivamente la pausa Brain;
- risultato PASS: Brain PAPER unpaused, runner attivo, exit healthy;
- nessun restart, deploy aggiuntivo, modifica rischio, LIVE o coinvolgimento Falco/Toro.

### Non ancora attestato

- primo ciclo produttivo DeepSeek completo su tutti gli otto simboli;
- heartbeat e journal dopo il completamento del primo ciclo orario;
- decisioni operative nella run reale;
- `paper_open`, gestione TP/SL o chiusura;
- consumo budget reale del ciclo completo;
- PnL o redditività.

Il PASS precedente feed → DeepSeek → decisione → journal era isolato, su BTC e con esito `NO_TRADE`. Non va confuso con una prova operativa completa. `NO_TRADE` resta valido e nessun ordine deve essere forzato.

## Toro LONG Profit Hunter — decisione vs stato reale

### Decisione utente verificata

L'utente ha scelto di implementare la **versione corretta** descritta nel rapporto indipendente e, una volta completata e verificata, riaccendere Falco e Toro per osservarli insieme a Brain.

### Contenuto approvato per lo sviluppo, non ancora implementato

Il rapporto giudica la proposta originale **DA CORREGGERE** e raccomanda un solo backtest pre-registrato della variante corretta, con aspettative prudenti:

- ingresso LONG su rientro confermato sopra la Bollinger 100 su candela 1H chiusa;
- filtro/contesto 4H e protezione anti-coltello;
- cancello economico netto costi;
- ordine limit post-only e simulazione PAPER conservativa;
- stop basato su struttura/ATR, non percentuale stretta del margine;
- Profit Guardian a pavimento crescente;
- rischio fisso e leva come risultato, non come moltiplicatore arbitrario;
- nessun DCA iniziale, `NO_TRADE` e slot vuoti ammessi.

Le scelte residue di rischio indicate nel rapporto richiedono ancora fissazione esplicita prima del backtest; non vanno inventate da questo checkpoint.

### Stato GitHub verificato

- [PR #93](https://github.com/alexiptv82/SuperBot-Trading/pull/93) resta Draft/FAIL e non va integrata.
- [PR #94](https://github.com/alexiptv82/SuperBot-Trading/pull/94) resta Draft, PASS tecnico ma NO-GO strategico; Toro Twin OFF.
- Nessun nuovo branch/commit/PR verificato per Profit Hunter corretto.
- Nessuna implementazione, test, backtest, merge, deploy o attivazione Toro verificati.
- Falco resta invariato; nessuna riaccensione Falco/Toro è attestata.

## Tre portafogli PAPER — desiderato vs implementato

- **Brain:** 2.000 USDT, `deepseek-flash`, leva desiderata 20–50× soggetta ai gate rischio, kill gate 450, cap AI 0,75 USD/giorno, ciclo 60 minuti. Hotfix dati installato; Brain unpaused con guardrail PASS. Primo ciclo completo ancora da verificare.
- **Falco:** strategia SHORT originale congelata e non modificata. La futura riaccensione insieme a Toro è roadmap, non stato eseguito.
- **Toro:** nuova direzione LONG Profit Hunter corretta approvata per sviluppo e backtest; ancora non implementata né rilasciata. Le precedenti PR #93/#94 non diventano approvate per effetto della nuova decisione.

## Backup, chiavi e conservazione

- Backup privato dell'hotfix e backup SQLite: verificati/conservati secondo il riscontro precedente, senza pubblicare percorsi o contenuti sensibili.
- Extbackup `work/extbackup-bot-stopped-20261109`: preparato ma non installato.
- Copia cifrata age sul PC: PowerShell `ESITO: VERIFICA OK` e chiave pubblica coincidente; non certifica backup o restore sulla VPS.
- RC84 PR [#80](https://github.com/alexiptv82/SuperBot-Trading/pull/80) resta riferimento storico.
- Trading esclusivamente PAPER; storici ed EventJournal devono essere preservati.
- Nessun segreto, token, passphrase, chiave privata o dettaglio di accesso salvato.

## Blocker e prossimi passi

1. Monitorare soltanto in lettura il primo ciclo Brain: heartbeat, exit heartbeat, journal `brain_decision`/eventuale `paper_open`, budget e rifiuti rischio/feed. Non lanciare un secondo ciclo manuale concorrente.
2. Non dichiarare Brain pienamente operativo su otto simboli finché il primo ciclo completo non è documentato.
3. Per Toro creare un ramo isolato dalla base decisa, tradurre fedelmente la strategia corretta, fissare prima del test le scelte residue e predisporre un unico backtest pre-registrato. Questo checkpoint non autorizza merge/deploy.
4. Non riaccendere Falco/Toro finché Toro non è implementato, testato e sottoposto ad approvazione separata per il rilascio.
5. Preservare PAPER, backup, storici ed EventJournal; niente LIVE.

## Istruzioni di ripresa

Leggere nell'ordine: questo file, `STATO.md`, Issue #95, commit `9b1abcc…`, rapporto `TORO-LONG-PROFIT-HUNTER-rapporto-indipendente.md`, poi PR #93/#94 soltanto come precedenti negativi/test. Verificare sempre lo stato corrente prima di agire e distinguere fra decisione, preparazione, test, installazione e attivazione.
