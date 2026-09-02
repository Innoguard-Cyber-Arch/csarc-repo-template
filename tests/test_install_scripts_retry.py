"""Regression tests for curl retry behavior in pinned-tool installers.

These tests run scripts/install-shellcheck against a local HTTP server that
fails the first request and succeeds afterward, proving the installer
survives one transient network failure without weakening checksum
verification (a corrupted download must still be rejected).
"""

from __future__ import annotations

import hashlib
import http.server
import io
import os
import re
import shutil
import subprocess
import tarfile
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
SCRIPT_NAME = "install-shellcheck"
UPSTREAM_BASE_URL = (
    "https://github.com/koalaman/shellcheck/releases/download/v${version}"
)


def _make_retry_once_handler(
    success_body: bytes,
) -> tuple[type[http.server.BaseHTTPRequestHandler], list[int]]:
    """Build a handler failing the first GET with 503, succeeding after."""
    hits: list[int] = []
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            with lock:
                hits.append(1)
                attempt = len(hits)
            if attempt == 1:
                # 503 is one of curl's default retryable transient codes.
                self.send_response(503)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", str(len(success_body)))
            self.end_headers()
            self.wfile.write(success_body)

        def log_message(self, log_format: str, *args: object) -> None:
            return  # keep test output free of default request logging

    return Handler, hits


def _make_always_corrupt_handler(
    body: bytes,
) -> type[http.server.BaseHTTPRequestHandler]:
    """Build a handler that always returns 200 with the wrong bytes."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            # A 200 response is never retried by curl; this stands in for a
            # download that "succeeds" at the HTTP layer but is corrupted.
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, log_format: str, *args: object) -> None:
            return

    return Handler


def _build_shellcheck_archive(version: str, binary_contents: bytes) -> bytes:
    """Build a tar.gz with the internal layout install-shellcheck expects."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(name=f"shellcheck-v{version}/shellcheck")
        info.size = len(binary_contents)
        info.mode = 0o755
        archive.addfile(info, io.BytesIO(binary_contents))
    return buffer.getvalue()


def _installer_version() -> str:
    source = (REPO_ROOT / f"scripts/{SCRIPT_NAME}").read_text(encoding="utf-8")
    match = re.search(r'version="([^"]+)"', source)
    assert match is not None
    return match.group(1)


def _prepare_script_copy(
    tmp_path: Path, server_base_url: str, patched_sha256: str
) -> Path:
    """Copy install-shellcheck into an isolated tree, pointed at a mock host.

    The download host is redirected to ``server_base_url`` and every
    platform's pinned digest is replaced with ``patched_sha256`` so the test
    is independent of which platform branch the host running it selects.
    Everything else -- retry flags, caching, checksum logic, extraction --
    is left exactly as shipped.
    """
    source = (REPO_ROOT / f"scripts/{SCRIPT_NAME}").read_text(encoding="utf-8")
    assert "--retry 3" in source
    assert "--retry-delay 2" in source
    assert "--retry-connrefused" in source

    patched = source.replace(UPSTREAM_BASE_URL, server_base_url)
    assert patched != source, "expected the upstream base URL to be present"
    patched, substitutions = re.subn(
        r'expected_sha256="[0-9a-f]{64}"',
        f'expected_sha256="{patched_sha256}"',
        patched,
    )
    assert substitutions == 4  # one pinned digest per supported platform

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    script_copy = scripts_dir / SCRIPT_NAME
    script_copy.write_text(patched, encoding="utf-8")
    script_copy.chmod(0o755)
    resolve_cache_root = scripts_dir / "resolve-cache-root"
    shutil.copy2(REPO_ROOT / "scripts/resolve-cache-root", resolve_cache_root)
    resolve_cache_root.chmod(0o755)
    return script_copy


def _run_script(
    script_copy: Path, cache_root: Path
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"CSARC_CACHE_ROOT": str(cache_root)}
    return subprocess.run(  # noqa: S603 - repository-owned installer script
        [str(script_copy)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_install_shellcheck_survives_one_transient_curl_failure(
    tmp_path: Path,
) -> None:
    """Retry a transient (503) download failure and still install cleanly."""
    version = _installer_version()
    binary_contents = b"#!/bin/sh\necho fake-shellcheck-for-retry-test\n"
    archive_bytes = _build_shellcheck_archive(version, binary_contents)
    good_sha256 = hashlib.sha256(archive_bytes).hexdigest()

    handler_cls, hits = _make_retry_once_handler(archive_bytes)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        script_copy = _prepare_script_copy(
            tmp_path, f"http://{host}:{port}", good_sha256
        )
        cache_root = tmp_path / ".cache"
        result = _run_script(script_copy, cache_root)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert result.returncode == 0, result.stderr
    assert len(hits) >= 2, "curl should have retried after the first 503"

    binary_path = Path(result.stdout.strip())
    assert binary_path.is_file()
    assert os.access(binary_path, os.X_OK)
    assert binary_path.read_bytes() == binary_contents


def test_install_shellcheck_rejects_a_corrupted_download_despite_retry(
    tmp_path: Path,
) -> None:
    """Never install a download whose bytes fail the pinned checksum."""
    expected_bytes = b"the bytes the server should have sent"
    good_sha256 = hashlib.sha256(expected_bytes).hexdigest()
    corrupted_bytes = b"a different payload standing in for a bad download"

    handler_cls = _make_always_corrupt_handler(corrupted_bytes)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        script_copy = _prepare_script_copy(
            tmp_path, f"http://{host}:{port}", good_sha256
        )
        cache_root = tmp_path / ".cache"
        result = _run_script(script_copy, cache_root)
    finally:
        server.shutdown()
        thread.join(timeout=5)

    assert result.returncode == 1
    assert "does not match the pinned digest" in result.stderr
    installed_binaries = [
        path for path in cache_root.rglob("shellcheck") if path.is_file()
    ]
    assert not installed_binaries, (
        "a corrupted download must never be installed as the shellcheck binary"
    )
