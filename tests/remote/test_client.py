from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING

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
    from pytestqt.qtbot import QtBot


@pytest.fixture(scope="session")
def server_process() -> subprocess.Popen:
    # create a server in a separate process
    proc = subprocess.Popen([sys.executable, "-m", server.__name__])
    uri = f"PYRO:{Pyro5.core.DAEMON_NAME}@{server.DEFAULT_HOST}:{server.DEFAULT_PORT}"
    remote_daemon = Pyro5.api.Proxy(uri)

    timeout = 4
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
def proxy(server_process) -> Iterator[CMMCorePlus]:
    with MMCoreProxy() as mmcore:
        mmcore.loadSystemConfiguration()
        yield mmcore


def test_client(proxy: CMMCorePlus) -> None:
    assert str(proxy._pyroUri) == server.DEFAULT_URI
    proxy.getConfigGroupState("Channel")


def test_mda(qtbot: QtBot, proxy: CMMCorePlus) -> None:
    mda = MDASequence(time_plan={"interval": 0.1, "loops": 2})

    def _check_frame(img, event):
        return (
            isinstance(img, np.ndarray)
            and isinstance(event, MDAEvent)
            and event.sequence == mda
            and event.sequence is not mda
        )

    def _check_seq(obj):
        return obj.uid == mda.uid

    signals = [
        (proxy.mda.events.sequenceStarted, "started"),
        (proxy.mda.events.frameReady, "frameReady1"),
        (proxy.mda.events.frameReady, "frameReady2"),
        (proxy.mda.events.sequenceFinished, "finishd"),
    ]
    checks = [_check_seq, _check_frame, _check_frame, _check_seq]

    with qtbot.waitSignals(signals, check_params_cbs=checks, order="strict"):
        thread = proxy.run_mda(mda)
    thread.join()
    breakpoint()


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


def test_cb_without_qt(qtbot: QtBot, proxy: CMMCorePlus) -> None:
    """This tests that we can call a core method within a callback

    currently only works for Qt callbacks... need to figure out synchronous approach.
    """
    assert isinstance(proxy.events, ClientSideCMMCoreSignaler)
    cam = [None]

    @proxy.events.systemConfigurationLoaded.connect
    def _cb() -> None:
        cam[0] = proxy.getCameraDevice()

    with qtbot.waitSignal(proxy.events.systemConfigurationLoaded, timeout=500):
        proxy.loadSystemConfiguration()
    assert cam[0] == "Camera"


# def test_cb_with_qt(qtbot, proxy):
#     """This tests that we can call a core method within a callback

#     currently only works for Qt callbacks... need to figure out synchronous approach.
#     """
#     # because we're running with qt active
#     assert isinstance(proxy.events, QCoreSignaler)
#     cam = [None]

#     @proxy.events.systemConfigurationLoaded.connect
#     def _cb():
#         cam[0] = proxy.getCameraDevice()

#     with qtbot.waitSignal(proxy.events.systemConfigurationLoaded):
#         proxy.loadSystemConfiguration()
#     assert cam[0] == "Camera"
