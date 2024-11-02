from __future__ import annotations

import contextlib
import threading
from typing import TYPE_CHECKING, Any, cast

import Pyro5.api
from psygnal import SignalInstance
from pymmcore_plus.core.events import CMMCoreSignaler
from pymmcore_plus.mda.events import MDASignaler

from . import server
from ._serialize import register_serializers

if TYPE_CHECKING:
    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.mda import MDARunner


class MDARunnerProxy(Pyro5.api.Proxy):
    def __init__(self, host: str, port: int, cb_thread: DaemonThread) -> None:
        uri = f"PYRO:{server.MDA_RUNNER_NAME}@{host}:{port}"
        super().__init__(uri)
        events = ClientSideMDASignaler()
        object.__setattr__(self, "events", events)
        cb_thread.api_daemon.register(events)
        self.connect_client_side_callback(events)  # must come after register()

    # this is a lie... but it's more useful than -> Self
    def __enter__(self) -> MDARunner:
        return super().__enter__()  # type: ignore [no-any-return]


class MMCoreProxy(Pyro5.api.Proxy):
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

        cb_thread = DaemonThread(name="CallbackDaemon")
        cb_thread.api_daemon.register(events)
        self.connect_client_side_callback(events)  # must come after register()

        object.__setattr__(self, "_mda_runner", MDARunnerProxy(host, port, cb_thread))
        cb_thread.start()

    # this is a lie... but it's more useful than -> Self
    def __enter__(self) -> CMMCorePlus:
        return super().__enter__()  # type: ignore [no-any-return]

    @property
    def mda(self) -> MDARunner:
        return self._mda_runner


@Pyro5.api.expose  # type: ignore [misc]
def receive_server_callback(self: Any, signal_name: str, args: tuple) -> None:
    """Will be called by server with name of signal, and tuple of args."""
    signal = cast("SignalInstance", getattr(self, signal_name))
    signal.emit(*args)


class ClientSideCMMCoreSignaler(CMMCoreSignaler):
    receive_server_callback = receive_server_callback


class ClientSideMDASignaler(MDASignaler):
    receive_server_callback = receive_server_callback
# 
# 
class DaemonThread(threading.Thread):
    def __init__(self, name: str = "DaemonThread"):
        self.api_daemon = Pyro5.api.Daemon()
        self._stop_event = threading.Event()
        super().__init__(target=self.api_daemon.requestLoop, name=name, daemon=True)
