# SUPERBOT — MASTER HANDOVER E ROADMAP OPERATIVA

**Data:** 19/11/2026 sera · **Autore:** Claude Code (responsabile operativo dello sviluppo dal 19/11/2026)
**Metodo:** repository GitHub (rami, PR aperte, Issue #113/#124, diario fino a `324a17a`), codice letto e test eseguiti offline su worktree isolati, osservazione VPS **solo come utente non-root** (nessun sudo, nessun journal/DB/segreto letto, nessun servizio toccato).

Legenda: **[V]** verificato da me ora · **[R]** riferito da altri, non riverificato · **[N]** non verificabile con i miei permessi.

---

## 1. Stato reale del progetto

- Il sistema reale non è su `main`. Il V3 (Brain, Arena, rischio, uscite) vive in una **catena di rami `work/*`** e in PR draft impilate (#86→#110→#112). La base di integrazione usata per il Brain Unico è `work/brain-exit-observability-20261113` @ `33a0de7` [V].
- Il Brain Unico **non esiste ancora come sistema in esecuzione**. Esistono componenti: motore di rischio, freno giornaliero, ricontrollo dopo l'AI, scrittore singolo, scoreboard EV, etichettatura NO_TRADE (V3), più quattro filoni di laboratorio:
  - Fase 0 e conservazione (#114–#117);
  - Dataset Builder (#118);
  - Guardian ed E0 (#119);
  - snapshot v2 (#122).
- L'apprendimento oggi è **descrittivo** (scoreboard). Nessun modello addestrato. Le feature al momento della decisione non vengono salvate dal runtime V3. La #122 le rende registrabili, ma non è collegata al runner.

## 2. Stato VPS verificato (non-root)

| Elemento | Stato | |
|---|---|---|
| `superbot-arena-runner@{deepseek,qwen,minimax}` | attivi | [V] |
| `superbot-arena-exit@{deepseek,qwen,minimax}`, `superbot-arena-close-bridge` | attivi | [V] |
| Codice Arena `/opt/superbot-arena-stage` | commit `3dd6aa5` (ramo `work/arena-72h-18usd-budget-20261118`, PR #110), albero pulito salvo `.venv` | [V] |
| `superbot-v3-paper-brain-exit` (uscite Brain V3), `superbot-v3-paper-single-close-bridge`, `superbot-v3-paper-telegram-alert-relay` | attivi | [V] |
| Runner del Brain V3 (nuove aperture) | **non in esecuzione** | [V] |
| Codice Brain V3 `/opt/superbot-v3-rc70-stage`, relay | directory root 0700: commit non leggibile | [N] |
| `superbot-extbackup.timer` | **attivo**; ultimo avvio 19/11 03:21 UTC esito `success`; prossimo 20/11 03:20 UTC | [V] |
| App web (`uvicorn backend.server:app` + nginx, in container) | attiva | [V] |

**Incongruenza da chiarire:** il diario riporta "extbackup `3dc2116` non installato", ma sulla VPS il timer esiste e gira con successo. Non posso verificare quale versione sia installata, cosa copi, né se esista un ripristino fuori host [N]. Finché non è verificato, **il backup esterno non va considerato certificato**.

## 3. Implementazioni completate (in PR draft, nessuna in produzione)

| PR | Contenuto | Test |
|---|---|---|
| #114–#116 | audit, inventario, procedura Fase 0, bundle sealed | [R] PASS riferiti |
| #117 | finalizzazione Arena + audit rischio | [R] |
| #118 `0833c0d` | Dataset Builder v0.3: legame per simbolo, attestazione v2 con ancora esterna | 103 test, mutazioni [V nella sessione precedente] |
| #119 `d6ed73d` | proposta Guardian, simulazione sintetica, strumento E0 | 18 test, 23/23 mutazioni [V prec.] |
| #121 `5b7403a` | prezzi mancanti o invalidi ⇒ fail-closed nel freno giornaliero | **[V] 8/8; suite pertinente 1117 pass, 0 fail** |
| **nuovo** `claude/brain-unico-daily-loss-latch-p0-20261119` `ddd1308` | **correzione P0 #124** (vedi §9) | **[V] 32 nuovi test, suite V3 completa 5063 pass, 0 fail** |
| #122 `513448e` | evento `brain_decision_snapshot_v2` append-only, non collegato al runner | **[V] 11 test, 13 sottotest pass** |
| #123 `c51c752` | laboratorio SHADOW costi LLM (Grok/Cursor) | [R] |
| #120 `f4f7457` | router LLM gratuito | [R]; **non conforme** (vedi §5) |

**Correzione importante sulla verifica precedente:** i "5 fallimenti preesistenti" di `test_v3_rc84_import_paths` erano **ambientali**: `numpy` mancava nel mio ambiente di test. Con le dipendenze installate passano. **Non ci sono fallimenti preesistenti** nella suite pertinente.

## 4. Implementazioni incomplete

1. Collegamento #122 → runner (le feature non vengono ancora scritte in esecuzione).
2. Collegamento #122 → #118: il builder non legge gli eventi snapshot v2.
3. Copie Fase 0 reali, ancora esterna dell'operatore, lettura delle copie root-only: serve consenso.
4. Misura E0 sui dati reali.
5. Contabilità mark-to-market verificabile per dashboard e Guardian.
6. Profilo di rischio v2:
   - la leva minima 20× vincola lo stop;
   - il 50% giornaliero è troppo largo.

   Proposta pronta; nessuna modifica alle soglie attive.
7. Anti-reingresso / `thesis_id`; filtro EV; Guardian: solo progettati.
8. Ruolo di Falco come segnale consultivo nel Brain Unico; ruolo di Claude come consulente selettivo con budget: da collegare.
9. App Samsung con un solo portafoglio Brain e motivo della chiusura manuale.
10. Universo top 25 per capitalizzazione + oro e argento, versionato: oggi la configurazione Arena ha 27 simboli fissi, senza versione né criterio di ranking verificato.

## 5. P0 e regressioni

| ID | Stato |
|---|---|
| **#124 latch giornaliero** | **corretto su branch, da revisionare** (§9). NO-GO deploy finché la PR non è revisionata |
| #121 prezzi mancanti | corretto, verificato verde; resta draft |
| **#120 non conforme all'architettura** | router `free_router` **primario** con DeepSeek come fallback e `auto:smart`; modifica `brain_f2/engine.py`, `deepseek_l5.py`, `wiring.py`. È contrario a "DeepSeek decisore principale, LLM economici in shadow". **Non integrabile così**; tocca anche `wiring.py`, che la #121 e la P0 modificano (conflitto da risolvere in integrazione) |
| Rischio di leakage nella #122 | il journal **non impone** l'ordine temporale (`occurred_at_ms` libero). Uno snapshot scritto dopo l'esito, con l'istante della decisione, sarebbe indistinguibile. La regola di collegamento deve usare il **numero di sequenza del journal** (vedi §8, fase B) |
| Backup esterno | incongruenza tra diario e VPS (§2): da verificare |

## 6. Dipendenze fra le PR

```
main ── #114 ── #115 ── #116 ── #117          (Fase 0 / Arena; ops/, documentazione)
main ── #118 (Dataset Builder)    main ── #119 (Guardian/E0)
work/... #86→…→#110 (Arena, codice in esecuzione sulla VPS) → #112 (cutover web)
work/brain-exit-observability (33a0de7) ─┬─ #121 ── P0 #124 (nuovo branch, impilato su #121)
                                         ├─ #122 (snapshot v2)
                                         ├─ #120 (router: conflitto su wiring.py, da riallineare)
                                         └─ #123 (lab costi, isolato)
```

#118 e #119 si basano su `main`, mentre il codice V3 che dovranno leggere sta sulla base `work/brain-exit-observability`. In integrazione vanno portati sulla stessa base. Non serve rifarli: il loro codice sta in `ops/brain-unico/`, separato.

## 7. Componenti operativi e sperimentali

- **Operativi sulla VPS** [V]:
  - Arena (3 runner + 3 servizi uscite);
  - servizio uscite del Brain V3 e close bridge;
  - relay Telegram;
  - app web;
  - timer extbackup.
- **Sperimentali, solo in PR:** tutto il Brain Unico (#118, #119, #121, #122, P0 #124), router e laboratorio LLM (#120, #123), Fase 0 (#114–#117).
- **Fermo:** runner di apertura del Brain V3.

## 8. Piano di completamento del Brain Unico

| Fase | Contenuto | Criterio di accettazione |
|---|---|---|
| **A. Rischio di base** | #121 + P0 #124 revisionate; profilo di rischio v2 proposto (leva come risultato, limite di sessione in R, MTM fail-closed) | test verdi sulla base di integrazione; nessuna riapertura in nessuno scenario #124; soglie cambiate solo con tua decisione |
| **B. Memoria verificabile** | #122 collegata al runner (scrittura dello snapshot nello stesso ciclo, **prima** dell'apertura); il builder #118 legge `brain_decision_snapshot_v2` | regole di ammissione: (1) `seq` dello snapshot < `seq` del primo evento della posizione (`paper_open`) e di ogni evento con istante successivo alla decisione; (2) `feature_asof ≤ captured_at ≤ decision_ts`; (3) legame per `decision_event_id` + hash; (4) simbolo uguale; (5) fonte attestata (ancora esterna) per i dati storici. Test anti-leakage con snapshot retrodatato ⇒ escluso |
| **C. Storici** | copie Fase 0 (con consenso), ancora esterna, builder, E0 | builder deterministico su copie attestate; conteggi riconciliati; nessun record cancellato |
| **D. Decisione** | DeepSeek decisore; Falco come feature; filtro EV dallo scoreboard con budget esplorativo; anti-reingresso con `thesis_id`; Claude consulente su casi ambigui con budget a zero finché non approvato | replay causale vs baseline; nessuna probabilità LLM nel sizing |
| **E. Guardian** | politica C (scala del budget in R) dopo E0; B e A come bracci ombra | effetto attribuibile, una modifica alla volta |
| **F. App** | un portafoglio Brain, MTM con freschezza, motivo della chiusura manuale, archivi in consultazione | autenticazione/WebAuthn/Telegram invariati; test frontend |
| **G. Release candidate** | integrazione su un'unica base, backup verificato, rollback, nessun P0 | un solo GO/NO-GO, poi PAPER finale integrato |
| **Modello** | LightGBM solo con ≥300 esempi ammessi / 20 giorni (shadow), ≥1000 / 45 giorni (valutazione) | split cronologico + embargo, calibrazione, EV netto, nessuna promozione automatica |

## 9. Primo intervento autonomo: eseguito

**P0 #124**, branch `claude/brain-unico-daily-loss-latch-p0-20261119` @ `ddd130847ae6ccdd2300b4d4ceba1ccde7e2a75e`, impilato sulla #121.

- **Principio:** il fatto che ora la perdita sia sotto soglia non prova nulla. Lo stato v2 registra fino a quale istante la perdita è stata controllata e scritta su disco.
- **Senza continuità dimostrata (≤ 3 min):** si ricostruisce la giornata da journal V3 e candele 1m, con la stessa formula del controllo vivo minuto per minuto.
- **Ricostruzione ≥ stop:** blocco `loss` fino a mezzanotte UTC, mai rimosso prima.
- **Ricostruzione impossibile:** blocco `unverified` sulle sole nuove aperture, rimosso solo da una ricostruzione successiva riuscita.
- **Primo avvio di un run nuovo:** journal vuoto, quindi verificabile senza flag.
- **Prima di ogni apertura:** lo stato deve essere su disco (fsync); se il disco rifiuta la scrittura, l'apertura è negata.
- **Prove:**
  - scenari corrotto / cancellato / scrittura fallita: baseline `ok` (il bug) ⇒ ora `halt`;
  - 32 nuovi test;
  - suite V3 completa 5063 pass;
  - mutazioni 14/15 + wiring (l'unica sopravvissuta è una guardia difensiva equivalente).
- **Uscite, soglie 35/50% e pavimento 450 USDT:** invariati.
- **PR:** il connettore GitHub restituisce 403 su creazione PR e commenti. Il branch è pubblicato; la PR draft si apre da `https://github.com/alexiptv82/SuperBot-Trading/pull/new/claude/brain-unico-daily-loss-latch-p0-20261119` con base `chatgpt/brain-unico-daily-loss-failclosed-20261119`. La descrizione pronta è nella voce `diario/2026-11-19_claude-p0-124-latch.md`.

**Prossimi interventi autonomi, in ordine:**
1. fase B (regole di collegamento #122 → #118 con test anti-leakage);
2. riallineamento proposto della #120 (DeepSeek primario, economici in shadow);
3. proposta del profilo di rischio v2;
4. porting di #118 e #119 sulla base di integrazione.

## 10. Operazioni che richiedono la tua autorizzazione

1. **Fase 0 reale:** copie degli storici (lettura di journal e DB root-only) e registrazione dell'ancora esterna.
2. **Merge** di #121 / P0 #124 / altre nel ramo di integrazione o nei rami operativi.
3. **Deploy** sulla VPS, riavvio o arresto di servizi, inclusa la **conclusione dell'Arena**: prima servono stato posizioni, backup coerente, checkpoint e procedura #117.
4. **Modifica delle soglie** (35/50%, leva minima 20×, rischio per trade) e dei parametri dei bot attivi.
5. **Spesa API:** Claude consulente nel Brain, DeepSeek oltre il budget, FreeLLMAPI.
6. **Verifica del backup esterno:** lettura della configurazione extbackup e prova di ripristino.
7. **Accesso GitHub per aprire e commentare PR** in autonomia (oggi 403): per esempio un token fine-grained limitato al repository, oppure continuare con l'apertura manuale.
8. LIVE, segreti, permessi VPS: fuori discussione senza decisione esplicita.

**Accessi mancanti dichiarati:**
- commit e codice di `/opt/superbot-v3-rc70-stage` e del relay (root 0700);
- contenuto del backup esterno;
- journal reali;
- report Grok (non presente nel repository o nelle sessioni);
- `AGENTS.md`, presente nella directory Arena, non confrontato con la base di integrazione.
