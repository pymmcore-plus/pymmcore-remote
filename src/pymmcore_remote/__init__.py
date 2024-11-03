"""RPC for pymmcore-plus."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pymmcore-remote")
except PackageNotFoundError:
    __version__ = "uninstalled"
__author__ = "Talley Lambert"
__email__ = "talley.lambert@gmail.com"

from .client import MMCorePlusProxy
from .server import serve, server_process

__all__ = ["MMCorePlusProxy", "serve", "server_process"]
