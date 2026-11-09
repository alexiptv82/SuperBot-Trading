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
- `backend/tests/test_ci_integration_guard.py` (nuovo, 17 test): un finto server su `127.0.0.1` **conta ogni richiesta**. Sottoprocessi pytest
  selezionano `test_superbot.py` con l'URL del finto server o con `http://backend.invalid:9` / `https://staging.example.org`:
  senza opt-in **0 richieste, 0 POST, 9 skipped**; con `-m "not integration"` 9 deselected; opt-in con host non locale rifiutato; opt-in senza URL
  inerte. Un **controllo positivo** (opt-in locale) prova che il contatore vede `GET /api/health` e `POST /api/bot/start`: senza questo "zero richieste"
  non dimostrerebbe nulla. Mutazione: neutralizzando le due barriere, 4 test falliscono (poi ripristinato).

La password di bootstrap resta altrove nel repository (`backend/auth.py`, test di autenticazione che verificano che sia *rifiutata* come nuova password,
`.github/workflows/staging-deploy.yml`): fuori da questo incarico, già segnalata come rischio nell'audit.

## 2. Pipeline proposta

`/.github/workflows/rc84-offline-verify.yml` (nome proposto; **non creato**):

```yaml
name: RC84 offline verification (TEST ONLY)

# SOLO VERIFICA. Nessun segreto, nessun ssh/scp/docker/systemctl, nessun deploy, nessun altro workflow richiamato.
# I test girano in un namespace di rete vuoto (nessuna richiesta esterna possibile, nemmeno verso Bitget).
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

jobs:
  backend:
    name: Backend offline (Python 3.11)
    runs-on: ubuntu-24.04
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
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
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: pip
          cache-dependency-path: backend/requirements.txt
      - name: Install declared dependencies
        run: python -m pip install --no-input -r backend/requirements.txt
      - name: Offline backend suite (integration excluded, empty network namespace)
        run: |
          mkdir -p reports
          # Namespace di rete vuoto: solo loopback. Nessuna richiesta esterna e' possibile.
          sudo -E env "PATH=$PATH" unshare -n -- bash -c '
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
      - uses: actions/upload-artifact@v4
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
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.sha }}
          persist-credentials: false
          fetch-depth: 1
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: yarn
          cache-dependency-path: frontend/yarn.lock
      - name: Install (lockfile)
        run: yarn install --frozen-lockfile --ignore-engines --network-timeout 300000
      - name: Jest (empty network namespace)
        run: |
          mkdir -p ../reports
          sudo -E env "PATH=$PATH" unshare -n -- bash -c '
            CI=true npx --no-install react-scripts test --watchAll=false --runInBand \
              --json --outputFile=../reports/jest.json'
      - name: Build (CI=true)
        env:
          CI: 'true'
          BUILD_PATH: ${{ runner.temp }}/rc84-build
        run: sudo -E env "PATH=$PATH" unshare -n -- npx --no-install react-scripts build
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
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: frontend-reports
          path: reports/
          retention-days: 7
```

### Sicurezza della pipeline (verificata anche da `backend/tests/test_v3_rc84_ci_proposal.py`)
- `permissions: contents: read`; nessun `secrets.*`, nessun `GITHUB_TOKEN` esplicito oltre al default in sola lettura, nessun `persist-credentials`.
- Nessun `ssh`, `scp`, `rsync`, `docker`, `systemctl`, `curl`, `deploy`; nessun `workflow_call`, `workflow_run`, `repository_dispatch`, `uses: ./.github/...`.
- Azioni di terze parti: solo `actions/*` ufficiali.
- `REACT_APP_BACKEND_URL` **vuota** e `SUPERBOT_ALLOW_INTEGRATION=0` a livello di workflow; `-m "not integration"` **e** barriera in `conftest.py`.
- I test girano in un **namespace di rete vuoto** (`unshare -n`): nessuna richiesta esterna possibile, nemmeno verso Bitget. Provato in sandbox: connessione
  a un IP esterno → `OSError`, risoluzione DNS di `api.bitget.com` → `gaierror`. Le dipendenze si installano **prima**, in step separati con rete.
- Il job fallisce se un qualunque test di `test_superbot` risulta eseguito, se c'è un `failed`/`error`/`xpassed`, o se l'SHA del checkout non è quello atteso.

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
| backend `-m "not integration"` | 6 935 passed (6 910 + 17 test di guardia + 8 test della proposta), 3 xfailed, 9 deselected, 0 failed | **6 935 passed, 0 failed, 3 xfailed, 9 deselected** in un namespace di rete vuoto (loopback riattivato con `ioctl` perché qui manca `ip`; un primo run senza loopback aveva 6 926 passed + 1 failed nel solo test di controllo positivo, che richiede il loopback) |
| auth/profiles | inclusi | inclusi |
| Jest (Node 22) | 124 passed, 0 failed, 14 suite | 124 / 0 / 14 |
| build `CI=true` | Compiled successfully | Compiled successfully |
| `actionlint` 1.7.12 sul YAML | nessun avviso | nessun avviso |
Lo script di report è stato provato su tre junit: reale (exit 1 per il FAIL), pulito (exit 0), con un test di `test_superbot` eseguito (exit 1).
Il run su GitHub **non è stato eseguito**: questi sono risultati locali, non una CI.

## 5. Limiti e punti aperti
- **Pin delle azioni**: il YAML usa tag (`@v4`, `@v5`); all'approvazione vanno sostituiti con SHA di commit verificati (qui non verificabili offline).
- `ip link set lo up` e `sudo unshare -n` assumono un runner `ubuntu-24.04` con `sudo` senza password e `iproute2` (standard sui runner ospitati da GitHub); non provati su un runner reale.
- Il namespace vuoto non impedisce a un test di *tentare* connessioni (falliranno): è il comportamento voluto; nessun test attuale ne dipende.
- Il job gira come root dentro `unshare`: i file in `reports/` risultano di root (irrilevante per gli step seguenti).
- **Workflow operativi presenti nel repository**: `v3-stop-paper-workers.yml` e `v3-vps-inventory.yml` hanno un trigger `push` su `main`; una futura fusione in `main` li farebbe partire. Decisione da prendere prima di qualsiasi merge.
- Release candidate unica ancora da definire (PR #76 non inclusa; 2 commit di `main` mancanti), browser autenticato/Android, backup off-host, preflight VPS, rimozione/rotazione della password di bootstrap: gate aperti dell'audit.
