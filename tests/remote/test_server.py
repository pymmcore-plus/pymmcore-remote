from unittest.mock import MagicMock

import pytest

pytest.importorskip("Pyro5")
from pymmcore_remote.server import RemoteCMMCorePlus, serve  # noqa


def test_server() -> None:
    core = RemoteCMMCorePlus()
    core.loadSystemConfiguration()

    assert core.getDeviceAdapterSearchPaths()
    cb = MagicMock()
    core.connect_client_side_callback(cb)

    core.emit_signal("propertiesChanged")
    core.disconnect_client_side_callback(cb)
