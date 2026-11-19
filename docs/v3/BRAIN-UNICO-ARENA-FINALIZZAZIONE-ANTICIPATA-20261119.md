# Brain Unico — finalizzazione anticipata dell'Arena e verifica dei limiti di rischio (MiniMax)

Stato: **PREPARAZIONE, nulla eseguito**. Nessun servizio fermato, nessuna chiusura, nessun dato reale letto. Riferimenti: Issue #113 (decisione del 19/11/2026 10:20: Brain Unico prioritario, Arena non bloccante), procedura dell'operatore (`BRAIN-UNICO-FASE0-PROCEDURA-OPERATORE-20261119.md`).

## 1. Principio

L'Arena può essere conclusa prima delle 72 ore **senza perdere nulla** e **senza chiusure manuali**: si ferma solo ciò che apre posizioni (i tre *runner*), mentre il servizio di uscita di ogni run continua a gestire le posizioni con le regole normali. Il codice lo conferma: il runner gestisce `SIGTERM` in modo ordinato, le uscite sono un servizio separato, e la politica di uscita è `stop` / `take_profit` a 2R / `timeout` a 24 ore (`exit_policy.json`). Quindi **tutte le posizioni si chiudono da sole entro circa 24 ore**, con motivo e timestamp nel journal append-only e senza il marchio `manual`, che un apprendimento serio deve trattare a parte.

## 2. Che cosa va preservato e dove vive

| Dato | Dove | Come si preserva |
|---|---|---|
| Decisioni (anche `NO_TRADE` e rifiuti) | `brain_decision` nel journal V3 della run | copia per file + hash chain ricalcolata |
| Posizioni, aperture, chiusure, esiti | `paper_open` / `paper_close` nello stesso journal | idem; le posizioni aperte sono *derivate* (aperture senza chiusura) |
| Chiusure manuali con motivazione | annotazioni dell'Arena nella cartella della run | la copia è per directory (`tree`), non solo per journal |
| Tracce di inferenza, budget, T0, battiti | `inference_trace.jsonl`, `budget*`, `arena_t0.json`, heartbeat | idem |
| Stato dei servizi al momento dello stop | letture `systemctl show` | `summary.json` (prima/dopo) |
| Durata effettiva | primo/ultimo evento vs `trial_start_ms` | `arena_window` in `summary.json` |

Nulla viene cancellato, riscritto o "ricostruito": si fermano processi e si copiano file.

## 3. Procedura ordinata e idempotente (mappata sui passi della Issue)

Comandi del bundle sigillato (stessa riga di avvio della procedura dell'operatore: download da commit fissato, controllo dell'hash, `python3 -I`). Tutti richiedono root e rifiutano un codice non fidato.

| Passo (Issue #113) | Comando | Effetto | Rischio |
|---|---|---|---|
| (0) fotografia a metà gara, facoltativa ma consigliata | `full --groups arena_deepseek,arena_qwen,arena_minimax --auth-ref …` | copia consistente + audit + **limiti di rischio** + manifest; nessun servizio toccato | basso |
| (b) stato e posizioni, in qualsiasi momento | `status` | unità Arena e posizioni aperte per provider, sola lettura | nullo |
| (a) **blocco nuove aperture** | `stop-openings --providers … --ended-early-reason TOKEN --auth-ref … --confirm-stop-runners` | `systemctl stop` dei **soli** runner scelti; le uscite restano attive | medio (modifica di servizi: serve consenso operativo) |
| (c) gestione delle uscite | nessun comando: lavora l'exit service | chiusure con motivo `stop`/`take_profit`/`timeout`, journal append-only | — |
| (d) riconciliazione PnL, ID, hash chain | `status` (ripetuto fino a `open_now = 0`) e poi `full` | verifica che non restino posizioni aperte né orfane; hash chain ricalcolata dall'audit | nullo |
| (e) snapshot definitivo | `full --groups … --ended-early-reason TOKEN --auth-ref …` | copia consistente su directory privata + manifest + ripristino provato + audit | basso |
| (f) stop finale | **non incluso nel bundle** | solo dopo `open_now = 0` per tutti e snapshot definitivo; richiede un consenso separato | — |

`stop-openings` **non può**: fermare altro che i tre runner (whitelist esatta, testata), toccare le uscite o il close-bridge, chiudere posizioni, cancellare file, modificare configurazioni o T0. Si rifiuta di fermare **qualsiasi** runner se un'uscita selezionata non è attiva (le posizioni resterebbero senza chi le chiude) e non ferma nulla se systemd non risponde. È idempotente: rieseguito, i runner già fermi risultano `already_stopped` e non viene emesso alcun comando. Un elenco di provider vuoto **non** significa "tutti".

Dopo lo stop: `ended_early_reason` e la durata effettiva (`arena_window.effective_hours` contro `planned_hours = 72`) restano nel riepilogo. **I risultati non vanno confrontati come gara da 72 ore completa.**

### Attesa e GO/NO-GO

- Attesa massima prevista: 24 ore (durata massima delle posizioni) più un margine di 1 ora. `status` mostra `open_now` per provider.
- **GO per `stop-openings`**: systemd leggibile; per ogni provider selezionato, runner caricato ed exit service `active`.
- **NO-GO**: exit service non attivo, runner non trovato, systemd non disponibile. Non viene eseguito alcun comando.
- **Esito `OPENINGS_STOPPED`** solo se: nessuno stop fallito, nessun runner ancora attivo, exit service con stesso PID e stesso numero di riavvii di prima.

### Se serve chiudere subito

La chiusura manuale delle posizioni (close-bridge e annotazione) esiste, ma sporca l'apprendimento: l'esito diventa `manual`, non imitabile alla cieca. Per questo la procedura **non** la usa. Se l'utente la richiede, va fatta posizione per posizione con motivazione, e il dataset la conserverà con il flag `manual`.

## 4. MiniMax: la perdita richiede una verifica urgente dei limiti?

**Dati.** L'utente riferisce circa −800 PAPER; l'ultimo valore nel diario (18/11, 19:35) era circa −222 (realizzato). Non posso verificare né l'uno né l'altro: i journal sono di root e non leggibili da `superbot-agent`. **Il −800 non è certificato.**

**Cosa dicono i limiti configurati** (identici per le tre run, `risk_policy_hash` comune):

| Limite | Valore | Su 2000 USDT |
|---|---|---|
| perdita allo stop per posizione | 4,29 % del capitale e 21,4 % del margine | ≈ 85,7 USDT |
| rischio aperto aggregato | 12 % | 240 USDT |
| margine per posizione / totale | 20 % / 55 % | 400 / 1100 USDT |
| leva | 20–50 | — |
| capitale minimo per aprire | 450 | −77,5 % |
| freno giornaliero (UTC) | avviso 35 %, **blocco 50 %** del capitale di inizio giornata | — |

**Valutazione.** −800 su 2000 è **−40 %**: sopra la soglia di avviso (35 %) ma **sotto** il blocco giornaliero (50 %) e ben sopra il capitale minimo (450). Se la perdita si è formata su due giorni UTC, nessun giorno raggiunge nemmeno l'avviso. Quindi **−800 è compatibile con i limiti** decisi dall'utente: non basta, da solo, a dire che un gate sia rotto. Per perdere 800 con posizioni dentro il tetto servono almeno 10 stop pieni, plausibile in circa due giorni con 27 simboli, leva 20–50 e cicli orari. Il regime è però permissivo *per scelta*: la sua efficacia come protezione è bassa, e il rischio per il Brain Unico è di ereditarlo.

**Quando sarebbe una violazione** (e solo il journal può dirlo): apertura dopo che il solo realizzato ha già superato il blocco giornaliero; rischio per posizione molto sopra il tetto; leva fuori da 20–50; apertura con capitale ≤ 450; posizioni oltre 24 ore; chiusure orfane o duplicate. `risk_audit.py` calcola tutto questo dalla **copia** del journal e riporta solo numeri e codici (`limits_held`, `hard_flags`, `soft_flags`, rapporti rispetto ai tetti). Limite dichiarato: il capitale del sistema include il non realizzato, assente dal journal; i rapporti sono indicativi (si riportano soglie 1,0 e 1,1) e il blocco giornaliero è un **limite inferiore** (solo realizzato).

**Raccomandazione.** Urgenza = *integrità dell'esperimento e fiducia nel risk manager che il Brain Unico riuserà*, non esposizione reale (i fondi sono simulati). Al primo consenso operativo, nell'ordine:
1. `status` (sola lettura, nessuna copia): posizioni aperte e stato servizi.
2. `full --groups arena_minimax --auth-ref …`: copia del solo journal MiniMax + audit dei limiti. Non tocca servizi.
3. **Solo se** il report indica `hard_flags` non vuoto: `stop-openings --providers minimax …`, che blocca le sole nuove aperture di MiniMax e preserva le uscite.
Se `limits_held = true`, nessuna azione sul rischio: la perdita è l'esito di una strategia, non di un guasto dei gate, ed è proprio il tipo di esperienza che il Brain Unico deve imparare.

## 5. Verifica (sintetica)

`sealed/test_sealed.py` (61 test) copre: whitelist dello stop, assenza di stop se un'uscita non è attiva o systemd non risponde, idempotenza, uscite intatte (stesso PID e riavvii), fallimento o inefficacia dello stop, `[]` ≠ tutti, validazione di motivo e riferimento, `status` che non apre DB WAL fermi né crea file, percorsi non fidati non letti, riepiloghi senza percorsi né contenuti, selezione dei gruppi. `phase0/test_risk_audit.py` (17 test) copre ogni limite e uno scenario −800 dentro i limiti. Ogni controllo è stato verificato anche per mutazione: reintroducendo il difetto in una copia di scratch (bundle ricostruito), almeno un test fallisce. **18 mutazioni su 18 rilevate** (whitelist dello stop, guardia sulle uscite, idempotenza, `[]` ≠ tutti, validazione, `status` su WAL fermi, catena dei percorsi, filtro dei gruppi e ciascun limite dell'audit di rischio, inclusa l'esportazione di contenuti).
