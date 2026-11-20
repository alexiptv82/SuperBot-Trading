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
| 10 | copertura solo su collegamenti validi, istanti distinti, cattura prima del modello, letture indicizzate | commit `14f42c40` | 5147 → **5184** (+37) | regola canonica allineata al Dataset Builder; mutazioni 16/16 |
| 11 | validazione indipendente delle feature degli snapshot (builder) | commit `d63e31a8` | 5184 → **5205** (+21) | builder 134 OK; mutazioni 14/14 |
| 12 | `thesis_id` e anti-reingresso in **osservazione** | commit `1193ffaa` | 5205 → **5224** (+19) | stessa definizione di E0 (test incrociato); mutazioni 12/13 (1 equivalente) |
| 13 | etichette degli esiti di mercato per il laboratorio LLM | commit `5c2edfca` | 5224 → **5235** (+11) | mutazioni 10/10; il messaggio di commit dice 13 test: sono 11 |
| 14 | integrità e provenienza verificabile degli archivi di candele (separate) | commit `9acd96d7` | 5235 → **5238** | builder 153 OK; mutazioni 15/15 |
| 15 | istante decisionale per simbolo (opzione di laboratorio, cablaggio invariato) | commit `1aadf4ec` | 5238 → **5250** | mutazioni 10/10 |
| 16 | etichette LLM: osservati separati dai controfattuali, NO_TRADE relative, incertezza | commit `0453433e` | **1 FALLITO**, 5255 passati | **regressione pubblicata per errore**: un commento citava un componente operativo, violando il test di isolamento del laboratorio; la pubblicazione non era condizionata all'esito della suite |
| 17 | correzione della regressione | commit `24b18d08` | **5256**, 0 falliti | ramo rimasto rosso per circa 5 minuti; da qui in poi si pubblica solo se suite e test del builder sono verdi |
| 18 | procedura di acquisizione delle candele (preparata, NON eseguita) | commit `3f1c5b9f` | 5256 → **5264** | 8 test offline con finto endpoint |
| 19 | limiti rigidi dell'acquisizione (350 tentativi HTTP, 100 MB, 47 giorni, niente date future) | commit `a3967b51` | 5264 → **5277** | gate di pubblicazione collaudato: bloccata una suite reale con un test-sonda fallito; mutazioni 14/14 |
| 20 | derivazione delle candele identica al runtime + diagnostica di interruzione | commit `2c07f7a9` | 5277 → **5280** | dopo l'interruzione dell'unica acquisizione autorizzata |
| 21 | deduplicazione per slot anche in modalità cycle (difetto di duplicazione corretto) | commit `bd4f2880` | 5280 → **5286** | runner cablato passa lo slot; mutazioni 3/3 |
| 22 | stato verificato / non verificato / escluso nel Dataset Builder; verifiche per simbolo (sidecar, costi AI) | commit `b71e706f` | 5286 → **5289** | builder 157 |
| 23 | memoria e apprendimento nell'app SuperBot (endpoint + sezioni Overview) | commit locale `c768a6f4` | **bloccato dal gate** (1 fallito: inventario rotte RC84) | non pubblicato da solo |
| 24 | inventario delle rotte aggiornato con la sola lettura `/brain/memory` | commit `8e03235d` | **5298**, 0 falliti | builder 157, Jest 129/129, build di produzione OK; pubblicati insieme 23+24 |

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
