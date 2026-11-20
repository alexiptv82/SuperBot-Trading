# Registro del ramo di integrazione `integration/brain-unico-20261119`

**Autorizzazione:** `AUTORIZZAZIONI.md` § 2 (merge solo in questo ramo, con condizioni). Base: `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`. **Punta attuale: `dd414831…`** (pubblicata; aggiornata dopo i passi 6–8). Il ramo non è usato da alcuna procedura (nato il 19/11/2026; nessun riferimento nel codice; nessun workflow con trigger push/PR su di esso, analisi di 90 workflow). Nessun deploy, nessuna modifica a `main` o a rami operativi, nessuna soglia modificata.

**Gate (identico a ogni passo):** suite V3 completa (80+ file, offline, proxy verso porta chiusa, utente non-root) prima e dopo; più i test di `ops/brain-unico` quando si integra `ops/`. Ambiente: pytest, fastapi, httpx, numpy, pandas in un venv fuori dal repository. Regola di accettazione: test dopo = test prima + test nuovi della PR, 0 falliti.

| # | Integrazione | Commit nel ramo | Suite V3 prima → dopo | Note |
|---|---|---|---|---|
| 0 | baseline `33a0de7` | — | **5023** passed, 1 skipped | rieseguita il 19/11 prima di qualunque merge |
| 1 | PR #121 `5b7403a` (prezzi mancanti fail-closed) | merge `b12189cb` | 5023 → **5031** (+8) | 0 falliti |
| 2 | P0 #124 `ddd1308` (latch con continuità dimostrata) | merge `46e18096` | 5031 → **5063** (+32) | 0 falliti; nessun conflitto |
| 3 | #118 Dataset Builder + fase B (5 commit propri) | cherry-pick `1829801d`…`2c133451` | 5063 → 5063 | solo `ops/` e `docs/`; test del builder **134 OK**; albero identico alla catena originale |
| 4 | #119 Guardian/E0 (2 commit propri) | cherry-pick `2a6f62ec`, `3e5d8fc3` | 5063 → 5063 | E0 **18 OK**; albero identico |
| 5 | #122 adattatore snapshot + mio controllo di ordine `2e0662a` | merge `0b86f18b` | 5063 → **5087** (+24) | adattatore inerte: nessun riferimento dal runtime |

| 6 | P0 #124 seconda correzione `a177729` (ricostruzione obbligatoria dopo riavvio) | merge `cc35f532` | 5087 → **5095** (+8) | scenario 10:00/10:01/10:02 del proprietario |
| 7 | #123 laboratorio LLM (Grok `c51c752`) + input equivalente (Claude `6d61943`) | merge (punta `8fc2139b`) | 5095 → **5120** (+25) | separato dal trading: nessun import dal runtime, `may_open` sempre falso, nessun provider |
| 8 | prova di equivalenza con `context_hash` (`4d24663`) | merge `dd414831` | 5120 → **5121** (+1) | |
| 9 | traccia causale delle decisioni (snapshot v2 cablato nel ciclo), 20/11 | commit diretto `a5a92040` | 5121 → **5147** (+26) | 0 falliti; builder 134 OK; mutazioni 10/10; rollback: `git revert a5a92040` (commit singolo). Dettagli: `2026-11-20_claude-traccia-decisioni.md` |

### Provenienza dell'autorizzazione (risposta al checkpoint ChatGPT 20:49)
Il consenso ai merge in questo ramo è stato dato dal proprietario **direttamente nella sessione Claude Code** (link di sessione nei trailer dei commit), in due messaggi del 19/11/2026: il primo autorizza i merge nel solo `integration/brain-unico-20261119` con le condizioni del § 2; il successivo lo riconferma («Continua autonomamente con lo sviluppo e i test sul ramo di integrazione autorizzato», «Puoi integrare nel ramo di laboratorio autorizzato i componenti della PR #123»). ChatGPT non vede quella sessione: il conflitto è di visibilità, non di contenuto. **Richiesta al proprietario:** una riga di conferma in un canale leggibile da entrambi (es. commento nella Issue #113) chiude la questione; Claude non può scriverlo (403).

### Perché cherry-pick e non merge per #118/#119
I rami di #118 e #119 nascono da `main`, che ha 95 commit in più rispetto al ramo di integrazione, tra cui **36 file di workflow e 35 file di trigger di deploy**. Un merge li avrebbe portati nel ramo, violando "separato dal sistema operativo" e "nessun workflow operativo". I cherry-pick (`-x`, con riferimento al commit originale) portano solo i commit propri delle PR, che toccano soltanto `docs/v3` e `ops/brain-unico/`. Verificato: albero identico a quello delle catene originali.

### Rollback (dimostrato, non solo dichiarato)
- Revert `-m 1` del merge P0 ⇒ albero identico al punto dopo #121; revert anche di #121 ⇒ albero identico a `33a0de7`.
- Revert del merge dell'adattatore + dei 7 cherry-pick ⇒ albero identico a `46e18096`.

### Componenti non integrati, con motivo
| PR | Stato | Motivo |
|---|---|---|
| #120 router LLM | prova di merge: **nessun conflitto, suite 5105 OK** | non conforme alla policy (vedi `…-requisiti-pr120.md`); lavoro di Grok in corso |
| #114–#117 Fase 0 | no | procedure per l'operatore con root; non servono al ramo di sviluppo |
| #112 / #110 Arena | no | codice dell'Arena in esecuzione sulla VPS (`3dd6aa5`): fuori dal ramo di integrazione |

### Ambiente
Il clone locale di lavoro era **shallow**: l'ho completato (`fetch --unshallow`, sola lettura) quando i merge-base risultavano vuoti. Ricontrollata con la storia completa la relazione con l'Arena: `3dd6aa5` non è antenato della base e viceversa (punto comune `0e29a73`).
