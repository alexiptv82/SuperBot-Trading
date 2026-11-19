# Claude — Proposta di ramo di integrazione (nessun merge eseguito)

**Data:** 19/11/2026 · I merge restano **non autorizzati** (vedi `AUTORIZZAZIONI.md` § 2). Questa è la comunicazione del nome del ramo e dell'esito dei controlli richiesti dal proprietario.

## Ramo proposto

**`integration/brain-unico-20261119`** — nuovo, creato al commit `33a0de73a9903ba1ff76326aa4cb7c688a1e4aca`, lo stesso su cui poggiano oggi #120–#123. Sul remoto è un semplice puntatore a quel commit: nessun codice nuovo.

### Perché non `work/brain-exit-observability-20261113`

Era il candidato naturale (base delle PR #120–#123). Non l'ho scelto perché **non posso dimostrare che la VPS non lo usi**: il codice del Brain V3 installato sta in `/opt/superbot-v3-rc70-stage`, cartella root 0700, e il suo commit non è leggibile da me. Il nome del ramo e i commit recenti ("guarded Brain PAPER-only unpause", "install… not deployed") sono quelli di un ramo di preparazione di rilascio. Un ramo che non esisteva prima di oggi non può essere usato da nessun servizio.

## Esito dei cinque controlli

| Controllo | Esito |
|---|---|
| 1. Non usato dalla VPS operativa | **VERIFICATO per costruzione**: il ramo è nato oggi e nessun servizio, timer o script punta a un ramo con questo nome. Il codice Arena in esecuzione è `3dd6aa5`, non antenato di questa base (verificato). Il commit del Brain V3 installato resta non leggibile. |
| 2. Non attiva deploy o modifiche ai servizi | **VERIFICATO per i push**: nessun deploy parte da un push o da una PR su questo ramo. Esistono workflow che installano o fermano servizi sulla VPS (es. `v3-rc70-install-exit-only-units`, `v3-stop-paper-workers`), ma partono **solo con avvio manuale** da una persona |
| 3. Non collegato a workflow operativi | **VERIFICATO** analizzando in modo strutturato tutti i **90 workflow**: nessuno ha trigger `push`, `pull_request`, `create` o `delete` che corrisponda a `integration/*` o al ramo base. Restano solo `workflow_dispatch` (avvio manuale, scelto da una persona su un ramo a sua scelta) e un job pianificato (`sg-extbackup-watch`, che gira dal ramo predefinito, non da questo) |
| 4. Test pertinenti per ogni modifica | **DEFINITO**: gate prima di ogni merge = suite V3 completa (80 file) offline: `pytest $(ls backend/tests/test_v3*.py; git ls-files 'backend/v3/*test_*.py')`, senza rete, con `numpy`, `pandas`, `fastapi`, `httpx`. **Base `33a0de7`: 5023 passed, 1 skipped.** Un merge è ammesso solo se il risultato è base + test nuovi della PR, senza falliti. Per #121 + P0 atteso: 5063 (verificato sul branch P0) |
| 5. Ritorno allo stato precedente | **DEFINITO**: merge sempre con `--no-ff` e `git revert -m 1` come rollback; base registrata sopra (`33a0de7`); nessun force push (regola 8). Posso aggiungere un tag di base su richiesta |

## Limiti dichiarati

- Non posso impostare la **protezione del ramo** su GitHub (nessun permesso di amministrazione). Il rispetto delle regole sarà quindi disciplina mia, e un'eventuale protezione richiede una tua azione nelle impostazioni.
- Poiché i workflow `workflow_dispatch` esistono su questo ramo, qualcuno potrebbe avviarne uno manualmente scegliendolo. Il rischio è identico a quello di qualsiasi altro ramo.
- Il ramo è creato ma **vuoto**: spostare le basi delle PR #120–#123 / #121 / P0 su di esso richiede la modifica della base su GitHub, che oggi non posso fare (403). Sono in ogni caso basate sullo stesso commit, quindi il merge in questo ramo sarebbe un avanzamento semplice.

## Ordine proposto dei merge (quando autorizzati)

1. #121 `5b7403a` → poi P0 #124 `ddd1308` (stesso file, impilate).
2. #122 `513448e`, dopo il collegamento con il builder (fase B).
3. #123 `c51c752` (laboratorio, isolato).
4. **#120 non** nella forma attuale (non conforme all'architettura; vedi handover).

**Decisione richiesta:** vuoi autorizzare merge `--no-ff` nel solo `integration/brain-unico-20261119`, con il gate sopra, fino a nuova comunicazione?
