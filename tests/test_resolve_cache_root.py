"""Regression tests for scripts/resolve-cache-root's default cache location.

These exercise the platform-specific default (macOS vs Linux/WSL2), the
explicit CSARC_CACHE_ROOT override (unchanged precedence), and the
fail-safe fallback to the repo-local .cache/ when the shared, user-level
location cannot be created or is not writable. uname and $HOME/$PATH are
mocked so the suite is independent of the host actually running it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[1]
RESOLVER_NAME = "resolve-cache-root"

# Permission checks below assume a non-root user; root bypasses them.
RUNNING_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


def _install_fake_uname(bin_dir: Path, kernel_name: str) -> None:
    """Put a fake `uname` on PATH that always reports `kernel_name`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_uname = bin_dir / "uname"
    fake_uname.write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' '{kernel_name}'\n",
        encoding="utf-8",
    )
    fake_uname.chmod(0o755)


def _copy_resolver(tmp_path: Path) -> Path:
    """Copy resolve-cache-root into an isolated `<tmp>/repo/scripts/` tree.

    Copying (rather than invoking the checked-out script directly) makes
    the script's own `repo_root` resolve to `tmp_path/repo`, so the
    repo-local `.cache/` fallback lands somewhere the test controls and can
    assert on.
    """
    scripts_dir = tmp_path / "repo" / "scripts"
    scripts_dir.mkdir(parents=True)
    resolver = scripts_dir / RESOLVER_NAME
    shutil.copy2(REPO_ROOT / "scripts" / RESOLVER_NAME, resolver)
    resolver.chmod(0o755)
    return resolver


def _run(
    resolver: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - repository-owned helper script
        [str(resolver)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def _base_env(fake_bin: Path, home: Path) -> dict[str, str]:
    return {"PATH": f"{fake_bin}:/usr/bin:/bin", "HOME": str(home)}


@pytest.mark.parametrize(
    ("kernel_name", "expected_suffix"),
    [
        ("Darwin", "Library/Caches/csarc"),
        ("Linux", ".cache/csarc"),
    ],
)
def test_default_cache_root_is_platform_specific(
    tmp_path: Path, kernel_name: str, expected_suffix: str
) -> None:
    """Prefer the native per-platform, cross-worktree-shared cache."""
    fake_bin = tmp_path / "fakebin"
    _install_fake_uname(fake_bin, kernel_name)
    home = tmp_path / "home"
    home.mkdir()
    resolver = _copy_resolver(tmp_path)

    result = _run(resolver, _base_env(fake_bin, home))

    assert result.returncode == 0, result.stderr
    expected = home / expected_suffix
    assert result.stdout.strip() == str(expected)
    assert expected.is_dir()


def test_linux_default_prefers_xdg_cache_home_when_set(
    tmp_path: Path,
) -> None:
    """Follow the XDG Base Directory convention on Linux/WSL2."""
    fake_bin = tmp_path / "fakebin"
    _install_fake_uname(fake_bin, "Linux")
    home = tmp_path / "home"
    home.mkdir()
    xdg_cache_home = tmp_path / "xdg-cache"
    resolver = _copy_resolver(tmp_path)

    env = _base_env(fake_bin, home)
    env["XDG_CACHE_HOME"] = str(xdg_cache_home)
    result = _run(resolver, env)

    assert result.returncode == 0, result.stderr
    expected = xdg_cache_home / "csarc"
    assert result.stdout.strip() == str(expected)
    assert expected.is_dir()


def test_linux_default_ignores_relative_xdg_cache_home(
    tmp_path: Path,
) -> None:
    """A non-absolute $XDG_CACHE_HOME is invalid; fall back to ~/.cache."""
    fake_bin = tmp_path / "fakebin"
    _install_fake_uname(fake_bin, "Linux")
    home = tmp_path / "home"
    home.mkdir()
    resolver = _copy_resolver(tmp_path)

    env = _base_env(fake_bin, home)
    env["XDG_CACHE_HOME"] = "relative-xdg-cache"
    result = _run(resolver, env)

    assert result.returncode == 0, result.stderr
    expected = home / ".cache" / "csarc"
    assert result.stdout.strip() == str(expected)


def test_csarc_cache_root_override_wins_over_platform_default(
    tmp_path: Path,
) -> None:
    """The explicit override still takes precedence (unchanged behavior)."""
    fake_bin = tmp_path / "fakebin"
    _install_fake_uname(fake_bin, "Darwin")
    home = tmp_path / "home"
    home.mkdir()
    override = tmp_path / "explicit-cache"
    resolver = _copy_resolver(tmp_path)

    env = _base_env(fake_bin, home)
    env["CSARC_CACHE_ROOT"] = str(override)
    result = _run(resolver, env)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(override)
    assert not (home / "Library").exists()


def test_falls_back_to_repo_local_cache_when_shared_location_cannot_be_created(
    tmp_path: Path,
) -> None:
    """Never fail tool installation just because the shared dir is unusable."""
    fake_bin = tmp_path / "fakebin"
    _install_fake_uname(fake_bin, "Linux")
    home = tmp_path / "home"
    home.mkdir()
    # A regular file sits where the shared cache directory needs to go, so
    # `mkdir -p` fails outright -- standing in for "can't be created" for
    # any reason (missing parent, read-only filesystem, and so on).
    (home / ".cache").write_text("not a directory", encoding="utf-8")
    resolver = _copy_resolver(tmp_path)

    result = _run(resolver, _base_env(fake_bin, home))

    assert result.returncode == 0, result.stderr
    repo_local_cache = resolver.parents[1] / ".cache"
    assert result.stdout.strip() == str(repo_local_cache)
    assert repo_local_cache.is_dir()


@pytest.mark.skipif(RUNNING_AS_ROOT, reason="root bypasses permission checks")
def test_falls_back_to_repo_local_cache_when_shared_dir_is_not_writable(
    tmp_path: Path,
) -> None:
    """Fall back when the shared cache root exists but isn't writable."""
    fake_bin = tmp_path / "fakebin"
    _install_fake_uname(fake_bin, "Linux")
    home = tmp_path / "home"
    home.mkdir()
    read_only_cache = home / ".cache" / "csarc"
    read_only_cache.mkdir(parents=True)
    read_only_cache.chmod(0o500)  # exists, but not writable by the owner
    resolver = _copy_resolver(tmp_path)

    try:
        result = _run(resolver, _base_env(fake_bin, home))
    finally:
        read_only_cache.chmod(0o700)  # restore so tmp_path cleanup can run

    assert result.returncode == 0, result.stderr
    repo_local_cache = resolver.parents[1] / ".cache"
    assert result.stdout.strip() == str(repo_local_cache)
    assert repo_local_cache.is_dir()


def test_relative_csarc_cache_root_is_still_rejected(tmp_path: Path) -> None:
    """The existing absolute-path validation for the override is unchanged."""
    fake_bin = tmp_path / "fakebin"
    _install_fake_uname(fake_bin, "Linux")
    home = tmp_path / "home"
    home.mkdir()
    resolver = _copy_resolver(tmp_path)

    env = _base_env(fake_bin, home)
    env["CSARC_CACHE_ROOT"] = "relative-cache"
    result = _run(resolver, env)

    assert result.returncode == 2
    assert "must be an absolute path" in result.stderr
