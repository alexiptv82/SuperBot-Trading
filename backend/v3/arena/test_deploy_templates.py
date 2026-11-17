"""I template systemd dell'Arena puntano a comandi e percorsi validi. Nessun servizio avviato."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from backend.tests.test_v3_runner_e2e import G
from backend.v3.arena.test_arena_runner import _prepare
from backend.v3.runner import exit_worker as EW

UNITS = Path(__file__).resolve().parents[3] / "deploy" / "arena-paper-services"


def _exec(name: str, provider: str, compact: str, day: str) -> list[str]:
    text = (UNITS / name).read_text()
    assert not re.search(r"^\[Install\]", text, re.M)                       # mai avvio automatico
    line = next(x for x in text.splitlines() if x.startswith("ExecStart="))[len("ExecStart="):]
    line = line.replace("%i", provider).replace("${ARENA_DAY_COMPACT}", compact).replace("${ARENA_DAY}", day)
    return shlex.split(line)


def test_units_are_paper_only_and_never_touch_existing_wallets():
    for unit in UNITS.glob("*.service"):
        text = unit.read_text()
        assert "DESK_MODE=paper" in text and not re.search(r"^\[Install\]", text, re.M)
        assert "/opt/superbot-v3-paper-runs" not in text and "/opt/superbot-desk-data" not in text
        assert not re.search(r"(?i)(api[_-]?key|sk-[a-z0-9])\s*=", text)


def test_exit_unit_command_validates_a_prepared_arena_run(tmp_path):
    root = tmp_path / "arena"
    root.mkdir()
    plan = _prepare(root, "minimax")
    argv = _exec("superbot-arena-exit@.service", "minimax", "20261118", "2026-11-18")
    assert argv[1:3] == ["-m", "backend.v3.runner.exit_worker"] and "--legacy-exits-disabled" in argv
    args = [a.replace("/opt/superbot-ai-arena-paper", str(root)) for a in argv[3:]]
    args[args.index("--start-paper")] = "--validate-only"
    args.remove("--legacy-exits-disabled")
    assert EW.main(args, env={"DESK_MODE": "paper"}, clock=lambda: G) == 0
    assert plan.folder.is_dir()


def test_runner_unit_command_matches_the_arena_cli():
    argv = _exec("superbot-arena-runner@.service", "qwen", "20261118", "2026-11-18")
    assert argv[1:] == ["-m", "backend.v3.arena.runner", "--provider", "qwen", "--root",
                        "/opt/superbot-ai-arena-paper", "--day", "2026-11-18"]
