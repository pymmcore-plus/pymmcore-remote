from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import Mock

import numpy as np
from pymmcore_plus import DeviceProperty
from useq import MDAEvent, MDASequence

from pymmcore_remote import server
from pymmcore_remote.client import ClientSideCMMCoreSignaler

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus


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
    frame_ready_mock.assert_called()
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


def test_cb(proxy: CMMCorePlus) -> None:
    """This tests that we can call a core method within a callback"""
    assert isinstance(proxy.events, ClientSideCMMCoreSignaler)

    mock = Mock()
    proxy.events.systemConfigurationLoaded.connect(mock)
    proxy.loadSystemConfiguration()
    while not mock.called:
        time.sleep(0.1)
    mock.assert_called_once()


def test_core_api(proxy: CMMCorePlus) -> None:
    """Test many of the core API methods."""
    props = list(proxy.iterProperties())
    assert props
    assert all(isinstance(prop, DeviceProperty) for prop in props)
    assert all(prop.isValid() for prop in props)

    props2 = list(proxy.iterProperties(as_object=False))
    assert props2
    # !! it should be a tuple, but it looks like pyro deserializes it as a list
    assert all(isinstance(prop, list) for prop in props2)

    _prop3 = proxy.getProperty("Objective", "Label")
    _prop4 = proxy.getPropertyObject("Objective", "Label")

    # will fail https://github.com/pymmcore-plus/pymmcore-remote/issues/2
    # assert _prop4.value == _prop3
    # assert isinstance(proxy.getPropertyType("Objective", "Label"), PropertyType)
