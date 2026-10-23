"""Run the actual deployment preflight with a fake Docker; no server access."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]

class GuardTests(unittest.TestCase):
    def test_paper_and_unchanged_risk_are_required(self):
        source = (ROOT / ".github/workflows/desk-deploy.yml").read_text()
        start = source.index("            # Preserve runtime")
        end = source.index("            DEPLOY_START_MS=", start)
        block = "\n".join(line[12:] for line in source[start:end].splitlines())
        with tempfile.TemporaryDirectory() as folder:
            docker = Path(folder) / "docker"
            docker.write_text('#!/bin/sh\nprintf "DESK_MODE=%s\\nDESK_DAILY_LOSS_PCT=10\\nDESK_HAWK_CAPITAL=1000\\nDESK_BULL_CAPITAL=1000\\n" "${FAKE_MODE:-paper}"\n')
            docker.chmod(0o755)
            for mode, loss, capital, expected in [("paper", "10", "1000", True), ("live", "10", "1000", False), ("paper", "12", "1000", False), ("paper", "10", "900", False)]:
                env = dict(os.environ, PATH=folder+":"+os.environ["PATH"], DESK_MODE="paper", DESK_DAILY_LOSS_PCT=loss, DESK_HAWK_CAPITAL=capital, DESK_BULL_CAPITAL="1000", FAKE_MODE=mode)
                result = subprocess.run(["bash", "-e", "-c", block], env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode == 0, expected, result.stdout+result.stderr)
                self.assertNotIn("1000", result.stdout+result.stderr)
        self.assertNotIn("docker logs", source)

if __name__ == "__main__":
    unittest.main()
