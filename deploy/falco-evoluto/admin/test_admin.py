"""Autonomia amministrativa limitata: wrapper superbot-ops, regola sudo, installatore. Prove offline (nessun sudo reale)."""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SUDOERS = (HERE / "superbot-ops.sudoers").read_text()
ALLOWED = re.findall(r"/usr/local/sbin/superbot-ops ([a-z0-9 -]+?)(?:, \\|\n)", SUDOERS)
RC1_FILES = {"80-paper.sh": REPO / "deploy/brain-unico/avvio/80-paper.sh",
             "comune.sh": REPO / "deploy/brain-unico/precollaudo/comune.sh",
             "30-controlli.sh": REPO / "deploy/brain-unico/precollaudo/30-controlli.sh",
             "controlli.py": REPO / "deploy/brain-unico/precollaudo/controlli.py"}
FS_FILES = {"80-paper.sh": HERE.parent / "rilascio/80-paper.sh", "comune.sh": HERE.parent / "rilascio/comune.sh",
            "controlli.py": REPO / "deploy/brain-unico/precollaudo/controlli.py",
            "90-rollback.sh": HERE.parent / "rilascio/90-rollback.sh"}


def _wrapper(tmp):
    rc1, fs, bins, log = tmp / "rc1", tmp / "fs", tmp / "bin", tmp / "log"
    for d, files in ((rc1, RC1_FILES), (fs, FS_FILES)):
        d.mkdir()
        for name, src in files.items():
            shutil.copy(src, d / name)
            (d / name).chmod(0o500)                       # come l'installazione reale (install -m 500)
    bins.mkdir()
    for name, body in (("id", "echo 0"), ("stat", "echo 0"), ("sh", f'echo "sh $*" >> {log}'),
                       ("systemctl", f'echo "systemctl $*" >> {log}; echo active'),
                       ("journalctl", f'echo "journalctl $*" >> {log}'), ("docker", f'echo "docker $*" >> {log}')):
        (bins / name).write_text(f"#!/bin/bash\n{body}\n")
        (bins / name).chmod(0o755)
    src = (HERE / "superbot-ops").read_text()
    src = src.replace("PATH=/usr/sbin:/usr/bin:/sbin:/bin", f"PATH={bins}:/usr/sbin:/usr/bin:/sbin:/bin")
    src = src.replace("RC1D=/root/brain-unico-avvio", f"RC1D={rc1}").replace("FSD=/root/falco-scalp-rilascio", f"FSD={fs}")
    w = tmp / "superbot-ops"
    w.write_text(src)
    return w, log, rc1, fs


def _run(w, *args):
    return subprocess.run(["/bin/sh", str(w), *args], capture_output=True, text=True, timeout=30)


def test_sudoers_is_valid_and_lists_only_exact_wrapper_commands():
    assert subprocess.run(["/usr/sbin/visudo", "-cf", str(HERE / "superbot-ops.sudoers")],
                          capture_output=True).returncode == 0
    assert len(ALLOWED) == 22 and len(set(ALLOWED)) == 22
    assert "*" not in SUDOERS and "ALL=(root) NOPASSWD: SUPERBOT_OPS" in SUDOERS
    assert re.findall(r"^\s*(/\S+)", SUDOERS, re.M) == ["/usr/local/sbin/superbot-ops"] * 22   # nessun altro binario
    for bad in ("attiva", "riprendi", "approva", "bash", "docker exec", "systemctl", "/bin/sh"):
        assert not any(c.startswith(bad) for c in ALLOWED)


EXPECT = {
    "pausa rc1": "sh {rc1}/80-paper.sh pausa", "pausa falco": "sh {fs}/80-paper.sh falco pausa",
    "revoca scalp": "sh {fs}/80-paper.sh scalp revoca", "revoca rc1": "sh {rc1}/80-paper.sh revoca",
    "riavvia-uscite falco": "systemctl restart superbot-falco-evoluto-p1-exit.service",
    "riavvia-runner scalp": "systemctl restart superbot-brain-scalp-p1-runner.service",
    "riavvia-uscite rc1": "systemctl restart superbot-brain-unico-rc1-exit.service",
    "riavvia-bridge": "systemctl restart superbot-v3-paper-single-close-bridge.service",
    "log falco-runner": "journalctl -u superbot-falco-evoluto-p1-runner.service -n 200 --no-pager -o short-iso",
    "log bridge": "journalctl -u superbot-v3-paper-single-close-bridge.service -n 200 --no-pager -o short-iso",
    "rollback-falco-scalp": "sh {fs}/90-rollback.sh",
}


def test_every_allowed_command_runs_and_maps_to_its_fixed_action(tmp_path):
    w, log, rc1, fs = _wrapper(tmp_path)
    for cmd in ALLOWED:
        p = _run(w, *cmd.split())
        assert p.returncode == 0, (cmd, p.stderr)
    text = log.read_text()
    for cmd, want in EXPECT.items():
        assert want.format(rc1=rc1, fs=fs) in text, cmd
    assert "docker restart -t 10 superbot" in text                          # solo dentro riavvia-bridge
    assert "attiva" not in text and "riprendi" not in text


@pytest.mark.parametrize("args", [[], ["attiva", "falco"], ["riprendi", "scalp"], ["pausa"], ["pausa", "toro"],
                                  ["pausa", "falco", "x"], ["log", "nginx"], ["log", "../../etc/shadow"],
                                  ["stato", "extra"], ["pausa", "falco;id"], ["riavvia-uscite", "superbot"],
                                  ["revoca", "arena"], ["rollback-falco-scalp", "now"], ["bash"]])
def test_anything_else_is_refused_without_side_effects(tmp_path, args):
    w, log, _, _ = _wrapper(tmp_path)
    p = _run(w, *args)
    assert p.returncode == 2 and "non consentita" in p.stderr
    assert not log.exists()


def test_a_modified_script_blocks_the_wrapper(tmp_path):
    w, log, rc1, fs = _wrapper(tmp_path)
    (fs / "80-paper.sh").chmod(0o700)
    (fs / "80-paper.sh").write_text((fs / "80-paper.sh").read_text() + "\n# alterato\n")
    p = _run(w, "pausa", "falco")
    assert p.returncode == 3 and "modificato" in p.stderr and not log.exists()
    assert _run(w, "pausa", "rc1").returncode == 0                           # RC1 resta gestibile


def test_installer_pins_the_exact_files():
    text = (HERE / "installa.sh").read_text()
    block = text.split("<<'LISTA'\n", 1)[1].split("LISTA\n", 1)[0]          # blocco della ripresa
    pairs = re.findall(r"^([0-9a-f]{64}) (deploy/\S+)$", block, re.M)
    assert len(pairs) == 19 and "deploy/falco-evoluto/rilascio/00-ripresa.sh" in [r for _, r in pairs]
    for h, rel in pairs:
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == h, rel
    for name in ("superbot-ops", "superbot-ops.sudoers"):
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() in text
    assert "SHA=246a3a92fc21d30b775f866bc266876c84199552" in text
    assert 'rilascio) nogo "le run esistono gia' in text and 'sh "$PKG/00-ripresa.sh"' in text   # niente run ricreate and "6dad215321b725f7a129228dba793de7f2abee64c9878a89014612effe2f198b" in text
    assert subprocess.run(["bash", "-n", str(HERE / "installa.sh")]).returncode == 0


def test_a_script_writable_by_others_is_refused_even_with_the_right_hash(tmp_path):
    w, log, rc1, _ = _wrapper(tmp_path)
    (rc1 / "80-paper.sh").chmod(0o664)
    p = _run(w, "pausa", "rc1")
    assert p.returncode == 3 and not log.exists()
