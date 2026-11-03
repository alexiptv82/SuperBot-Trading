"""Tests for a fixed-command, low-privilege metadata-only agent."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "restricted_status", HERE / "restricted_status.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class RestrictedStatusTests(unittest.TestCase):
    def test_metadata_never_reads_file_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brain.sqlite3"
            path.write_text("PRIVATE_SESSION_DATA_NEVER_LOG")
            self.assertEqual(agent.metadata(path)["bytes"], path.stat().st_size)
            self.assertEqual(agent.metadata(path)["status"], "PRESENT")
            with patch("builtins.open", side_effect=AssertionError("MUST_NOT_READ")):
                self.assertEqual(agent.metadata(path)["status"], "PRESENT")

    def test_link_to_sensitive_file_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            actual = Path(tmp) / "secret"
            actual.write_text("secret")
            link = Path(tmp) / "link"
            link.symlink_to(actual)
            self.assertEqual(agent.metadata(link)["status"], "UNSAFE_SYMLINK")

    def test_missing_files_fail_as_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(
                agent.metadata(Path(tmp) / "nonexistent")["status"],
                "UNAVAILABLE",
            )

    def test_systemd_only_returns_aggregate_not_arguments(self):
        sample = (
            "superbot-brain.service loaded active running confidential-data\\n"
            "cron.service loaded active running Cron\\n"
        )
        p = types.SimpleNamespace(returncode=0, stdout=sample)
        with patch.object(agent.subprocess, "run", return_value=p):
            summary = agent.services()
        self.assertEqual(summary, {"status": "POSSIBLE_ACTIVE", "matching_count": 1})
        self.assertNotIn("confidential-data", str(summary))

    def test_processes_return_counts_without_commands(self):
        data = (
            "1900 /usr/bin/superbot confidential-token=NEVER_PRINT\\n"
            "1901 /usr/bin/python3 private.py\\n"
        )
        p = types.SimpleNamespace(returncode=0, stdout=data)
        with patch.object(agent.subprocess, "run", return_value=p), \\
             patch.object(agent.os, "getpid", return_value=9000):
            summary = agent.processes()
        self.assertEqual(summary["matching_count"], 1)
        self.assertNotIn("NEVER_PRINT", str(summary))

    def test_unavailable_service_checks_are_unknown_not_ok(self):
        p = types.SimpleNamespace(returncode=1, stdout="")
        with patch.object(agent.subprocess, "run", return_value=p):
            self.assertEqual(agent.services()["status"], "UNKNOWN")
            self.assertEqual(agent.processes()["status"], "UNKNOWN")

    def test_refuses_root_even_if_forced_command_is_misconfigured(self):
        capture = io.StringIO()
        with patch.object(agent.os, "geteuid", return_value=0), \\
             patch.object(agent, "collect", side_effect=AssertionError("not called")), \\
             patch("sys.stdout", capture):
            rc = agent.main()
        self.assertEqual(rc, 3)
        self.assertIn("REFUSED_ROOT_EXECUTION", capture.getvalue())

    def test_collect_cannot_report_backup_certified(self):
        with tempfile.TemporaryDirectory() as tmp:
            # No real source paths or host services are accessed in this test.
            with patch.object(agent, "SOURCE", Path(tmp)), \\
                 patch.object(agent, "CLASSICS", Path(tmp)), \\
                 patch.object(agent, "BACKUPS", Path(tmp)), \\
                 patch.object(agent, "services", return_value={"status": "UNKNOWN"}), \\
                 patch.object(agent, "processes", return_value={"status": "UNKNOWN"}):
                report = agent.collect()
            self.assertEqual(report["status"], "OBSERVATION_ONLY")
            self.assertTrue(report["not_a_backup_certificate"])
            self.assertTrue(report["read_only"])


if __name__ == "__main__":
    unittest.main()
