# Brain Unico — finalizzazione anticipata dell'Arena e verifica dei limiti di rischio (MiniMax)

Stato: **PREPARAZIONE, nulla eseguito**. Nessun servizio fermato, nessuna chiusura, nessun dato reale letto. L'utente ha autorizzato la **pianificazione** della finalizzazione, **non la sua esecuzione**. Riferimenti: Issue #113 (decisioni del 19/11/2026: Brain Unico prioritario, Arena non bloccante, ogni intervento reale richiede runbook verificato e consenso separato), revisione ChatGPT della PR #117.

## 1. Principio

Si può concludere l'Arena prima delle 72 ore **senza perdere l'esperienza** e **senza chiusure manuali**: si ferma solo ciò che apre posizioni (i tre *runner*) e si lascia attivo il servizio di uscita di ogni run. Il runner gestisce `SIGTERM` in modo ordinato; la politica di uscita è `stop` / `take_profit` a 2R / `timeout` a 24 ore (`exit_policy.json`).

**Questo non garantisce che le posizioni si chiudano entro 24 ore.** Le uscite dipendono dal servizio di uscita, da un feed di prezzi valido e dalla politica caricata: `24 h + 1 h` è un'attesa *condizionata*, non una promessa. Per questo la procedura non assume la chiusura: la **verifica** a ogni controllo e, se le uscite non progrediscono, **si ferma e torna all'utente** (nessun timeout automatico, nessuna chiusura forzata).

## 2. Che cosa va preservato e dove vive

| Dato | Dove | Come si preserva |
|---|---|---|
| Decisioni (anche `NO_TRADE` e rifiuti) | `brain_decision` nel journal V3 della run | copia per file + hash chain ricalcolata |
| Posizioni, aperture, chiusure, esiti | `paper_open` / `paper_close` nello stesso journal | idem; le posizioni aperte sono *derivate* (aperture senza chiusura) |
| Chiusure manuali con motivazione | annotazioni dell'Arena nella cartella della run | copia per directory (`tree`) |
| Tracce di inferenza, budget, T0, battiti | `inference_trace.jsonl`, `budget*`, `arena_t0.json`, heartbeat | idem |
| Stato dei servizi | letture `systemctl show` | `summary.json` (prima/dopo) |
| Durata effettiva | primo/ultimo evento vs `trial_start_ms` | `arena_window` in `summary.json` |

Nulla viene cancellato, riscritto o "ricostruito": si fermano processi e si copiano file.

## 3. Procedura ordinata e idempotente

Tutti i comandi sono del bundle sigillato (download da commit fissato, controllo dell'hash, `python3 -I`), richiedono root e rifiutano un codice non fidato. **`--auth-ref` serve solo a tracciare: non è un'autorizzazione e non sostituisce il consenso esplicito dell'utente.**

| # | Passo | Comando | Effetto | Rischio |
|---|---|---|---|---|
| 1 | stato dei servizi | `status-services` | **solo systemd**: nessun database, nessun file di dati aperto; esito `SERVICES_OK` o `INCOMPLETE` (exit 1) | nullo |
| 2 | **checkpoint coerente PRE-stop (obbligatorio)** | `full --groups arena_deepseek,arena_qwen,arena_minimax --auth-ref …` | copia consistente per file di tutte e tre le run + audit di catena + manifest + audit dei limiti + stato dei servizi prima/dopo | basso, azione autorizzata a parte |
| 3 | **blocco nuove aperture** | `stop-openings --checkpoint-run <run_id del passo 2> --providers … --ended-early-reason TOKEN --auth-ref … --confirm-stop-runners` | `systemctl stop` dei **soli** runner scelti; le uscite restano attive | medio: modifica di servizi, consenso esplicito |
| 4 | avanzamento delle uscite | `full --groups …` ripetuto | per ogni run: posizioni aperte, età (da *adesso*), posizioni in ritardo di uscita, esito dell'audit | basso |
| 5 | snapshot definitivo | `full --groups … --ended-early-reason TOKEN` quando `still_open = 0` | copia consistente + manifest + ripristino provato + audit | basso |
| 6 | stop finale | **non incluso nel bundle** | solo dopo il passo 5 e con consenso separato | — |

### Il checkpoint PRE-stop è una condizione, non un suggerimento

`stop-openings` **rifiuta di fermare qualsiasi runner** se non gli si indica un `--checkpoint-run` che sia: un `full` (non un preflight) con esito `SNAPSHOT_GO`; che copra **tutti** i provider selezionati; con snapshot e manifest completi e nessun file instabile; con audit `PASS` o `WARN` e **tutte le catene V3 verificate**; con l'audit dei limiti presente per ogni run; con servizi invariati durante il checkpoint; **recente** (default 60 minuti) e non datato nel futuro; in una directory fidata (di root, non scrivibile da altri, non un link). Su qualunque rifiuto: **nulla viene fermato e nulla viene distrutto**, si torna all'utente.

**Se la copia coerente con i runner attivi non è possibile** (per esempio un DB WAL senza prova di quiescenza → NO-GO del `full`), la procedura **non prosegue silenziosamente** e il bundle non offre alcuna scorciatoia: la scelta (attendere, correggere la causa, o una decisione esplicita e scritta dell'utente di rinunciare al checkpoint con un runbook diverso) resta dell'utente. Quel runbook alternativo non esiste e non viene proposto qui.

### `stop-openings`: cosa può e non può fare

Può fermare **solo** i tre runner indicati (whitelist esatta, testata). Non può fermare le uscite o il close-bridge, chiudere posizioni, cancellare file, toccare configurazioni o T0, né leggere database. Non ferma nulla se un'uscita selezionata non è attiva, se systemd non risponde o se il checkpoint non è valido. È idempotente: rieseguito, i runner già fermi risultano `already_stopped`. Un elenco di provider vuoto **non** significa "tutti". Esito `OPENINGS_STOPPED` solo se nessuno stop è fallito, nessun runner è ancora attivo e le uscite hanno stesso PID e stesso numero di riavvii di prima.

### Attesa e NO-GO sulle uscite

- Il controllo (passo 4) riporta, per run: posizioni aperte, età della più vecchia **misurata da adesso** (non dall'ultimo evento, che con un feed fermo sarebbe ingannevole) e il numero di posizioni oltre `24 h + 1 h` (`open_overdue`).
- **NO-GO / attenzione** se `open_overdue > 0` (flag `open_positions_overdue_for_exit`), se un'uscita non è `active`, se `NRestarts` cambia, o se le posizioni aperte non diminuiscono tra due controlli. In quel caso: **nessun timeout automatico, nessuna chiusura incontrollata**, si torna all'utente con i numeri.
- La chiusura manuale esiste (close-bridge e annotazione) ma sporca l'apprendimento: l'esito diventa `manual`, non imitabile alla cieca. Se l'utente la richiede, va fatta posizione per posizione con motivazione; il dataset la conserverà con il flag `manual`.

Dopo lo stop: `ended_early_reason` e la durata effettiva (`arena_window.effective_hours` contro `planned_hours = 72`) restano nel riepilogo. **I risultati non vanno confrontati come gara da 72 ore completa.**

## 4. MiniMax: la perdita richiede una verifica urgente dei limiti?

**Dati.** L'utente riferisce circa −800 PAPER (−40 % su 2000); l'ultimo valore nel diario (18/11, 19:35) era circa −222. Non posso verificare né l'uno né l'altro: i journal sono di root. **Il −800 non è certificato.**

**Limiti configurati** (copia pubblica delle config, identici per le tre run; il journal **non** riporta la politica effettivamente caricata, quindi `policy.verified_against_run = false`):

| Limite | Valore | Su 2000 USDT |
|---|---|---|
| perdita allo stop per posizione | 4,29 % del capitale e 21,4 % del margine | ≈ 85,7 USDT |
| rischio aperto aggregato | 12 % | 240 USDT |
| margine per posizione / totale | 20 % / 55 % | 400 / 1100 USDT |
| leva | 20–50 | — |
| capitale minimo per aprire | 450 | −77,5 % |
| freno giornaliero (giorno UTC) | avviso 35 %, blocco 50 % del capitale di inizio giornata | — |

**Valutazione, con cautela.** Un −40 % *complessivo* **non** consente di dedurre il rispetto del freno *giornaliero*: dipende da come la perdita si distribuisce nei giorni UTC, dal non realizzato e dalla storia dei blocchi, che il journal non contiene. Si può dire solo che −40 % non supera, di per sé, né il blocco giornaliero del 50 % né il capitale minimo, e che **non è una violazione provata**. Non è nemmeno un esito sano: una perdita superiore al 40 % in pochi giorni resta **strategicamente inadatta a un futuro profilo LIVE**, anche se compatibile con una politica permissiva scelta per l'esperimento.

**Che cosa può dimostrare l'audit (`risk_audit`)**, dalla *copia* del journal e solo con numeri:
- `no_breach_proven`: nessuna violazione provata dai dati disponibili. **Non** significa "nessun problema".
- `fully_checked`: **sempre `false`**; `not_checkable` elenca ciò che il journal non permette di verificare (equity non realizzato, calcolo esatto del freno giornaliero, storia dei blocchi, politica caricata dalla run).
- `data_gaps`: eventi senza i campi numerici necessari. Un dato mancante **non vale zero**: viene contato e rende falso `no_breach_proven`.
- ripartizione per **giorno UTC** (capitale di inizio giornata, perdita realizzata, frazione, aperture dopo il blocco provato dal solo realizzato); il blocco giornaliero è un **limite inferiore**.
- `hard_flags` (violazioni indicative: aperture dopo il blocco, rischio per posizione molto sopra il tetto, leva fuori profilo, apertura con capitale ≤ 450, rischio aggregato o margine oltre i limiti, chiusure orfane o doppie) e `soft_flags` (perdita realizzata oltre il tetto per gap/slippage, durata oltre il massimo, posizioni in ritardo di uscita, dati mancanti).
- i rapporti usano "capitale = iniziale + realizzato": sono **indicativi** (si riportano le soglie 1,0 e 1,1).

**Raccomandazione.** L'urgenza è *integrità dell'esperimento e fiducia nel risk manager che il Brain Unico riuserà*, non esposizione reale (i fondi sono simulati). Ordine, ciascun passo con consenso dell'operatore:
1. `status-services` (solo systemd): servizi attivi, nessun database toccato.
2. `full --groups arena_minimax --auth-ref …`: copia del solo journal MiniMax + audit; non tocca servizi. Posizioni aperte e limiti vengono **da qui**, non da una lettura dal vivo.
3. Se `hard_flags` non è vuoto: valutare `stop-openings --providers minimax …`, **che richiede un checkpoint valido** (il `full` del passo 2 lo è se copre il provider).
`no_breach_proven = true` con `fully_checked = false` significa: *la violazione non è provata*, non *i limiti hanno retto*.

## 5. Verifica (sintetica, non replicata da ChatGPT)

`sealed/test_sealed.py` (76 test): whitelist dello stop; nessuno stop senza checkpoint valido e un test per ciascuna causa di rifiuto (run id, percorso non fidato, non-`full`, verdetto, copertura dei provider, snapshot/manifest/audit/catene, limiti di rischio, servizi, età); uscite intatte; idempotenza; `[]` ≠ tutti; `status-services` che non apre database né file di dati, con esito `INCOMPLETE` esplicito; età delle posizioni misurata da adesso. `phase0/test_risk_audit.py` (24 test): ciascun limite, dati mancanti ≠ zero, ripartizione giornaliera, `fully_checked` sempre falso, politica non verificata. Ogni controllo è stato verificato anche per mutazione (reintroducendo il difetto in una copia di scratch con bundle ricostruito, almeno un test fallisce): **28 su 28 rilevati** per questa revisione (ciascuna condizione del checkpoint, stop senza checkpoint, database toccato da `stop-openings` o `status-services`, esito sempre 0 o sempre OK, unità mancanti, età non da adesso, dati mancanti trattati come zero, `fully_checked` vero, politica dichiarata verificata, ripartizione giornaliera assente, posizioni in ritardo non segnalate), dopo i 18 su 18 della versione precedente.

**Verifica indipendente del bundle.** L'hash del bundle va calcolato sui *byte del commit* (`git show <commit>:ops/brain-unico/sealed/phase0_sealed.py | sha256sum`) e confrontato con il messaggio ricevuto; dopo **qualunque** patch l'hash cambia e quello precedente non vale più.
