"""F0 passive preflight: uses synthetic dirs and mocked service lists."""
import json
from pathlib import Path

from v3.f0_host_preflight import build_report, examine_sources, _related


def fixtures(tmp_path):
    brain = tmp_path / "brain.sqlite3"
    brain.write_bytes(b"test brain")
    hawk, bull = tmp_path / "hawk", tmp_path / "bull"
    for root in (hawk, bull):
        root.mkdir()
        for name in ("state_v2.json", "trade_history.jsonl",
                     "learning_log.jsonl", "lessons.md"):
            (root / name).write_text("synthetic fixture")
        (root / "archive").mkdir()
        (root / "archive" / "old").mkdir()
    return {"brain": (str(brain), "file"),
            "hawk": (str(hawk), "directory"),
            "bull": (str(bull), "directory")}


def test_passive_preflight_on_stopped_synthetic_services(tmp_path):
    sources = examine_sources(fixtures(tmp_path))
    result = build_report(sources, True, [], True, [])
    assert result["status"] == "PRECHECK_OK_NOT_CERTIFIED"
    assert result["issues"] == []
    assert result["no_backup_or_copy_performed"]
    assert result["no_sqlite_open_or_wal_replay"]


def test_preflight_blocks_related_worker_even_if_files_exist(tmp_path):
    sources = examine_sources(fixtures(tmp_path))
    result = build_report(sources, True, ["superbot-brain-free", "unrelated"],
                          True, [])
    assert result["status"] == "PREFLIGHT_BLOCKED"
    assert result["active_related_container_names"] == ["superbot-brain-free"]
    assert "RELATED_DOCKER_CONTAINERS_RUNNING" in result["issues"]


def test_preflight_blocks_when_service_status_unknown(tmp_path):
    sources = examine_sources(fixtures(tmp_path))
    result = build_report(sources, False, [], False, [])
    assert "DOCKER_STATUS_UNAVAILABLE" in result["issues"]
    assert "SYSTEMD_STATUS_UNAVAILABLE" in result["issues"]
    assert result["status"] == "PREFLIGHT_BLOCKED"


def test_preflight_indicates_wal_and_shm_without_reading_contents(tmp_path):
    src = fixtures(tmp_path)
    db = Path(src["brain"][0])
    Path(str(db) + "-wal").write_bytes(b"committed-frame-synthetic")
    Path(str(db) + "-shm").write_bytes(b"index")
    data = examine_sources(src)
    assert data["brain"]["wal"]["bytes"] == len(b"committed-frame-synthetic")
    assert data["brain"]["shm"]["present"]
    assert data["brain"]["journal"]["present"] is False


def test_preflight_requires_classic_lessons_and_archive(tmp_path):
    src = fixtures(tmp_path)
    root = Path(src["hawk"][0])
    (root / "lessons.md").unlink()
    data = examine_sources(src)
    result = build_report(data, True, [], True, [])
    assert result["status"] == "PREFLIGHT_BLOCKED"
    assert "MANDATORY_FILE_MISSING_OR_UNSAFE_HAWK_LESSONS_MD" in result["issues"]


def test_preflight_catches_symlinked_source_and_archive(tmp_path):
    src = fixtures(tmp_path)
    hawk = Path(src["hawk"][0])
    (hawk / "archive" / "malicious").symlink_to(tmp_path / "brain.sqlite3")
    data = examine_sources(src)
    result = build_report(data, True, [], True, [])
    assert "ARCHIVE_MISSING_OR_UNSAFE_HAWK" in result["issues"]


def test_preflight_flags_running_systemd_worker(tmp_path):
    result = build_report(examine_sources(fixtures(tmp_path)), True, [],
                          True, ["superbot-brain-worker.service"])
    assert result["status"] == "PREFLIGHT_BLOCKED"
    assert "RELATED_SYSTEMD_SERVICES_RUNNING" in result["issues"]


def test_report_excludes_sensitive_file_contents(tmp_path):
    src = fixtures(tmp_path)
    (Path(src["hawk"][0]) / "lessons.md").write_text("PRIVATE_AI_LESSON_DO_NOT_EMIT")
    output = json.dumps(build_report(examine_sources(src), True, [], True, []))
    assert "PRIVATE_AI_LESSON_DO_NOT_EMIT" not in output


def test_brain_adjacent_learning_files_are_inventory_only(tmp_path):
    src = fixtures(tmp_path)
    root = Path(src["brain"][0]).parent
    (root / "memory.jsonl").write_text("HIDDEN_PRIVATE_AI_MEMORY_DO_NOT_EMIT")
    data = examine_sources(src)
    assert data["brain"]["adjacent_memory_candidates"]["memory.jsonl"]["present"]
    output = json.dumps(data)
    assert "HIDDEN_PRIVATE_AI_MEMORY_DO_NOT_EMIT" not in output
    assert "memory.jsonl" in output
