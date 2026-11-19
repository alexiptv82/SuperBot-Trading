# Rapporto tecnico — Brain Unico (fase read-only, 19/11/2026)

Autore: Claude Code (clone di laboratorio). Riferimento: Issue #113.
Ambito: sola lettura di GitHub (`main`, ramo `diario`, PR #110 e #112). Nessun accesso alla VPS, ai runner, ai servizi o a credenziali. Nessun push, merge, deploy o Action. Nessun importo o saldo reale in questo documento.

## 0. Sintesi

1. **`main` non rappresenta il sistema reale.** `main` ha 296 file (bot classici + desk + rule_pool). Il sistema V3/Arena (circa 715 file, `backend/v3/`, 162 file) vive in rami `work/*` e nelle PR draft #110 e #112. La verità di runtime è sulla VPS e non è verificabile da qui. Prima azione: manifest commit↔runtime (§2).
2. **La conservazione dei dati è ben progettata nel codice, ma non è ancora certificata sulla VPS.** Esistono journal append-only con catena SHA-256, audit di riconciliazione, importatore offline idempotente, certificazione backup F0. Mancano: backup esterno cifrato attestato, restore provato sui dati reali, manifest SHA256 immutabile. L'`age` PC dice `VERIFICA OK` ma non certifica la VPS (come già scritto nel diario).
3. **L'apprendimento oggi è "memoria + scoreboard statistico", non un modello addestrato.** Cosa esiste e cosa manca è in §3. Il difetto principale: l'evento `brain_decision` del V3 **non salva lo snapshot causale delle feature** e i `NO_TRADE` non vengono etichettati a posteriori. Senza questo, nessun modello quantitativo è addestrabile.
4. **Il percorso più sicuro:** Brain Unico = nuovo strato *sopra* il journal V3, con tre cambiamenti additivi (schema decisione con feature, etichettatore forward dei NO_TRADE/rifiutati, modello locale in shadow). Nessun reset, nessuna migrazione distruttiva, nessuna modifica ai runner in produzione finché non c'è consenso separato.

## 1. Stato dell'architettura attuale

### 1.1 Componenti (da codice PR #112 + diario)

| Area | Dove | Stato |
|---|---|---|
| Falco/Toro classici (LONG/SHORT, regole, Claude consulente) | `backend/desk/*`, `bot_engine.py` (main) | Spenti; storici da preservare |
| Brain storico "Free" | `brain_free_*`, `desk/brain.py`, `brain.sqlite3` | Fermo (halt `exit_service_unhealthy`); exit service sano |
| V3 journal | `v3/events.py` | SQLite append-only, `portfolio_id` ∈ {hawk, bull, brain}, hash chain, trigger anti UPDATE/DELETE |
| Rischio deterministico | `v3/risk.py`, `runner/exit_service.py`, `exit_worker.py`, `daily_loss.py` | Autonomo dall'AI (requisito già soddisfatto in struttura) |
| Executor PAPER | `v3/executor/paper.py`, `paper_close.py` | Solo PAPER |
| Brain F2 (analyst→reviewer→risk gate→memoria) | `v3/brain_f2/engine.py` (31 KB) | DeepSeek analista, Claude reviewer selettivo |
| Vista mercato/scoreboard per DeepSeek | `brain_view/`, `brain_market/` (L4/L5) | Prompt riceve scoreboard strategia×lato×regime |
| Arena 72h | `v3/arena/*` | 3 wallet (DeepSeek, Qwen, MiniMax), T0 comune, stop nuove aperture 21/11 18:03 |
| Lab statistico | `v3/learning/{expectancy,opportunity,walkforward}.py`, `v3/lab/` | Moduli puri e testati; non collegati a un ciclo di training |
| Dashboard | `frontend/src/pages/*`, route `/arena`, `/overview`, `/classic`, `/supervisor`, `/live*`, `/performance`, `/trades` | ~15 pagine, frammentata |
| Backup | `deploy/scripts/backup_*.py`, `extbackup_watch.py`, `v3/arena/backup.py`, `v3/backup_certification.py` | Locale operativo; esterno preparato, non installato |
| Collaborazione AI | `CLAUDE.md`/`AGENTS.md` (identici), ramo `diario` | Funzionante; vedi §7 |

### 1.2 Osservazioni di rischio architetturale

- **Deploy via file `.trigger` + GitHub Actions** (≈81 workflow, ≈55 trigger in `deploy/`): potente ma costoso e con superficie ampia. Per Brain Unico serve un percorso di rilascio con meno workflow, diretto ma controllato (§6, fase 5).
- **Regola 7 di AGENTS.md** (repo pubblico, niente saldi) è in tensione con il diario che riporta P&L PAPER. I PAPER non sono reali ma conviene decidere la politica (consiglio: P&L PAPER ok, mai dati Bitget reali).
- **Divergenza universo:** il ramo gara `6a88857` scorre oltre rank 25 dopo le esclusioni. Il mandato dice "top 25 per rank assoluto + XAU/XAG". Lo snapshot reale usato dalla gara non è ancora ispezionato. Nel config DeepSeek nel repo ci sono 27 simboli, incluse GRAM e CC, che è plausibile indicatore dello stesso scarto. Da verificare in sola lettura sullo snapshot; non è una violazione certificata.
- **Gara in corso:** stop nuove inferenze 21/11 18:03:12. Qualsiasi fermo o restart prima è escluso.

## 2. Piano di preservazione dei dati

Principio: *nessuna scrittura sui dati originali; ogni operazione lavora su copie verificate.*

### 2.1 Inventario da fare (richiede solo un utente VPS in lettura, vedi Fase 0)

| Fonte | Contenuto | Rischio |
|---|---|---|
| directory dati dei classici (Falco/Toro) | `trade_history.jsonl`, `lessons.md`, `errors.md`, `learning_log.jsonl`, `state_v2.json`, `archive/` per run | Il learning log è cumulativo; l'archiviatore legacy non lo copia nelle cartelle `archive/` |
| Brain storico `brain.sqlite3` (+ WAL/-shm) | ~8.4k eventi al 02/11, ora più | Copia con file-copy a caldo può perdere righe nel WAL: usare `Connection.backup()` (già in `backup_certification.py`) |
| Arena: `journal.db` per provider, annotazioni, trace inferenza | Tre wallet indipendenti | Non unire i journal alla cieca (già stabilito) |
| V3 journal brain/hawk/bull | Eventi con hash chain | Verificare `verify_chain()` |
| Config, policy, snapshot universo, `arena_model_pricing`, `arena_universe_snapshot` | Provenienza della gara | Versionare con hash |
| Rami Git (255 branch remoti, tra cui `archive/falco-short-before-ai-arena-20261116`, `backup/*`, `stable/*`) | Storia del codice | Fare un mirror (`git clone --mirror`) e un bundle |

### 2.2 Manifest immutabile (proposta)

Un file `MANIFEST-<data>.json` (non nel repo pubblico se contiene percorsi sensibili; nel repo solo l'hash radice) con, per ogni artefatto: percorso logico, SHA256, byte, mtime, conteggio righe/eventi, per i journal `max_seq` + `last_event_hash`, `run_id`/`portfolio_id` distinti, `schema_version`, commit del codice che lo ha prodotto. Il digest del manifest va conservato **fuori host** (e nel diario come hash, non il contenuto).

### 2.3 Prova di ripristino

1. Estrarre la copia in directory vuota separata, su utente non-root.
2. `f0_cli verify-brain` / `verify-classic` (già nel codice) con testimone esterno.
3. `legacy_multirun`/`legacy_accounting` per quadrature (al 02/11: 534 chiusure Falco/Toro su run 1–8, Brain 182 chiusure con `ISSUES=NONE`; da rieseguire sui dati aggiornati).
4. Contare gli eventi e confrontare con il manifest. Esito binario, scritto nel diario.

### 2.4 Regole di non-distruzione

- Nessun `DELETE/UPDATE` (i trigger lo impediscono nel journal; imporlo anche con permessi di file `0440` sulle copie).
- Per "riaprire" un portafoglio si crea un nuovo `run_id`, mai un reset.
- Importazione cross-run in un **archivio nuovo** con `source_system`, `source_run`, `policy_version`, `schema_version`, `source_hash` per riga. Un evento duplicato in più fonti (es. chiusura in `state_v2.json` e in `trade_history.jsonl`) deve avere un ID stabile (già fatto in `legacy_multirun`).
- Tutto ciò che è di Toro, Falco, Brain storico, Qwen/MiniMax: archivio read-only, **mai** cancellato né ricostruito.

## 3. Memoria e apprendimento: cosa esiste davvero

### 3.1 Cosa esiste (verificato nel codice)

| Meccanismo | Natura | Alimenta decisioni? |
|---|---|---|
| `learning_log.jsonl` legacy (`open/close/candidate/split_*`, feature d'ingresso causali, MAE/MFE, net_r, `candidate` = decisioni di aprire non eseguite) | **Dataset utile.** Schema v1, append-only, tetto 250 MB | No: "Non cambia in nulla le decisioni" |
| `lessons.md`, `errors.md` (legacy, aggiornati da Claude) | Memoria testuale | Sì (nel prompt classico) |
| `load_symbol_stats()` / `stats_summary()` (`desk/brain.py`) | Statistiche per simbolo sugli ultimi 200 trade | Sì, nel prompt del Brain storico |
| V3 `TradeOutcome` (`outcomes.py`): net bp, R, costi, exit reason, `link_status`, regime, strategy_id | **Etichette affidabili**, ricalcolate e verificate | Input di scoreboard |
| V3 `build_scoreboard` → prompt DeepSeek L4/L5 | Expectancy per strategia×lato×regime con bootstrap a blocchi di giorni, `status` positive/negative/inconclusive/insufficient | **Sì**: unico circuito di apprendimento quantitativo reale, ma solo descrittivo |
| `learning/opportunity.py` | Etichettatore a posteriori di candidati non eseguiti (+15m/1h/4h, barriera toccata per prima) | **No: modulo puro non collegato** |
| `learning/walkforward.py` | Walk-forward con decay IS/OOS | Non collegato |
| `brain_f2` `MemoryEpisode` | Lista **in RAM** | Si perde al riavvio (nel journal finisce solo `brain_decision`) |
| `arena/learning_evidence.py` | Bundle di evidenze sola lettura per revisione futura | Dichiaratamente: "NO training" |

### 3.2 Lacune che impediscono un modello addestrabile

1. **`brain_decision` salva solo** `kind, status, rationale, sources, symbol, regime` (+ `strategy_id` se OPEN approvato). **Non salva le feature** note al timestamp (indicatori, funding, OI, long/short ratio, correlazioni, spread/liquidità), né SL/TP proposti per i `NO_TRADE` e i rifiutati dal risk gate. Il vecchio `learning_log` le aveva; il V3 le ha perse.
2. **I NO_TRADE e i rifiutati non hanno etichetta forward.** Sono la maggior parte del campione e il solo modo di misurare falsi negativi. `opportunity.py` esiste ma non è alimentato da candele ancorate al timestamp.
3. **Mancano MFE/MAE e funding pagato** nel `TradeOutcome` (ci sono PnL, costi, R). Servono per calibrare TP/SL.
4. **Nessun modello registry, nessun ciclo di training, nessun confronto shadow.** Lo scoreboard non predice; riassume.
5. **Campione piccolo.** Ordine di grandezza: ~534 chiusure classiche, ~182 Brain, pochi trade per wallet Arena in 72 ore. Insufficiente per LightGBM sulle sole chiusure; per questo gli esempi devono includere NO_TRADE/rifiutati con etichette forward (migliaia di righe).
6. **Verità sulla memoria testuale:** `lessons.md` non è addestramento. L'Issue lo dice già (Fase A3); lo ribadisco nel rapporto.

## 4. Progetto del Brain Unico

```
        ┌──────────── market data (Bitget pubblico, candele ancorate) ────────────┐
        ▼                                                                          │
 Feature Snapshotter (puro, causale, versionato) ──► feature_snapshot (journal)    │
        │                                                                          │
        ▼                                                                          │
 DeepSeek (decisore: OPEN/LONG/SHORT/NO_TRADE + SL/TP + thesis_id)                 │
        │            ▲ scoreboard + modello locale (probabilità/EV calibrati)      │
        │            │ advisory: Falco SHORT (solo segnale) • Claude (eventi)      │
        ▼                                                                          │
 Policy gate deterministico (risk.py) ──► Executor PAPER ──► Exit service autonomo │
        │                                         │                                │
        ▼                                         ▼                                │
 Journal V3 append-only  ◄──── outcomes + label forward (opportunity) ◄────────────┘
        │
        ▼
 Evidence store (SQLite/Parquet, versionato) ──► Training offline ──► Model registry ──► shadow ──► promozione con OK utente
```

Scelte:

- **Un solo portafoglio `brain`** in produzione PAPER. Falco/Toro/Qwen/MiniMax: archivi read-only con `source_system`.
- **DeepSeek decide**; ogni decisione porta `decision_id`, `thesis_id`, `policy_version`, `prompt_version`, `model_version`, `feature_snapshot_hash`.
- **Claude** solo su condizioni dichiarate e contate a budget: es. conflitto DeepSeek↔modello locale, evento macro, drawdown giornaliero oltre soglia, posizione in profit giveback. Mai nel percorso delle uscite.
- **Falco SHORT** emette un segnale che entra nel prompt come feature `falco_short_signal`, mai come ordine. Va registrato come feature, così se ne misura il valore.
- **Risk manager / exit service deterministico**: invariato e indipendente (già nei requisiti e nel codice).
- **Universo:** top 25 crypto per rank assoluto + XAU/XAG idonei, filtro liquidità, snapshot con hash, versione fissa per test. Un test deve fallire se un simbolo oltre rank 25 entra.
- **Thesis ID:** hash stabile di (simbolo, lato, struttura/livello di invalidazione, strategia); il reingresso con stesso thesis richiede una nuova conferma oggettiva registrata come evento `thesis_reconfirmed`.

### 4.1 Dashboard unica Samsung (semplificazione)

Oggi: ~15 pagine (Overview V3, Classici, Agenti, Trade, Performance, Settings, Live*, Brain archivio, Arena, Supervisor). Proposta: **5 schede**, un solo portafoglio.

| Scheda | Contenuto |
|---|---|
| **Oggi** | Equity mark-to-market verificata (con timestamp prezzi e stato `fresh/stale`), PnL aperto/realizzato, stato PAPER/runner/exit/heartbeat, allarmi |
| **Posizioni** | Aperte con SL/TP, thesis, PnL, pulsante chiudi (flusso manual-close già collaudato) |
| **Storico** | Chiusure con filtri, PnL per simbolo, statistiche LONG/SHORT, sorgente (Brain/Falco/Toro/Arena) come filtro, non come sezione |
| **Training** | Versione modello, calibrazione, shadow vs live, campione disponibile, ultima valutazione, rollback |
| **Controlli** | Interruttori PAPER già collaudati, log, backup/ripristino stato, WebAuthn + Telegram invariati |

Passi: (1) congelare le route vecchie come `/archivio/*` (non cancellare nulla); (2) nuova `BrainHome` che riusa `brainArenaModel.js`, `BrainPortfolioSection`, `BrainPerformancePanel`, `OverviewCloseControls`; (3) un solo endpoint `GET /api/brain/summary` read-only con schema versionato; (4) test frontend esistenti come base (Jest già presenti) più uno scenario Samsung (390×844); (5) nessun cambiamento ai servizi backend per la prima release UI (`UI_ONLY`, come già fatto con Arena).

## 5. Architettura del sistema di training

### 5.1 Dati (tabella `training_example`, una riga per *decisione* e per *candidato*)

| Gruppo | Campi |
|---|---|
| Identità | `example_id`, `decision_id`, `thesis_id`, `portfolio_id`, `run_id`, `source_system`, `schema_version`, `policy_version`, `prompt_version`, `model_version` |
| Tempo | `decision_ts_ms` (la candela più recente usata è chiusa e precedente) |
| Decisione | `action` ∈ {LONG, SHORT, NO_TRADE, REJECTED_BY_RISK, REJECTED_BY_COOLDOWN…}, SL/TP/leva proposti, confidenza, `manual_reason` |
| Feature causali | indicatori multi-timeframe, ATR%, volatilità realizzata, volume relativo, funding e predicted, OI e variazione, long/short ratio, spread/profondità, regime, BTC/ETH come contesto, correlazione con posizioni aperte, ora/giorno, `falco_short_signal` |
| Label | forward return netto a 15m/1h/4h, barriera toccata per prima (SL/TP) con esito ambiguo marcato, MFE/MAE, R realizzato, slippage, commissioni, funding pagato, motivo uscita, tempo in posizione |
| Qualità | `link_status`, `label_complete`, `is_synthetic` (sempre falso per training; i sintetici restano separati) |

Si riutilizzano `features/indicators.py`, `outcomes.py`, `opportunity.py`; si aggiunge un **Feature Snapshotter** puro e una tabella `evidence_store` separata dal journal (derivata, ricostruibile, mai fonte di verità).

### 5.2 Modello

- **Obiettivo:** stimare `E[net_R]` e `P(TP prima di SL)` per candidato; calibrare i parametri TP/SL; produrre un punteggio che DeepSeek vede e il gate usa come filtro consultivo.
- **Algoritmo:** LightGBM (gradient boosting) a bassa complessità, regolarizzato, con calibrazione isotonica o Platt. Baseline obbligatorie: base rate, regola semplice, scoreboard attuale.
- **Split:** cronologico con **embargo** (≥ durata massima di posizione) e *purging* delle label che si sovrappongono; walk-forward riusando `learning/walkforward.py`; blocchi di giorni (già nel bootstrap).
- **Metriche:** EV netto per trade con IC, Brier/ECE, `precision@k` sui candidati accettati, decay IS→OOS, risultato per regime e per lato.
- **Soglie minime** (decisione dell'utente, qui solo proposta): ≥ 300 esempi etichettati e ≥ 20 giorni distinti per una prima versione "shadow"; ≥ 1000 e ≥ 45 giorni per promozione consultiva.
- **Divieti:** nessun trade sintetico spacciato per reale; nessun training sui propri output senza label di mercato; nessun riaddestramento dei pesi DeepSeek.

### 5.3 Ciclo

1. **Raccolta** (continua, sempre attiva, nessun effetto sulle decisioni).
2. **Etichettatura forward** (job batch, solo candele chiuse).
3. **Training offline** su copia (nessuna scrittura sul journal).
4. **Registry:** cartella versionata con modello, hash dati, hash codice, parametri, report. Immutabile.
5. **Shadow:** il modello stima ma non decide; si confronta con DeepSeek e con l'esito reale.
6. **Promozione:** solo con report vs versione precedente, shadow sufficiente, rollback pronto, **OK esplicito dell'utente**.
7. **Esperimenti uscite** (profit giveback ecc.): uno alla volta, pre-registrati nel formato già usato in `v3/lab/PREREGISTRAZIONE.md`.

### 5.4 Preventivo AI/VPS (stime di ordine di grandezza, da confermare)

- Training LightGBM su qualche decina di migliaia di righe: secondi–minuti su CPU; nessun costo AI. Nessuna GPU.
- Raccolta feature: chiamate pubbliche Bitget, già nel perimetro.
- DeepSeek: da config attuale (flash, 60 min/ciclo, tetto giornaliero 2 USD per wallet Arena; 0,30/1,20 USD per milione di token). Il Brain Unico a un solo wallet costa meno della gara a tre. Claude: da contingentare con un tetto separato per giorno.
- Spazio: `learning_log` aveva tetto 250 MB; l'evidence store con snapshot per ogni ciclo e simbolo cresce di più (ordine: decine di MB/giorno non compressi). Parquet/zstd o SQLite con retention della sola vista derivata, mai del journal.

## 6. Roadmap delle implementazioni

Ogni fase = branch `claude/<fase>` + PR **draft**, `[skip ci]` per documenti, test locali, nessun deploy.

| Fase | Contenuto | Rischio | Richiede consenso |
|---|---|---|---|
| **0** Ambiente | Mirror Git, inventario read-only, tabella commit↔runtime, delta file locali VPS vs Git | Nullo | Accesso VPS in sola lettura dell'utente (comandi forniti da me, eseguiti dall'operatore) |
| **1** Preservazione | Manifest SHA256, backup cifrato esterno, restore su copia, esito nel diario | Basso | Installazione extbackup = modifica VPS: sì |
| **2** Audit apprendimento | Tracciare journal→memoria→prompt→gate in sola lettura; elenco dei campi realmente nei prompt | Nullo | No |
| **3** Schema dati | `brain_decision` v2 con `feature_snapshot`, `thesis_id`, versioni; `evidence_store`; test di non regressione dell'hash dei vecchi payload | Medio (tocca journal) | Sì (merge) |
| **4** Etichettatura | Job offline che collega `opportunity.py` alle candele e ai NO_TRADE; MFE/MAE/funding | Basso | PR draft |
| **5** Modello shadow | Training offline, registry, report, ECE/OOS; zero impatto sul decisore | Basso | No fino alla shadow live |
| **6** Brain Unico PAPER | Un wallet `brain`, DeepSeek + gate + exit; Falco SHORT come feature; Claude contingentato | Alto | **Sì, dopo fine gara + backup + posizioni gestite** |
| **7** Dashboard unica | 5 schede, `UI_ONLY` | Medio | Sì (deploy web) |
| **8** Promozione modello | Report, shadow, rollback, OK utente | Medio | Sì |

Dipendenza: 6 dopo la conclusione e archiviazione coerente della gara (21/11 18:03 + chiusura posizioni) e dopo l'audit di §3 (richiesto anche dal diario prima di riavviare il Brain storico).

## 7. Collaborazione ChatGPT Work ↔ Claude tramite GitHub

Già esistono `CLAUDE.md`/`AGENTS.md` (identici) e il ramo `diario`. Proposta di rinforzo, tutta additiva:

1. **Namespace dei rami per autore:** `claude/<area>-<AAAAMMGG>` e `chatgpt/<area>-<AAAAMMGG>` (oggi `work/*` mescola autori; si mantengono quelli esistenti). Nessuno scrive in un ramo dell'altro.
2. **Un solo autore per componente** (regola 9 già esistente) reso esplicito in `OWNERS.md` sul ramo `diario`, con tabella componente → autore → ramo → stato → data. Prima di toccare un componente, ci si "prenota" con un commit `[skip ci]` a quella tabella.
3. **Handoff come file, non chat:** ogni sessione termina con una voce `diario/AAAA-MM-GG_<tema>.md` più aggiornamento di `STATO.md` (già prassi) con tre campi fissi: *cosa è cambiato*, *cosa NON è stato toccato*, *prossimo passo e blocchi*.
4. **PR sempre draft**, titolo `[claude]` / `[chatgpt]`, descrizione con checklist: dati toccati, test eseguiti (comando + esito), rischi, rollback. Revisione incrociata: ciò che scrive Claude lo rivede ChatGPT e viceversa; il merge resta all'utente.
5. **Issue #113 come registro decisioni:** un commento per decisione, prefisso `DECISIONE:` o `RICHIESTA CONSENSO:`; gli agenti non agiscono su ciò che non è un commento dell'utente.
6. **Niente file di interfaccia in conflitto:** schemi condivisi (`schema_version`, `policy_version`) in `backend/v3/contracts/` modificabili solo con PR approvata; i due agenti lavorano su moduli separati che parlano tramite quei contratti.
7. **Sincronizzazione:** `git fetch --all` a inizio sessione, rebase sul proprio ramo, mai `--force`, mai commit su `main`. Un lock leggero: file `LOCK-<componente>.md` nel ramo `diario` (commit `[skip ci]`) con scadenza a 24 h.
8. **Segreti:** nessun segreto nel repo né negli allegati; il PDF utente `SuperBot_Brain_Report.pdf` va alla sessione Claude privata, non al repo.
9. **Divisione naturale del lavoro (suggerimento):** Claude: audit, schema dati, training/registry, test; ChatGPT Work: UI Samsung, documentazione per l'utente, revisione. Da confermare con l'utente.

## 8. Limiti di questo rapporto e domande aperte

- **Non verificato:** stato dei servizi, heartbeat, commit effettivamente in esecuzione, dimensioni reali degli storici, esistenza e contenuto dei backup sulla VPS. Tutto ciò che sopra riguarda la VPS deriva dal diario e dal codice, non da osservazione diretta.
- Ho esaminato soprattutto la PR #112 (HEAD `86288a3…`), non ogni ramo `work/*`; i 255 rami non sono stati letti uno per uno. Il rapporto sull'universo (27 simboli nel config) va confermato con lo snapshot di gara.
- Test non eseguiti (richiederebbero dipendenze e non erano nel perimetro): i numeri di test citati vengono dal diario.
- **Decisioni che servono a te:** (a) soglie minime di campione per shadow/promozione; (b) politica di Claude (quali eventi e quale tetto giornaliero); (c) se Falco SHORT debba restare solo feature o anche trigger di allarme; (d) permesso di fornirti comandi read-only da incollare in terminale operatore per la Fase 0 (nessun accesso diretto mio alla VPS).

## 9. Prossimo passo proposto

Fase 0 e Fase 2 (entrambe read-only): ti preparo uno script di inventario **solo lettura**, da eseguire tu in terminale operatore (`! ./inventory.sh`), che produce conteggi/hash senza leggere né stampare credenziali; e in parallelo l'audit journal→memoria→prompt→gate sul codice. Non procedo senza il tuo OK.

## 10. Decisioni dell'utente (Issue #113, commento del 19/11/2026 07:49)

1. Script di inventario read-only: autorizzata la **preparazione** (`ops/brain-unico/inventory.py`, testato su fixture). **Non** autorizzata l'esecuzione privilegiata sulla VPS né modifiche ACL/sudo/docker.
2. Soglie (proposte, non garanzie): >=300 esempi etichettati e verificati e >=20 giorni per un primo modello shadow solo offline; per *considerare* la promozione >=1000 esempi, >=45 giorni, OOS cronologico con embargo, baseline, calibrazione, EV netto, drawdown e approvazione esplicita.
3. Claude via API dal Brain: zero chiamate e zero budget finché Arena e audit continuano. Pilot event-driven con cap candidato 0,50 USD/giorno solo proposto, non attivato.
4. Falco SHORT: solo advisory (feature + spiegazione, eventuale avviso `trend_reversal/SHORT_conflict` non bloccante). Il Risk Manager conserva il veto.
5. PR draft di sola documentazione: sì, branch isolato, nessun merge/deploy.

Conseguenze sul piano: la Fase 6 resta bloccata fino a fine Arena e audit; il `Training Dataset Builder` (feature point-in-time con provenance, esiti dei NO_TRADE, MFE/MAE, funding, split temporali) è la prima implementazione dopo l'audit; lo scoreboard LLM non va presentato come addestramento.

## 11. Strumento allegato

`ops/brain-unico/inventory.py`: manifest read-only (byte, mtime, SHA256, righe e run distinti dei `.jsonl`, commit in esecuzione, file tracciati modificati). Non legge né stampa contenuti, salta file dal nome sensibile, non segue symlink, non apre SQLite salvo `--sqlite` su copia ferma, rifiuta di sovrascrivere. Test: `python3 ops/brain-unico/test_inventory.py` (5 test su fixture sintetiche).
