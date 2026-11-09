"""La proposta di CI offline RC84 resta una PROPOSTA inerte e sicura (nessun workflow attivo, nessun segreto/ssh/deploy).

Nessuna dipendenza esterna (niente PyYAML): i controlli sono sul testo, cosi' il test non puo' essere saltato in CI.
La sintassi del YAML e' verificata a parte con actionlint (vedi il documento).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/v3/RC84-CI-OFFLINE-PROPOSAL-20261109.md"
BRANCH = "cursor/rc84-running-stop-health-telegram-20261108"
FORBIDDEN = ("ssh", "scp", "rsync", "docker", "systemctl", "curl", "wget", "deploy", "secrets.", "sshpass",
             "workflow_call", "workflow_run", "repository_dispatch", "uses: ./", "gh workflow", "gh api",
             "bitget", "anthropic", "persist-credentials: true", "pull_request", "schedule:")


def _yaml_text() -> str:
    m = re.search(r"```yaml\n(.*?)\n```", DOC.read_text(encoding="utf-8"), re.S)
    assert m, "blocco yaml mancante"
    return m.group(1)


def _no_comments() -> str:
    return re.sub(r"(?m)^\s*#.*$", "", _yaml_text())               # i commenti spiegano i divieti


def _block(text: str, key: str) -> str:
    m = re.search(rf"(?m)^{key}:\n((?:[ \t]+.*\n|\n)+)", text + "\n")
    assert m, key
    return m.group(1)


WORKFLOW_FILE = "rc84-offline-verify.yml"
WORKFLOW_MARKER = "RC84 offline verification"


def _normalized(text: str) -> str:
    """Confronto insensibile a fine riga CRLF, spazi finali e righe vuote iniziali/finali (nient'altro)."""
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n"))


def workflow_state_problems(workflows_dir: Path, approved_yaml: str) -> list[str]:
    """Problemi dello stato del workflow, valido in ENTRAMBI gli stati ammessi:
    - proposta ancora inattiva: il file non esiste;
    - pubblicazione autorizzata: il file esiste ed e' IDENTICO al YAML approvato nel documento.
    Qualunque altra cosa (file modificato, copie o varianti, altri workflow con lo stesso nome, link simbolici) e' un problema."""
    problems: list[str] = []
    if not workflows_dir.is_dir():
        return problems
    for path in sorted(workflows_dir.iterdir()):
        if path.is_dir() or path.suffix not in (".yml", ".yaml"):
            continue
        if path.name == WORKFLOW_FILE:
            if path.is_symlink():
                problems.append(f"{path.name}: collegamento simbolico")
            elif _normalized(path.read_text(encoding="utf-8")) != _normalized(approved_yaml):
                problems.append(f"{path.name}: diverso dal YAML approvato nel documento")
        elif path.name.startswith("rc84-offline-verify"):
            problems.append(f"{path.name}: variante non approvata del workflow")
        elif WORKFLOW_MARKER in path.read_text(encoding="utf-8"):
            problems.append(f"{path.name}: un altro workflow usa il nome della proposta")
    return problems


def test_real_repository_state_is_either_inactive_or_exactly_the_approved_workflow():
    assert DOC.exists() and ".github" not in DOC.parts
    assert workflow_state_problems(ROOT / ".github/workflows", _yaml_text()) == []


def _tree(tmp_path, files):
    d = tmp_path / ".github/workflows"
    d.mkdir(parents=True)
    for name, text in files.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def test_state_inactive_proposal_passes(tmp_path):
    assert workflow_state_problems(tmp_path / "missing", _yaml_text()) == []
    assert workflow_state_problems(_tree(tmp_path, {}), _yaml_text()) == []
    assert workflow_state_problems(_tree(tmp_path / "x", {"other.yml": "name: Altro\non: push\n"}), _yaml_text()) == []


def test_state_future_published_workflow_identical_to_the_approved_yaml_passes(tmp_path):
    y = _yaml_text()
    assert workflow_state_problems(_tree(tmp_path / "a", {WORKFLOW_FILE: y}), y) == []
    assert workflow_state_problems(_tree(tmp_path / "b", {WORKFLOW_FILE: y + "\n"}), y) == []
    crlf = "\r\n".join(line + "  " for line in y.split("\n")) + "\r\n"
    assert workflow_state_problems(_tree(tmp_path / "c", {WORKFLOW_FILE: crlf}), y) == []


MODIFICATIONS = {
    "permessi di scrittura": ("  contents: read\n", "  contents: write\n"),
    "integrazione non esclusa": ('-m "not integration" ', ""),
    "tag al posto dello SHA": ("actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4.4.0", "actions/checkout@v4"),
    "segreto aggiunto": ("      - name: Check the SHA under test", "      - run: echo ${{ secrets.TOKEN }}\n      - name: Check the SHA under test"),
    "preflight rimosso": ("Preflight - empty network namespace (fail fast, no fallback)", "Setup"),
    "ripiego senza namespace": ("exit ${PIPESTATUS[0]}'\n      - name: Report (PASS", "exit ${PIPESTATUS[0]}' || python -m pytest backend/tests\n      - name: Report (PASS"),
    "trigger su pull_request": ("  push:\n", "  pull_request:\n  push:\n"),
    "altro ramo": ("branches: [cursor/rc84-running-stop-health-telegram-20261108]", "branches: ['**']"),
    "URL backend non vuoto": ("  REACT_APP_BACKEND_URL: ''", "  REACT_APP_BACKEND_URL: 'http://example.org'"),
    "PYTHONPATH relativo": ("PYTHONPATH: ${{ github.workspace }}:${{ github.workspace }}/backend", "PYTHONPATH: .:backend"),
    "ssh aggiunto": ("      - name: Install declared dependencies", "      - run: ssh host\n      - name: Install declared dependencies"),
}


@pytest.mark.parametrize("label", sorted(MODIFICATIONS))
def test_state_published_but_modified_or_missing_protections_fails(tmp_path, label):
    y = _yaml_text()
    old, new = MODIFICATIONS[label]
    assert old in y, label
    problems = workflow_state_problems(_tree(tmp_path, {WORKFLOW_FILE: y.replace(old, new, 1)}), y)
    assert problems and "diverso dal YAML approvato" in problems[0]


def test_state_variants_copies_and_name_collisions_fail(tmp_path):
    y = _yaml_text()
    assert workflow_state_problems(_tree(tmp_path / "a", {"rc84-offline-verify.yaml": y}), y)
    assert workflow_state_problems(_tree(tmp_path / "b", {"rc84-offline-verify-copy.yml": y}), y)
    assert workflow_state_problems(_tree(tmp_path / "c", {"deploy.yml": f"name: {WORKFLOW_MARKER} (TEST ONLY)\non: push\n"}), y)
    d = _tree(tmp_path / "d", {"real.yml": y})
    (d / WORKFLOW_FILE).symlink_to(d / "real.yml")
    assert any("collegamento simbolico" in p for p in workflow_state_problems(d, y))


def test_triggers_are_exactly_dispatch_and_a_path_filtered_push_on_the_rc84_branch():
    on = _block(_no_comments(), "on")
    assert set(re.findall(r"(?m)^  (\w+):", on)) == {"workflow_dispatch", "push"}
    assert f"    branches: [{BRANCH}]" in on
    assert "    paths: ['.github/workflows/rc84-offline-verify.yml']" in on


def test_read_only_permissions_and_exactly_two_plain_jobs():
    text = _no_comments()
    assert re.search(r"(?m)^permissions:\n  contents: read\n(?=\S|\n)", text)
    assert len(re.findall(r"(?m)^\s*permissions:", text)) == 1
    jobs = _block(text, "jobs")
    assert set(re.findall(r"(?m)^  (\w+):", jobs)) == {"backend", "frontend"}
    for key in ("needs", "environment", "services", "container", "strategy", "secrets"):
        assert not re.search(rf"(?m)^\s*{key}:", text), key


def test_no_secret_operational_or_remote_keywords():
    body = _no_comments().lower()
    for word in FORBIDDEN:
        assert word not in body, word
    assert "${{ secrets" not in body and "github_token" not in body


PINS = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
}


def test_only_the_four_official_actions_pinned_to_verified_commit_shas():
    uses = re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", _yaml_text())
    assert uses
    for u in uses:
        name, _, ref = u.partition("@")
        assert name in PINS, f"azione non prevista: {name}"
        assert re.fullmatch(r"[0-9a-f]{40}", ref), f"{name} non e' fissata a uno SHA"
        assert ref == PINS[name]
    assert {u.partition("@")[0] for u in uses} == set(PINS)
    doc = DOC.read_text(encoding="utf-8")
    for sha in PINS.values():
        assert sha in doc


def _steps(job: str) -> list[str]:
    """Testo di ciascuno step di un job, in ordine."""
    jobs = _block(_no_comments(), "jobs")
    m = re.search(rf"(?ms)^  {job}:\n(.*?)(?=^  \w+:\n|\Z)", jobs)
    assert m, job
    return re.split(r"(?m)^      - ", m.group(1))[1:]


def test_network_namespace_preflight_runs_first_in_both_jobs_and_is_fail_fast():
    for job in ("backend", "frontend"):
        steps = _steps(job)
        idx = next(i for i, st in enumerate(steps) if st.startswith("name: Preflight - empty network namespace"))
        first_real = next(i for i, st in enumerate(steps)
                          if "pytest" in st or "react-scripts" in st or "pip install" in st or "yarn install" in st)
        assert idx < first_real, f"{job}: il preflight deve precedere installazione e test"
        pre = steps[idx]
        assert "set -euo pipefail" in pre
        assert "sudo -n true" in pre and "command -v unshare" in pre and "command -v ip " in pre
        assert "sudo -n unshare -n --" in pre and "ip link set lo up" in pre
        assert "ENETUNREACH" in pre and "/proc/net/dev" in pre and "isolation-probe.invalid" in pre
        assert "exit 1" in pre or "sys.exit(1)" in pre


def test_there_is_no_fallback_that_runs_tests_with_an_open_network():
    text = _no_comments()
    assert "continue-on-error" not in text
    guard = re.compile(r'\|\| \{ echo "::error::[^"\n]*"; exit 1; \}')
    for line in text.splitlines():
        if re.search(r"unshare|pytest|react-scripts", line):
            # unico uso ammesso di "||": un controllo che stampa un errore ed esce con 1 (mai un ripiego)
            assert "||" not in guard.sub("", line), line
    for job in ("backend", "frontend"):
        for st in _steps(job):
            if "pytest" in st or "react-scripts test" in st or "react-scripts build" in st:
                assert "sudo -n" in st and "unshare -n --" in st and "set -euo pipefail" in st or "build" in st
                assert "if:" not in st.split("run:")[0]            # mai saltati o resi condizionali
    for st in _steps("backend") + _steps("frontend"):
        if "pytest backend/tests" in st or "react-scripts test" in st:
            assert "unshare -n --" in st


def test_pythonpath_is_explicit_absolute_and_forwarded_through_sudo():
    env = _block(_no_comments(), "env")
    assert "PYTHONPATH: ${{ github.workspace }}:${{ github.workspace }}/backend" in env
    run_step = next(st for st in _steps("backend") if "Offline backend suite" in st)
    assert '"PYTHONPATH=$PYTHONPATH"' in run_step
    check = next(st for st in _steps("backend") if "imports resolve" in st)
    assert 'cd "$RUNNER_TEMP"' in check and "desk.cli" in check and "backend.v3_api" in check


def test_integration_is_excluded_fail_closed_and_the_backend_url_is_empty():
    text = _no_comments()
    env = _block(text, "env")
    assert re.search(r"(?m)^  REACT_APP_BACKEND_URL: ''$", env)
    assert re.search(r"(?m)^  SUPERBOT_ALLOW_INTEGRATION: '0'$", env)
    assert '-m "not integration"' in text and "--strict-markers" in text
    assert len(re.findall(r"unshare -n --", text)) == 5            # 2 sonde + pytest + jest + build: mai con rete


def test_versions_and_scope():
    text = _no_comments()
    assert "python-version: '3.11'" in text and "node-version: '22'" in text
    assert "python -m pytest backend/tests" in text and "backend/requirements.txt" in text
    assert "react-scripts test" in text and "react-scripts build" in text
    assert "yarn install --frozen-lockfile" in text


def test_the_doc_states_what_triggers_it_and_that_nothing_was_started():
    text = DOC.read_text(encoding="utf-8")
    assert "NON è un workflow attivo" in text and "[skip ci]" in text
    assert "Il run su GitHub **non è stato eseguito**" in text
