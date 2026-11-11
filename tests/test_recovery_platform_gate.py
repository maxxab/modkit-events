"""Portable refusal checks; no patched acceptance or native-runtime claims."""

import os
from types import SimpleNamespace

import pytest
from recovery_test_support import RECOVERY_HOST

from modkit_events.persistence import _resource_io as resource
from modkit_events.persistence import recovery_profile as profile
from modkit_events.persistence.errors import ErrorCode, PersistenceError


def _assert_profile_refusal(monkeypatch):
    def forbidden():
        raise AssertionError("unsupported host reached accounting after the profile gate")

    monkeypatch.setattr(profile, "_recovery_preparation_min", forbidden)
    with pytest.raises(PersistenceError) as caught:
        profile.recovery_requirements(readiness=object())
    assert caught.value.code is ErrorCode.PROFILE_REJECTED
    assert caught.value.unconfirmed is False


def test_required_ci_profile_cannot_silently_skip():
    if os.environ.get("MODKIT_CI_RECOVERY_PROFILE") == "1":
        assert RECOVERY_HOST, "exact recovery CI lane does not match its declared host"
        assert profile._layout().startswith("cpython-")


@pytest.mark.skipif(RECOVERY_HOST, reason="this host has an accepted recovery profile")
def test_actual_unsupported_host_refuses_before_accounting(monkeypatch):
    _assert_profile_refusal(monkeypatch)


@pytest.mark.parametrize("version", [(3, 12, 14), (3, 13, 6), (3, 14, 0), (3, 15, 0)])
def test_other_patch_and_minor_versions_refuse_before_accounting(monkeypatch, version):
    monkeypatch.setattr(profile.sys, "platform", "linux")
    monkeypatch.setattr(profile.sys, "version_info", version)
    _assert_profile_refusal(monkeypatch)


@pytest.mark.parametrize("platform_name", ["win32", "darwin"])
def test_other_platforms_refuse_before_accounting(monkeypatch, platform_name):
    monkeypatch.setattr(profile.sys, "version_info", (3, 12, 3))
    monkeypatch.setattr(profile.sys, "platform", platform_name)
    _assert_profile_refusal(monkeypatch)


def test_non_posix_resource_backend_refuses_before_open(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("unsupported resource backend attempted filesystem I/O")

    monkeypatch.setattr(resource, "os", SimpleNamespace(name="nt", open=forbidden))
    with pytest.raises(ValueError, match="^unsupported migration resource backend$"):
        resource.PosixLease("unused")
