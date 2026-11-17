"""Offline unit checks for bridge socket access policy. No services or network."""
from __future__ import annotations

import stat
from types import SimpleNamespace

import pytest

from backend.v3.arena import close_bridge_server as CBS


@pytest.mark.parametrize("bad", ["", "0", "-1", "+1", " 4", "01", "abc", "2147483648", "1" * 40, 42])
def test_group_gid_refuses_untrusted_config(bad):
    with pytest.raises(RuntimeError, match="arena_socket_gid_invalid"):
        CBS.socket_group_gid({CBS.GROUP_GID_ENV: bad})


def test_group_gid_is_explicit_and_disabled_by_default():
    assert CBS.socket_group_gid({}) is None
    assert CBS.socket_group_gid({CBS.GROUP_GID_ENV: "1400"}) == 1400


class FakePath:
    def __init__(self, *, directory=False, socket=False, uid=0, gid=0, mode=0o700, symlink=False):
        self.directory = directory
        self.socket = socket
        self.uid, self.gid, self.mode, self.symlink = uid, gid, mode, symlink

    def is_symlink(self):
        return self.symlink

    def is_dir(self):
        return self.directory

    def is_socket(self):
        return self.socket

    def stat(self):
        kind = stat.S_IFDIR if self.directory else stat.S_IFSOCK
        return SimpleNamespace(st_uid=self.uid, st_gid=self.gid, st_mode=kind | self.mode)


def test_root_only_parent_stays_private():
    CBS.validate_socket_directory(FakePath(directory=True, mode=0o700), None)
    for mode in (0o710, 0o750, 0o777):
        with pytest.raises(RuntimeError):
            CBS.validate_socket_directory(FakePath(directory=True, mode=mode), None)


def test_explicit_group_requires_exact_root_owned_directory():
    CBS.validate_socket_directory(FakePath(directory=True, uid=0, gid=1400, mode=0o710), 1400)
    for overrides in ({"uid": 99}, {"gid": 0}, {"mode": 0o700},
                      {"mode": 0o750}, {"mode": 0o711}, {"symlink": True}):
        with pytest.raises(RuntimeError):
            CBS.validate_socket_directory(FakePath(**{"directory": True, "gid": 1400, "mode": 0o710, **overrides}), 1400)


@pytest.mark.parametrize("group_gid,expected_gid,expected_mode", [(None, 0, 0o600), (1400, 1400, 0o660)])
def test_socket_permissions_never_open_to_others(monkeypatch, group_gid, expected_gid, expected_mode):
    sock = FakePath(socket=True, uid=0, gid=0, mode=0o777)
    monkeypatch.setattr(CBS.os, "chown", lambda target, uid, gid: setattr(target, "gid", gid))
    monkeypatch.setattr(CBS.os, "chmod", lambda target, mode: setattr(target, "mode", mode))
    CBS.set_socket_permissions(sock, group_gid)
    assert sock.gid == expected_gid
    assert sock.mode == expected_mode
    assert sock.mode & 0o007 == 0


def test_socket_rejects_symlink(monkeypatch):
    sock = FakePath(socket=True, symlink=True)
    monkeypatch.setattr(CBS.os, "chown", lambda *args: pytest.fail("unexpected chown"))
    with pytest.raises(RuntimeError):
        CBS.set_socket_permissions(sock, 1400)
