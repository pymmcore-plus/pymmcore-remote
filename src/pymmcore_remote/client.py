from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, cast

import Pyro5.api
from pymmcore_plus.core.events import CMMCoreSignaler
from pymmcore_plus.mda.events import MDASignaler

from . import server
from ._serialize import register_serializers

if TYPE_CHECKING:
    from psygnal import SignalInstance
    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.mda import MDARunner


class MDARunnerProxy(Pyro5.api.Proxy):
    """Proxy for MDARunner object on server."""

    def __init__(self, mda_runner_uri: Any, cb_thread: _DaemonThread) -> None:
        super().__init__(mda_runner_uri)
        events = ClientSideMDASignaler()
        object.__setattr__(self, "events", events)
        cb_thread.api_daemon.register(events)
        self.connect_client_side_callback(events)  # must come after register()

    # this is a lie... but it's more useful than -> Self
    def __enter__(self) -> MDARunner:
        """Use as a context manager."""
        return super().__enter__()  # type: ignore [no-any-return]


class MMCoreProxy(Pyro5.api.Proxy):
    """Proxy for CMMCorePlus object on server."""

    _mda_runner: MDARunnerProxy

    def __init__(
        self,
        host: str = server.DEFAULT_HOST,
        port: int = server.DEFAULT_PORT,
    ) -> None:
        register_serializers()
        uri = f"PYRO:{server.CORE_NAME}@{host}:{port}"
        super().__init__(uri)
        events = ClientSideCMMCoreSignaler()
        object.__setattr__(self, "events", events)

        cb_thread = _DaemonThread(name="CallbackDaemon")
        cb_thread.api_daemon.register(events)
        self.connect_client_side_callback(events)  # must come after register()

        # Retrieve the existing MDARunner URI instead of creating a new one
        mda_runner_uri = self.get_mda_runner_uri()
        object.__setattr__(
            self, "_mda_runner", MDARunnerProxy(mda_runner_uri, cb_thread)
        )
        cb_thread.start()

    # this is a lie... but it's more useful than -> Self
    def __enter__(self) -> CMMCorePlus:
        """Use as a context manager."""
        return super().__enter__()  # type: ignore [no-any-return]

    @property
    def mda(self) -> MDARunner:
        """Return the MDARunner proxy."""
        return self._mda_runner


@Pyro5.api.expose  # type: ignore [misc]
def receive_server_callback(self: Any, signal_name: str, args: tuple) -> None:
    """Will be called by server with name of signal, and tuple of args."""
    signal = cast("SignalInstance", getattr(self, signal_name))
    signal.emit(*args)


class ClientSideCMMCoreSignaler(CMMCoreSignaler):
    """Client-side signaler for CMMCore events."""

    receive_server_callback = receive_server_callback


class ClientSideMDASignaler(MDASignaler):
    """Client-side signaler for MDA events."""

    receive_server_callback = receive_server_callback


class _DaemonThread(threading.Thread):
    def __init__(self, name: str = "DaemonThread"):
        self.api_daemon = Pyro5.api.Daemon()
        self._stop_event = threading.Event()
        super().__init__(target=self.api_daemon.requestLoop, name=name, daemon=True)
