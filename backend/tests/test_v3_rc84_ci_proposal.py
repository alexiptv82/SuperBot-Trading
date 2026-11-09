"""La proposta di CI offline RC84 resta una PROPOSTA inerte e sicura (nessun workflow attivo, nessun segreto/ssh/deploy).

Nessuna dipendenza esterna (niente PyYAML): i controlli sono sul testo, cosi' il test non puo' essere saltato in CI.
La sintassi del YAML e' verificata a parte con actionlint (vedi il documento).
"""
from __future__ import annotations

import re
from pathlib import Path

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


def test_proposal_is_not_an_active_workflow():
    assert DOC.exists() and ".github" not in DOC.parts
    workflows = list((ROOT / ".github/workflows").glob("*.y*ml"))
    assert "rc84-offline-verify.yml" not in {p.name for p in workflows}
    for p in workflows:
        assert "RC84 offline verification" not in p.read_text(encoding="utf-8")


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


def test_only_official_actions_and_no_other_workflow_is_invoked():
    uses = re.findall(r"(?m)^\s*-?\s*uses:\s*(\S+)", _yaml_text())
    assert uses and all(u.startswith("actions/") for u in uses)


def test_integration_is_excluded_fail_closed_and_the_backend_url_is_empty():
    text = _no_comments()
    env = _block(text, "env")
    assert re.search(r"(?m)^  REACT_APP_BACKEND_URL: ''$", env)
    assert re.search(r"(?m)^  SUPERBOT_ALLOW_INTEGRATION: '0'$", env)
    assert '-m "not integration"' in text and "--strict-markers" in text
    assert text.count("unshare -n") == 3                           # pytest, jest, build: mai con rete


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
