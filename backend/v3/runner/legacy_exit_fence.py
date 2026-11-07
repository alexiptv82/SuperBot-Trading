"""Optional legacy-owner bridge to the same lock used by ExitService.

This does NOT fence an unpatched legacy process. Migration must FIRST start
legacy with this lease for its entire exit-owning lifetime and verify it in
staging; ONLY THEN can the split worker safely replace legacy. This module
acquires no lease on import and creates no heartbeat purporting to be healthy.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from backend.v3.runner.exit_service import ExitService
from backend.v3.runner.monitor import MonitorReport


class LegacyExitFence:
    """Passive adapter, same kernel-exclusive ExitService lease as sidecar.

    Integrator must hold it from BEFORE legacy commands/monitor begin until
    AFTER they have fully stopped. Do not call its tick; the legacy runner
    retains its original monitor behavior and timing during migration.
    """
    def __init__(self, *, run_id: str, data_dir: Path):
        self._owner = ExitService(
            run_id=run_id, data_dir=data_dir,
            run_commands=lambda _: None,
            run_monitor=lambda _: MonitorReport(0,(),()),
        )
        self._held = False

    def start(self) -> "LegacyExitFence":
        if self._held:
            raise RuntimeError("legacy_fence_already_held")
        self._owner.start()
        self._held = True
        return self

    @property
    def held(self) -> bool:
        return self._held

    def stop(self) -> None:
        if self._held:
            self._owner.stop()
            self._held = False

    def __enter__(self) -> "LegacyExitFence":
        return self.start()

    def __exit__(self, *_: object) -> None:
        self.stop()
