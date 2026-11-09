# RC84 — proposta di pipeline GitHub Actions di SOLA VERIFICA (da revisionare)

**Stato: proposta. NON è un workflow attivo.** Questo file è in `docs/v3/` e il YAML è dentro un blocco di codice Markdown: GitHub
Actions legge solo `.github/workflows/`, quindi nulla qui può partire. Nessun workflow è stato creato, avviato o richiamato.
Base: PR #80 Draft, `10ac0cce626716ee97983319f23cfb538b377ce1`.

## 1. Rischio individuato prima di tutto: `backend/tests/test_superbot.py`

Il file contiene 9 test di **integrazione** verso un server in esecuzione. Se `REACT_APP_BACKEND_URL` era impostata, venivano eseguiti
davvero: tra le richieste c'è **`POST /api/bot/start`** (avvia il bot) e un login con una password fissa scritta nel repository.
Il solo `skipif(not BASE_URL)` non era una barriera: una variabile ereditata (frontend, staging, VPS) li avrebbe fatti partire.

Correzione (solo test, nessun codice applicativo):
- `backend/tests/conftest.py` (nuovo): marker `integration` registrato; **ogni test `integration` viene SALTATO** salvo opt-in esplicito
  `SUPERBOT_ALLOW_INTEGRATION=1` **e** `REACT_APP_BACKEND_URL` con host `127.0.0.1`, `localhost` o `::1` (server effimero locale).
  Host non locali, `0.0.0.0`, schemi diversi da http/https, trucchi come `127.0.0.1.evil.example` o `user@evil/127.0.0.1` sono rifiutati.
- `backend/tests/test_superbot.py`: seconda barriera in codice (le chiamate passano da un wrapper che rifiuta prima di inviare senza opt-in);
  **password statica rimossa** dal file: il login di successo usa `SUPERBOT_TEST_PASSWORD` dall'ambiente (se manca, il test è saltato).
- **Wrapper HTTP rafforzato** (revisione ChatGPT #6747209165): oltre all'opt-in, controlla l'**URL effettivo** di ogni richiesta (stesso schema/host/porta di
  `REACT_APP_BACKEND_URL`; `localhost` ≠ `127.0.0.1`, altra porta, altro schema, stringa vuota o non-stringa ⇒ rifiutato prima di inviare); **nessun redirect
  seguito** (`allow_redirects=False`; un 3xx è un errore e non parte alcuna seconda richiesta); **nessun proxy ereditato** (`trust_env=False`, `proxies` del chiamante
  ignorati); **timeout** su ogni richiesta: default 10 s, e prima di inviare viene rifiutato qualunque valore nullo (attesa infinita), non numerico, booleano, tupla, non finito (`nan`/`inf`), zero, negativo o superiore a 30 s.
- `backend/tests/test_ci_integration_guard.py` (nuovo, 61 test): un finto server su `127.0.0.1` **conta ogni richiesta**. Sottoprocessi pytest
  selezionano `test_superbot.py` con l'URL del finto server o con `http://backend.invalid:9` / `https://staging.example.org`:
  senza opt-in **0 richieste, 0 POST, 9 skipped**; con `-m "not integration"` 9 deselected; opt-in con host non locale rifiutato; opt-in senza URL
  inerte. In più, test in-process con un finto server che risponde `302` verso `sentinel.invalid`, `https://example.org`, un'altra porta locale e un URL relativo allo schema:
  una spia su `HTTPAdapter.send` registra ogni richiesta (e non apre mai connessioni fuori dal server finto): con il wrapper **solo la richiesta al server finto**,
  nessuna seconda richiesta; un controllo con una sessione `requests` normale mostra invece che il redirect verso la sentinella **partirebbe**. Stessa prova per i
  proxy ereditati (variabili `HTTP(S)_PROXY` verso un secondo finto server: il controllo li usa, il wrapper no) e per il timeout. Con il wrapper precedente 14 di
  questi test falliscono. Un **controllo positivo** (opt-in locale) prova che il contatore vede `GET /api/health` e `POST /api/bot/start`: senza questo "zero richieste"
  non dimostrerebbe nulla. Mutazione: neutralizzando le due barriere, 4 test falliscono (poi ripristinato).

La password di bootstrap resta altrove nel repository (`backend/auth.py`, test di autenticazione che verificano che sia *rifiutata* come nuova password,
`.github/workflows/staging-deploy.yml`): fuori da questo incarico, già segnalata come rischio nell'audit.

## 2. Pipeline proposta

`/.github/workflows/rc84-offline-verify.yml` (nome proposto; **non creato**):

```yaml
name: RC84 offline verification (TEST ONLY)

# SOLO VERIFICA. Nessun segreto, nessun ssh/scp/docker/systemctl, nessun deploy, nessun altro workflow richiamato.
# Test e build girano in un namespace di rete vuoto (nessuna richiesta esterna possibile, nemmeno verso Bitget).
# Se il namespace non funziona il job FALLISCE: non esiste alcun ripiego che esegua i test con la rete aperta.
on:
  workflow_dispatch:
    inputs:
      expected_sha:
        description: "SHA atteso del checkout (facoltativo): il job fallisce se non coincide"
        required: false
        type: string
  push:
    branches: [cursor/rc84-running-stop-health-telegram-20261108]
    paths: ['.github/workflows/rc84-offline-verify.yml']

permissions:
  contents: read

concurrency:
  group: rc84-offline-verify-${{ github.ref }}
  cancel-in-progress: true

env:
  # Mai un backend vero: la variabile e' vuota e l'integrazione e' disabilitata (vedi backend/tests/conftest.py).
  REACT_APP_BACKEND_URL: ''
  SUPERBOT_ALLOW_INTEGRATION: '0'
  DESK_MODE: paper
  TRADING_MODE: paper
  DESK_MACRO_FETCH: '0'
  PYTHONDONTWRITEBYTECODE: '1'
  # Percorsi ASSOLUTI (equivalenti a ".:backend"): non dipendono dalla cwd, che alcuni test cambiano temporaneamente.
  PYTHONPATH: ${{ github.workspace }}:${{ github.workspace }}/backend

jobs:
  backend:
    name: Backend offline (Python 3.11)
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      # Azioni ufficiali fissate a commit SHA (tag nel commento).
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          ref: ${{ github.sha }}
          persist-credentials: false
          fetch-depth: 1
      - name: Check the SHA under test
        env:
          EXPECTED_SHA: ${{ inputs.expected_sha }}
        run: |
          echo "SHA under test: $(git rev-parse HEAD)"
          if [ -n "$EXPECTED_SHA" ] && [ "$(git rev-parse HEAD)" != "$EXPECTED_SHA" ]; then
            echo "::error::checkout SHA differs from expected_sha"; exit 1
          fi
      - name: Preflight - empty network namespace (fail fast, no fallback)
        run: |
          set -euo pipefail
          command -v unshare >/dev/null || { echo "::error::unshare not available"; exit 1; }
          command -v ip >/dev/null || { echo "::error::ip (iproute2) not available"; exit 1; }
          sudo -n true || { echo "::error::passwordless sudo not available"; exit 1; }
          { uname -r; . /etc/os-release; echo "$PRETTY_NAME"; id -un; ip -V; unshare --version
            sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null || echo "apparmor userns sysctl: n/a"; } | sed 's/^/diag: /'
          cat > "$RUNNER_TEMP/netns_probe.py" <<'PY'
          import errno, socket, sys
          def fail(msg):
              print("::error::" + msg); sys.exit(1)
          ifaces = [l.split(":")[0].strip() for l in open("/proc/net/dev").read().splitlines()[2:]]
          if ifaces != ["lo"]:
              fail(f"namespace not isolated: interfaces={ifaces}")
          if open("/proc/net/route").read().splitlines()[1:]:
              fail("namespace has routes")
          try:
              srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
              socket.create_connection(("127.0.0.1", srv.getsockname()[1]), timeout=2).close(); srv.close()
          except OSError as exc:
              fail(f"loopback is not usable: {exc}")
          try:
              socket.create_connection(("192.0.2.1", 80), timeout=2)
              fail("external connection is possible")
          except OSError as exc:
              if exc.errno != errno.ENETUNREACH:
                  fail(f"unexpected error {exc.errno}")
          try:
              socket.getaddrinfo("isolation-probe.invalid", 443)
              fail("name resolution is possible")
          except socket.gaierror:
              pass
          print("network namespace ok: loopback usable, no external route, no name resolution")
          PY
          sudo -n unshare -n -- bash -euo pipefail -c 'ip link set lo up; python3 "$0"' "$RUNNER_TEMP/netns_probe.py"
      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065 # v5.6.0
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: backend/requirements.txt
      - name: Install declared dependencies
        run: python -m pip install --no-input -r backend/requirements.txt
      - name: Check imports resolve from any working directory
        run: |
          set -euo pipefail
          cd "$RUNNER_TEMP"
          python -c "import desk.cli, desk_view, live_view, backend.v3_api, backend.v3.runner.wiring, backend.tests.conftest; print('imports ok from', __import__('os').getcwd())"
      - name: Offline backend suite (integration excluded, empty network namespace)
        run: |
          set -euo pipefail
          mkdir -p reports
          sudo -n env "PATH=$PATH" "PYTHONPATH=$PYTHONPATH" unshare -n -- bash -euo pipefail -c '
            ip link set lo up
            python -m pytest backend/tests -m "not integration" --strict-markers -p no:cacheprovider \
              -q -rfsxX --junitxml=reports/backend-junit.xml 2>&1 | tee reports/backend.log
            exit ${PIPESTATUS[0]}'
      - name: Report (PASS / FAIL / skipped / xfail / deselected)
        if: always()
        run: |
          python - <<'PY'
          import os, re, sys, xml.etree.ElementTree as ET
          path = "reports/backend-junit.xml"
          if not os.path.exists(path):
              print("::error::no junit report"); sys.exit(1)
          cases = ET.parse(path).getroot().iter("testcase")
          n = dict(passed=0, failed=0, error=0, skipped=0, xfailed=0, xpassed=0)
          integration_ran = 0
          for c in cases:
              kids = {k.tag: k for k in c}
              if "failure" in kids: n["failed"] += 1
              elif "error" in kids: n["error"] += 1
              elif "skipped" in kids:
                  n["xfailed" if "xfail" in (kids["skipped"].get("type") or "") else "skipped"] += 1
              else:
                  n["passed"] += 1
                  if "test_superbot" in (c.get("classname") or ""): integration_ran += 1
          log = open("reports/backend.log", encoding="utf-8").read()
          m = re.search(r"(\d+) deselected", log)
          deselected = int(m.group(1)) if m else 0
          rows = "\n".join(f"| {k} | {v} |" for k, v in [*n.items(), ("deselected (integration)", deselected)])
          md = f"### Backend offline (Python 3.11)\n| esito | n |\n|---|---|\n{rows}\n"
          open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8").write(md)
          print(md)
          bad = n["failed"] or n["error"] or n["xpassed"] or integration_ran
          sys.exit(1 if bad else 0)
          PY
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        if: always()
        with:
          name: backend-reports
          path: reports/
          retention-days: 7

  frontend:
    name: Frontend Jest + build (Node 22)
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0
        with:
          ref: ${{ github.sha }}
          persist-credentials: false
          fetch-depth: 1
      - name: Preflight - empty network namespace (fail fast, no fallback)
        run: |
          set -euo pipefail
          command -v unshare >/dev/null || { echo "::error::unshare not available"; exit 1; }
          command -v ip >/dev/null || { echo "::error::ip (iproute2) not available"; exit 1; }
          sudo -n true || { echo "::error::passwordless sudo not available"; exit 1; }
          cat > "$RUNNER_TEMP/netns_probe.py" <<'PY'
          import errno, socket, sys
          def fail(msg):
              print("::error::" + msg); sys.exit(1)
          ifaces = [l.split(":")[0].strip() for l in open("/proc/net/dev").read().splitlines()[2:]]
          if ifaces != ["lo"]:
              fail(f"namespace not isolated: interfaces={ifaces}")
          if open("/proc/net/route").read().splitlines()[1:]:
              fail("namespace has routes")
          try:
              srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
              socket.create_connection(("127.0.0.1", srv.getsockname()[1]), timeout=2).close(); srv.close()
          except OSError as exc:
              fail(f"loopback is not usable: {exc}")
          try:
              socket.create_connection(("192.0.2.1", 80), timeout=2)
              fail("external connection is possible")
          except OSError as exc:
              if exc.errno != errno.ENETUNREACH:
                  fail(f"unexpected error {exc.errno}")
          try:
              socket.getaddrinfo("isolation-probe.invalid", 443)
              fail("name resolution is possible")
          except socket.gaierror:
              pass
          print("network namespace ok: loopback usable, no external route, no name resolution")
          PY
          sudo -n unshare -n -- bash -euo pipefail -c 'ip link set lo up; python3 "$0"' "$RUNNER_TEMP/netns_probe.py"
      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020 # v4.4.0
        with:
          node-version: '22'
          cache: yarn
          cache-dependency-path: frontend/yarn.lock
      - name: Install (lockfile)
        run: yarn install --frozen-lockfile --ignore-engines --network-timeout 300000
      - name: Jest (empty network namespace)
        run: |
          set -euo pipefail
          mkdir -p ../reports
          sudo -n env "PATH=$PATH" unshare -n -- bash -euo pipefail -c '
            CI=true npx --no-install react-scripts test --watchAll=false --runInBand \
              --json --outputFile=../reports/jest.json'
      - name: Build (CI=true, empty network namespace)
        env:
          CI: 'true'
          BUILD_PATH: ${{ runner.temp }}/rc84-build
        run: sudo -n env "PATH=$PATH" "CI=$CI" "BUILD_PATH=$BUILD_PATH" "REACT_APP_BACKEND_URL=" unshare -n -- npx --no-install react-scripts build
      - name: Report
        if: always()
        working-directory: .
        run: |
          python3 - <<'PY'
          import json, os, sys
          p = "reports/jest.json"
          if not os.path.exists(p):
              print("::error::no jest report"); sys.exit(1)
          r = json.load(open(p, encoding="utf-8"))
          rows = [("passed", r["numPassedTests"]), ("failed", r["numFailedTests"]),
                  ("skipped/pending", r["numPendingTests"]), ("todo", r["numTodoTests"]),
                  ("suites", r["numTotalTestSuites"]), ("suites failed", r["numFailedTestSuites"])]
          md = "### Frontend Jest (Node 22)\n| esito | n |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows) + "\n"
          open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8").write(md)
          print(md)
          sys.exit(1 if r["numFailedTests"] or r["numFailedTestSuites"] else 0)
          PY
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        if: always()
        with:
          name: frontend-reports
          path: reports/
          retention-days: 7
```

### Sicurezza della pipeline (verificata anche da `backend/tests/test_v3_rc84_ci_proposal.py`)
- `permissions: contents: read`; nessun `secrets.*`, nessun `GITHUB_TOKEN` esplicito oltre al default in sola lettura, `persist-credentials: false`.
- Nessun `ssh`, `scp`, `rsync`, `docker`, `systemctl`, `curl`, `deploy`; nessun `workflow_call`, `workflow_run`, `repository_dispatch`, `uses: ./.github/...`.
- **Azioni ufficiali fissate a commit SHA** (vedi sotto), nessuna azione nuova o di terzi: `actions/checkout`, `setup-python`, `setup-node`, `upload-artifact`.
- `REACT_APP_BACKEND_URL` **vuota** e `SUPERBOT_ALLOW_INTEGRATION=0` a livello di workflow; `-m "not integration"` **e** barriera in `conftest.py`.
- **Preflight fail-fast del namespace di rete**, in entrambi i job, **prima** di installare o testare: diagnostica (`uname`, release, utente, `ip -V`, `unshare --version`,
  sysctl AppArmor sugli user namespace), poi verifica che `unshare`, `ip` e `sudo -n` esistano, poi una sonda dentro `sudo -n unshare -n` che richiede: solo
  l'interfaccia `lo`, nessuna rotta, loopback usabile (bind+connect), connessione verso `192.0.2.1` (RFC 5737) = `ENETUNREACH`, risoluzione di `isolation-probe.invalid` fallita.
  Qualunque anomalia ⇒ `exit 1` e il job si ferma. **Non esiste alcun ripiego**: nessun `||`, nessun `continue-on-error`, nessun passo che esegua test senza il namespace.
- Test, Jest e build girano in `sudo -n unshare -n` con `set -euo pipefail`; le dipendenze si installano **prima**, in step separati con rete.
- **`PYTHONPATH` esplicito e assoluto** (`<workspace>:<workspace>/backend`, equivalente a `.:backend` ma immune ai test che cambiano cwd) e passato esplicitamente a `sudo env`.
  Un passo dedicato verifica che `desk.cli`, `desk_view`, `live_view`, `backend.v3_api`, `backend.v3.runner.wiring` e `backend.tests.conftest` si importino da una cartella estranea.
- Il job fallisce se un qualunque test di `test_superbot` risulta eseguito, se c'è un `failed`/`error`/`xpassed`, o se l'SHA del checkout non è quello atteso.

### Pin delle azioni (verificati il 09/11/2026 con `git ls-remote` in sola lettura sui repository ufficiali, poi `git fetch --depth 1` del commit)
| azione | tag | commit SHA | data del commit | verifica |
|---|---|---|---|---|
| `actions/checkout` | v4 (= v4.4.0) | `11d5960a326750d5838078e36cf38b85af677262` | 2026-07-16 | il tag `v4` e il patch più alto `v4.4.0` puntano allo stesso commit; oggetto `commit` |
| `actions/setup-python` | v5 (= v5.6.0) | `a26af69be951a213d495a4c3e4e4022e16d87065` | 2025-04-23 | idem (`v5.6.0`) |
| `actions/setup-node` | v4 (= v4.4.0) | `49933ea5288caeca8642d1e84afbd3f7d6820020` | 2025-04-02 | idem (`v4.4.0`) |
| `actions/upload-artifact` | v4 (= v4.6.2) | `ea165f8d65b6e75b540449e92b4886f43607fa02` | 2025-03-19 | idem (`v4.6.2`) |

Restano sulla **stessa serie maggiore** già usata dagli altri workflow del repository (nessun cambio di comportamento). Limite: la verifica prova che il tag ufficiale punta a quel commit
*oggi*; non sostituisce una revisione del contenuto delle azioni. Rieseguire il controllo al momento della pubblicazione e prima di ogni aggiornamento.

### Compatibilità dei test con la futura pubblicazione
`test_v3_rc84_ci_proposal.py` ammette **due soli stati** del repository, tramite `workflow_state_problems()`: (a) proposta inattiva, file `.github/workflows/rc84-offline-verify.yml` assente;
(b) pubblicazione autorizzata, file presente e **identico** al YAML approvato in questo documento (confronto insensibile solo a fine riga CRLF, spazi finali e righe vuote ai bordi).
Falliscono: file modificato (permessi, trigger, pin, preflight, ripiego, URL, `PYTHONPATH`, segreti, ssh), varianti o copie (`.yaml`, `-copy`), un altro workflow con lo stesso nome, collegamento simbolico.
Provato con directory temporanee sintetiche (25 test) e con una **prova generale in una copia di scratch** con il file identico: suite completa 7 003 passed, 0 failed; con il file alterato il test fallisce.
Quando il workflow verrà pubblicato non servirà modificare alcun test; se si modifica il YAML bisogna aggiornare il documento (è la fonte approvata).

### Quale evento lo attiverebbe, una volta approvato
1. **`push` sul solo ramo `cursor/rc84-running-stop-health-telegram-20261108`, e solo se il push modifica `.github/workflows/rc84-offline-verify.yml`.**
   Quindi il commit che *aggiunge* il file produce **un** run; i push successivi che non toccano il file non fanno partire nulla. Per rilanciare
   serve un nuovo commit che modifichi il file (anche solo un commento). Il commit **non deve contenere `[skip ci]`**, altrimenti il run viene soppresso.
2. `workflow_dispatch` (con `expected_sha` facoltativo): GitHub rende lanciabile a mano un workflow solo se il file esiste sul ramo predefinito (`main`), cosa che
   qui non accade finché non c'è un merge. **Non contare su questo evento.**
3. Nessun `pull_request`, `schedule`, `workflow_run`, `repository_dispatch`. Nessun altro workflow esistente scatta su questo ramo (89 workflow esaminati; 0 run sul ramo).

Lo SHA verificato è quello del commit che contiene il workflow (`github.sha`): differisce dal codice RC84 solo per quel file.

## 3. Procedura di pubblicazione (da eseguire solo dopo approvazione esplicita)
1. Rivedere questo documento e il YAML; decidere i pin (punto 5).
2. In un commit **separato**, solo per il ramo RC84 della PR #80 (Draft), creare `.github/workflows/rc84-offline-verify.yml` con il YAML sopra, senza `[skip ci]`.
3. Il push avvia un solo run. Leggere i log e il riepilogo; non promettere il verde prima del run.
4. Se il run è rosso, correggere e fare un nuovo commit che tocchi il file; non rilanciare altri workflow.
5. Dopo l'esito, valutare di rimuovere il file prima di qualsiasi merge (vedi §5, workflow su `main`).

## 4. Risultati attesi e verificati in sandbox (Python 3.11, stessi comandi del YAML, namespace di rete vuoto)
| | atteso | verificato localmente |
|---|---|---|
| backend `-m "not integration"` | 7 003 passed (6 910 + 61 guardia integrazione + 25 proposta + 7 import/ordine), 3 xfailed, 9 deselected, 0 failed | **7 003 passed, 0 failed, 3 xfailed, 9 deselected** in un namespace di rete vuoto, sia nello stato reale (workflow assente) sia in una copia di prova con il workflow approvato presente; in precedenza anche con i file di test in ordine inverso (loopback riattivato con `ioctl`: qui manca `ip`) |
| auth/profiles | inclusi | inclusi |
| import da cwd estranea, ordine dei test (avanti / inverso / ruotato / mescolato) | PASS | 7 test PASS (`test_v3_rc84_import_paths.py`), `PYTHONPATH` relativo da altra cwd fallisce come documentato |
| sonda del namespace (stesso codice del YAML) | OK dentro, errore fuori, errore senza loopback | verificato nei tre casi (loopback attivato con `ioctl`: qui manca `ip`) |
| Jest (Node 22) | 124 passed, 0 failed, 14 suite | 124 / 0 / 14 |
| build `CI=true` | Compiled successfully | Compiled successfully |
| `actionlint` 1.7.12 sul YAML | nessun avviso | nessun avviso |
Lo script di report è stato provato su tre junit: reale (exit 1 per il FAIL), pulito (exit 0), con un test di `test_superbot` eseguito (exit 1).
Il run su GitHub **non è stato eseguito**: questi sono risultati locali, non una CI.

## 5. Limiti e punti aperti
- **Pin delle azioni**: SHA verificati qui sopra; da riverificare alla pubblicazione. I commenti `# vX.Y.Z` accanto agli SHA sono solo informativi.
- **Da verificare solo su un runner GitHub reale** (non provabile qui): `ip link set lo up`, `sudo -n unshare -n` e `iproute2` su `ubuntu-24.04` ospitato, eventuali limiti AppArmor/namespace, comportamento di `setup-python`/`setup-node`/cache, upload degli artefatti. Il preflight è pensato per far fallire subito il job con una diagnostica leggibile; se fallisce, **non** si ripiega sui test con rete: si discute un'alternativa revisionabile (es. runner con rete controllata) prima di riprovare.
- Il namespace vuoto non impedisce a un test di *tentare* connessioni (falliranno): è il comportamento voluto; nessun test attuale ne dipende.
- Il job gira come root dentro `unshare`: i file in `reports/` risultano di root (irrilevante per gli step seguenti).
- **Workflow operativi presenti nel repository**: `v3-stop-paper-workers.yml` e `v3-vps-inventory.yml` hanno un trigger `push` su `main`; una futura fusione in `main` li farebbe partire. Decisione da prendere prima di qualsiasi merge.
- Release candidate unica ancora da definire (PR #76 non inclusa; 2 commit di `main` mancanti), browser autenticato/Android, backup off-host, preflight VPS, rimozione/rotazione della password di bootstrap: gate aperti dell'audit.
