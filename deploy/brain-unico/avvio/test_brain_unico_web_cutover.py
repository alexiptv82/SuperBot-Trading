"""Funzioni pure del cutover web Brain Unico (nessun Docker, nessuna rete, nessun VPS)."""
import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("bu_cutover", HERE / "brain_unico_web_cutover.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

ENV = {**c.REQUIRED_ENV, "V3_RUN_ID": "brain-v3-paper20261111",
       "V3_JOURNAL_PATH": "/opt/superbot-v3-paper-runs/brain-v3-paper20261111/journal.db",
       "V3_ARENA_READONLY_ENABLED": "1", "JWT_SECRET_PRESENT": "x"}
OLD_UNIT = ("[Service]\nExecStart=/usr/bin/docker run --rm --name superbot-rc84-paper-close-bridge --network none "
            "-v /run/superbot-paper-close:/run/superbot-paper-close:rw "
            "-v /opt/superbot-v3-paper-runs/classic-hawk-paper20261111:/opt/superbot-v3-paper-runs/classic-hawk-paper20261111:rw "
            "-v /opt/superbot-v3-paper-runs/brain-v3-paper20261111:/opt/superbot-v3-paper-runs/brain-v3-paper20261111:rw "
            "-w /app -e V3_CLOSE_BRIDGE_ONLY=1 --entrypoint python3 superbot:rc84-paper-single-close-20261111 "
            "-m backend.v3.close_bridge_server\nRestart=on-failure\n")


def web(mounts):
    return {"Mounts": [{"Destination": d, "Type": "bind", "RW": rw, "Source": s} for d, s, rw in mounts]}


BASE = [("/app/data", "/opt/superbot/data", True), ("/app/backend/.env", "/opt/superbot/backend/.env", False),
        ("/run/superbot-paper-close", "/run/superbot-paper-close", False),
        ("/opt/superbot-v3-paper-runs/brain-v3-paper20261111", "/opt/superbot-v3-paper-runs/brain-v3-paper20261111", False)]


def test_env_switches_only_the_brain_paths_and_keeps_everything_else():
    new = c.target_env(ENV)
    assert new["V3_RUN_ID"] == "brain-unico-paper-rc1"
    assert all(new[k].startswith(c.NEW_RUN + "/") for k in c.new_run_env() if k != "V3_RUN_ID")
    assert {k: v for k, v in new.items() if k not in c.new_run_env()} == {
        k: v for k, v in ENV.items() if k not in c.new_run_env()}


@pytest.mark.parametrize("key", sorted(c.REQUIRED_ENV))
def test_refuses_a_web_without_paper_readonly_and_bridge_gates(key):
    with pytest.raises(c.Refused):
        c.target_env({**ENV, key: "live" if "MODE" in key else "0"})


def test_new_run_mounted_read_only_only_when_not_already_visible():
    w = web(BASE)
    assert c.needs_run_mount(w)
    assert (c.NEW_RUN, "bind", False, c.NEW_RUN) in c.expected_mounts(w)
    args = c.mount_args(w, force_ro=False)
    assert args[-2:] == ["-v", f"{c.NEW_RUN}:{c.NEW_RUN}:ro"]
    assert "-v" in args and "/opt/superbot/data:/app/data:rw" in args          # dati di login invariati (rw)
    assert all(a.endswith(":ro") for a in c.mount_args(w, force_ro=True) if a != "-v")
    parent = web(BASE + [(c.RUN_ROOT, c.RUN_ROOT, False)])
    assert not c.needs_run_mount(parent) and c.expected_mounts(parent) == c.mount_tuples(parent)
    with pytest.raises(c.Refused):
        c.needs_run_mount(web(BASE + [(c.RUN_ROOT, c.RUN_ROOT, True)]))      # mai la run scrivibile nel web
    with pytest.raises(c.Refused):
        c.needs_run_mount(web(BASE + [(c.NEW_RUN, "/tmp/altro", False)]))


def test_bridge_unit_points_to_the_new_run_and_keeps_classic_wallets():
    new = c.bridge_unit_text(OLD_UNIT, "superbot:brain-unico-web-0123456789ab")
    assert "superbot:rc84-paper-single-close-20261111" not in new
    assert "--entrypoint python3 superbot:brain-unico-web-0123456789ab -m backend.v3.close_bridge_server" in new
    assert f"-v {c.NEW_RUN}:{c.NEW_RUN}:rw" in new and c.OLD_BRAIN + ":" not in new
    assert "classic-hawk-paper20261111:rw" in new                              # Falco invariato
    assert "-e V3_BRIDGE_BRAIN_RUN_DIR=brain-v3-unico-paper-rc1 -e V3_BRIDGE_BRAIN_RUN_ID=brain-unico-paper-rc1" in new
    assert new.replace("superbot:brain-unico-web-0123456789ab", "X").count("\n") == OLD_UNIT.count("\n")
    with pytest.raises(c.Refused):
        c.bridge_unit_text(new, "superbot:brain-unico-web-0123456789ab")      # gia' convertita: rifiuto
    with pytest.raises(c.Refused):
        c.bridge_unit_text(OLD_UNIT.replace("brain-v3-paper20261111:/", "x:/"), "superbot:x")
    with pytest.raises(c.Refused):
        c.bridge_unit_text(OLD_UNIT, "superbot:x; rm -rf /")


def test_config_comparison_ignores_only_normalised_defaults():
    old = {"HostConfig": {"Memory": 0, "SecurityOpt": ["no-new-privileges:true"], "NetworkMode": "bridge"},
           "Config": {"User": "", "Cmd": ["python"], "Labels": {}}}
    same = {"HostConfig": {"SecurityOpt": ["no-new-privileges"], "NetworkMode": "default"},
            "Config": {"Cmd": ["python"]}}
    assert c.config_differences(old, same) == []
    assert c.config_differences(old, {**same, "Config": {"Cmd": ["sh"]}}) == ["Config.Cmd"]
    assert set(c.config_differences(old, {**same, "HostConfig": {"Privileged": True}})) == {
        "HostConfig.SecurityOpt", "HostConfig.Privileged"}
