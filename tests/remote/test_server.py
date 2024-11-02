from unittest.mock import MagicMock, patch

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


def test_serve(monkeypatch) -> None:
    import sys

    monkeypatch.setattr(sys, "argv", ["serve", "-p", "65111"])
    with patch("Pyro5.api.serve") as mock:
        serve()
    mock.assert_called_once()
