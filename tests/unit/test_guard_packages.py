"""Guard: barred packages (spec 9.2 / SP3)."""

from __future__ import annotations

import sys
import types

import pytest

from sdip._pins import BARRED_MODULES
from sdip.guard.packages import check_barred_packages


def test_no_barred_module_is_importable():
    assert check_barred_packages() == []


def test_zfpy_is_barred():
    assert "zfpy" in BARRED_MODULES


@pytest.mark.parametrize("name", sorted(BARRED_MODULES))
def test_barred_module_is_detected_when_present(name, tmp_path, monkeypatch):
    """NEGATIVE CONTROL: plant an importable module and assert the guard fires.

    A real ``zfpy`` install cannot be created in CI, so a minimal module of the same
    name is planted on ``sys.path``. The guard resolves names, not implementations,
    so this exercises exactly the code path a real install would.
    """
    (tmp_path / f"{name}.py").write_text("VERSION = 'planted for a negative control'\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(name, None)
    from importlib import invalidate_caches

    invalidate_caches()
    try:
        findings = check_barred_packages()
        assert [f.module for f in findings] == [name]
        assert findings[0].origin is not None
    finally:
        sys.modules.pop(name, None)


def test_guard_does_not_import_the_barred_module(tmp_path, monkeypatch):
    """find_spec must locate without executing. An importable zfpy must not run."""
    (tmp_path / "zfpy.py").write_text(
        "raise AssertionError('the guard executed a barred module')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("zfpy", None)
    from importlib import invalidate_caches

    invalidate_caches()
    try:
        findings = check_barred_packages()
        assert [f.module for f in findings] == ["zfpy"]
    finally:
        sys.modules.pop("zfpy", None)


def test_multidimio_lossy_extra_is_not_installed():
    """SP3: the lossy extra pulls zfpy and must not be present."""
    assert "zfpy" not in sys.modules
    import importlib.util

    assert importlib.util.find_spec("zfpy") is None


def test_planted_module_shape_is_a_module(tmp_path, monkeypatch):
    """Sanity check on the control itself, so a broken control cannot pass silently."""
    (tmp_path / "zfpy.py").write_text("x = 1\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    from importlib import import_module, invalidate_caches

    invalidate_caches()
    sys.modules.pop("zfpy", None)
    try:
        assert isinstance(import_module("zfpy"), types.ModuleType)
    finally:
        sys.modules.pop("zfpy", None)
