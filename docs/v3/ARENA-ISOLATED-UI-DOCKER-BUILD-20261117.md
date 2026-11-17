# AI Arena — Build UI isolata con Node.js in Docker (17 novembre 2026)

**Stato prima del build:** screenshot Termius 21:20 su VPS Singapore conferma `APP_ATTUALE=OK`, `NODE_DOCKER=ASSENTE`, `LOCKFILE=PRESENTE`. `node` e `npm` **non** installati sul sistema. La root Nginx attiva è `/opt/superbot-web/build`. Il codice Arena nello stage è fissato al commit `48dc07494345fe9d973b900b67cd094cec56e7e5`, con 149 test Python superati. Falco e Toro disattivati/archiviati, Brain storico rimane operativo.

**Preparazione ammessa:** generare una build statica della dashboard **in un percorso isolato**, non pubblicarla ancora. L'utente desidera utilizzare l'app Samsung esistente (probabilmente PWA); non creare link Chrome alternativi o sostituire il container attivo.

## Script

`deploy/scripts/arena-frontend-docker-isolated-build-20261117.sh` sul ramo draft PR #106.

- Richiede root, sorgente stage SHA bloccato, `frontend/{src,public,package.json,package-lock.json}`. Il lockfile è **presente sulla VPS ma non risultava tracciato al commit GitHub esaminato**: lo script verifica `packages[''].dependencies == package.json.dependencies` e lockfileVersion 2/3; in caso di differenza abortisce. Questa verifica NON è ancora un audit completo della dipendenza.
- Se manca l'immagine Docker ufficiale `node:20-bookworm-slim`, scarica l'immagine **solo dopo** la verifica lockfile. Usa Docker CLI e npm registry, quindi richiede rete per dipendenze; **non usa chiavi AI o Bitget**.
- Crea una nuova directory privata `/opt/superbot-arena-ui-builds/preview.XXXXXXXX`, copia soltanto sorgenti React, public, package.json e lockfile. Nessuna copia dei segreti dal server o dei dati dei portafogli.
- Lancia un container effimero senza `docker.sock`, con l'unico bind mount del nuovo workspace, `--cap-drop ALL`, `--security-opt no-new-privileges`, limiti risorse. Esegue `npm ci --no-audit --no-fund --prefer-offline` e `npm run build`.
- Flag: `REACT_APP_PREVIEW_READONLY=1`, `REACT_APP_BRAIN_ARENA_PREVIEW=1`, `REACT_APP_BRAIN_ARENA_SHADOW_API=0`, `REACT_APP_ARENA_MANUAL_CLOSE=0`, `REACT_APP_ARENA_EXISTING_CLOSE=0`. In questa fase nessun endpoint della nuova Arena né tre run PAPER esistono. Non spacciare per dati reali i segnaposto.
- Verifica output `build/index.html`, `build/static` e stampa SHA-256 dell'indice. NON aggiorna `/opt/superbot-web/build`, Nginx, container `superbot`, unità systemd, Brain o la PWA distribuita.

## Esecuzione e stop

1. Recuperare script da GitHub tramite **commit SHA del file**, verificare `bash -n` e lanciare solo sulla VPS Singapore.
2. Se appare `ARENA_UI_BUILD_LOCKFILE_MATCH=TRUE`, poi `ARENA_UI_BUILD_RESULT=SUCCESS_ISOLATED_BUILD_ONLY`, la compilazione è riuscita. Altrimenti **non correggere a mano** le dipendenze; riferire l'errore e fermarsi.
3. In caso di build riuscita, verificare in anteprima isolata che UI e API non confondano Brain storico con DeepSeek Arena, e che `not_started` e PnL vuoti siano resi onestamente. La pubblicazione della PWA è una successiva procedura con backup/rollback e test autenticazione reali, distinta dall'attuale build.

**Nessun deploy/live, approvazione del budget o inizio 14 giorni autorizzato da questo script.**