from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any
from unittest.mock import Mock

import numpy as np
import Pyro5.api
import Pyro5.core
import pytest
from useq import MDAEvent, MDASequence

from pymmcore_remote import MMCoreProxy, server
from pymmcore_remote.client import ClientSideCMMCoreSignaler

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pymmcore_plus import CMMCorePlus


@pytest.fixture(scope="session")
def server_process() -> Iterator[subprocess.Popen]:
    # create a server in a separate process
    proc = subprocess.Popen([sys.executable, "-m", server.__name__])
    uri = f"PYRO:{Pyro5.core.DAEMON_NAME}@{server.DEFAULT_HOST}:{server.DEFAULT_PORT}"
    remote_daemon = Pyro5.api.Proxy(uri)

    timeout = 4.0
    while timeout > 0:
        try:
            remote_daemon.ping()
            break
        except Exception:
            timeout -= 0.1
            time.sleep(0.1)
    yield proc
    proc.kill()
    proc.wait()


@pytest.fixture
def proxy(server_process: Any) -> Iterator[CMMCorePlus]:
    with MMCoreProxy() as mmcore:
        mmcore.loadSystemConfiguration()
        yield mmcore


def test_client(proxy: CMMCorePlus) -> None:
    assert str(proxy._pyroUri) == server.DEFAULT_URI  # type: ignore
    proxy.getConfigGroupState("Channel")


def test_mda(proxy: CMMCorePlus) -> None:
    mda = MDASequence(time_plan={"interval": 0.1, "loops": 2})

    seq_started_mock = Mock()
    frame_ready_mock = Mock()
    seq_finished_mock = Mock()

    proxy.mda.events.sequenceStarted.connect(seq_started_mock)
    proxy.mda.events.frameReady.connect(frame_ready_mock)
    proxy.mda.events.sequenceFinished.connect(seq_finished_mock)

    proxy.mda.run(mda)
    seq_started_mock.assert_called_once()
    for call in frame_ready_mock.call_args_list:
        assert isinstance(call[0][0], np.ndarray)
        assert isinstance(call[0][1], MDAEvent)
        assert call[0][1].sequence == mda
        assert call[0][1].sequence is not mda
    seq_finished_mock.assert_called_once()


# test canceling while waiting for the next time point
def test_mda_cancel(proxy: CMMCorePlus) -> None:
    mda = MDASequence(time_plan={"interval": 1, "loops": 3})
    assert not proxy.mda.is_running()
    proxy.run_mda(mda)
    time.sleep(0.2)
    assert proxy.mda.is_running()
    proxy.mda.cancel()
    while proxy.mda.is_running():
        time.sleep(0.1)
    assert not proxy.mda.is_running()


# TODO: this test may accidentally pass if qtbot is created before this


def test_cb(proxy: CMMCorePlus) -> None:
    """This tests that we can call a core method within a callback"""
    assert isinstance(proxy.events, ClientSideCMMCoreSignaler)

    mock = Mock()
    proxy.events.systemConfigurationLoaded.connect(mock)
    proxy.loadSystemConfiguration()
    while not mock.called:
        time.sleep(0.1)
    mock.assert_called_once()
