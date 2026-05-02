"""wispy -- Minimal local push-to-talk dictation tool."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("wispy")
except PackageNotFoundError:
    __version__ = "unknown"
