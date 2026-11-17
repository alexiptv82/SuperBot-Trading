# AI Arena — Build UI isolata con Node.js in Docker (17 novembre 2026)

**Stato prima del build:** screenshot Termius 21:20 su VPS Singapore conferma `APP_ATTUALE=OK`, `NODE_DOCKER=ASSENTE`, **`LOCKFILE=ASSENTE`**. La lettura precedente del risultato era sbagliata. Il primo tentativo di compilazione, alle 21:31, si è fermato con `ARENA_UI_BUILD_REFUSED=MISSING_package-lock.json`, senza modificare la dashboard. `node` e `npm` **non** installati sul sistema. La root Nginx attiva è `/opt/superbot-web/build`. Il codice Arena nello stage è fissato al commit `48dc07494345fe9d973b900b67cd094cec56e7e5`, con 149 test Python superati. Falco e Toro disattivati/archiviati, Brain storico rimane operativo.

**Preparazione ammessa:** generare una build statica della dashboard **in un percorso isolato**, non pubblicarla ancora. L'utente desidera utilizzare l'app Samsung esistente (probabilmente PWA); non creare link Chrome alternativi o sostituire il container attivo.

## Script

`deploy/scripts/arena-frontend-docker-isolated-build-20261117.sh` sul ramo draft PR #106.

- Richiede root e sorgente stage SHA bloccato, `frontend/{src,public,package.json}`. Il `package-lock.json` è assente sia nella verifica VPS sia nel commit GitHub esaminato. La versione corretta genera il lockfile **solo dentro la nuova directory temporanea** usando `npm install --package-lock-only --ignore-scripts --no-audit --no-fund --legacy-peer-deps` nel container, verifica l'allineamento delle dipendenze e poi esegue `npm ci --legacy-peer-deps`. L'installazione richiede rete npm e può fallire senza toccare la dashboard. Per avere build riproducibili in futuro, il lockfile generato andrà revisionato e versionato, non aggiunto alle directory operative di nascosto.
- Se manca l'immagine Docker ufficiale `node:20-bookworm-slim`, scarica l'immagine **solo dopo** la verifica lockfile. Usa Docker CLI e npm registry, quindi richiede rete per dipendenze; **non usa chiavi AI o Bitget**.
- Crea una nuova directory privata `/opt/superbot-arena-ui-builds/preview.XXXXXXXX`, copia soltanto sorgenti React, public, package.json e lockfile. Nessuna copia dei segreti dal server o dei dati dei portafogli.
- Lancia un container effimero senza `docker.sock`, con l'unico bind mount del nuovo workspace, `--cap-drop ALL`, `--security-opt no-new-privileges`, limiti risorse. Esegue `npm ci --no-audit --no-fund --prefer-offline` e `npm run build`.
- Flag: `REACT_APP_PREVIEW_READONLY=1`, `REACT_APP_BRAIN_ARENA_PREVIEW=1`, `REACT_APP_BRAIN_ARENA_SHADOW_API=0`, `REACT_APP_ARENA_MANUAL_CLOSE=0`, `REACT_APP_ARENA_EXISTING_CLOSE=0`. In questa fase nessun endpoint della nuova Arena né tre run PAPER esistono. Non spacciare per dati reali i segnaposto.
- Verifica output `build/index.html`, `build/static` e stampa SHA-256 dell'indice. NON aggiorna `/opt/superbot-web/build`, Nginx, container `superbot`, unità systemd, Brain o la PWA distribuita.

## Esecuzione e stop

1. Recuperare script da GitHub tramite **commit SHA del file**, verificare `bash -n` e lanciare solo sulla VPS Singapore.
2. Se appare `ARENA_UI_BUILD_LOCKFILE_SOURCE=GENERATE_IN_ISOLATED_WORKSPACE`, poi `ARENA_UI_BUILD_LOCKFILE_MATCH=TRUE` e infine `ARENA_UI_BUILD_RESULT=SUCCESS_ISOLATED_BUILD_ONLY`, la compilazione è riuscita. Altrimenti **non correggere a mano** le dipendenze; riferire l'errore e fermarsi.
3. In caso di build riuscita, verificare in anteprima isolata che UI e API non confondano Brain storico con DeepSeek Arena, e che `not_started` e PnL vuoti siano resi onestamente. La pubblicazione della PWA è una successiva procedura con backup/rollback e test autenticazione reali, distinta dall'attuale build.

**Nessun deploy/live, approvazione del budget o inizio 14 giorni autorizzato da questo script.**
**Fix del primo blocco:** script aggiornato al commit `cbe854b79e503f77caa037f47efde3daf3201547`. Non usare la vecchia versione al commit `9badd1fb`.
