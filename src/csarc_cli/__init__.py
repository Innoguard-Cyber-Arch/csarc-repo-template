"""CSARC repository lifecycle CLI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("csarc-repo-template")
except PackageNotFoundError:
    __version__ = "0.0.0"
