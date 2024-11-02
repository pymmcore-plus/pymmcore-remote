# src/pymmcore_remote/server.py
from functools import partial
from typing import Any

import Pyro5
import Pyro5.api
import Pyro5.errors
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.core.events import CMMCoreSignaler
from pymmcore_plus.mda import MDAEngine, MDARunner
from pymmcore_plus.mda.events import MDASignaler

from ._protocols import CallbackProtocol
from ._serialize import register_serializers
from ._util import wrap_for_pyro


class _CallbackMixin:
    def __init__(self, signal_type: type, events: Any) -> None:
        self._callback_handlers: set[CallbackProtocol] = set()

        for name in {
            name
            for name in dir(signal_type)
            if not name.startswith("_") and name != "all"
        }:
            attr = getattr(events, name)
            if hasattr(attr, "connect"):
                # FIXME: devicePropertyChanged will not work on Remote
                attr.connect(partial(self.emit_signal, name))

    def connect_client_side_callback(self, handler: CallbackProtocol) -> None:
        self._callback_handlers.add(handler)

    def disconnect_client_side_callback(self, handler: CallbackProtocol) -> None:
        self._callback_handlers.discard(handler)

    @Pyro5.api.oneway  # type: ignore [misc]
    def emit_signal(self, signal_name: str, *args: Any) -> None:
        for handler in list(self._callback_handlers):
            try:
                handler._pyroClaimOwnership()  # type: ignore
                handler.receive_server_callback(signal_name, args)
            except Pyro5.errors.CommunicationError:  # pragma: no cover
                self._callback_handlers.discard(handler)


@Pyro5.api.expose
@Pyro5.api.behavior(instance_mode="single")
@wrap_for_pyro
class RemoteCMMCorePlus(CMMCorePlus, _CallbackMixin):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        CMMCorePlus.__init__(self, *args, **kwargs)
        _CallbackMixin.__init__(self, CMMCoreSignaler, self.events)


@Pyro5.api.expose
@wrap_for_pyro
class RemoteMDARunner(MDARunner, _CallbackMixin):
    def __init__(self) -> None:
        MDARunner.__init__(self)
        _CallbackMixin.__init__(self, MDASignaler, self.events)
        self._engine = MDAEngine(CMMCorePlus.instance())


MDA_RUNNER_NAME = "pymmcore.mda.MDARunner"
CORE_NAME = "pymmcore.CMMCorePlus"
DEFAULT_PORT = 54333
DEFAULT_HOST = "127.0.0.1"


def main() -> None:
    """Start a Pyro5 server with a remote CMMCorePlus instance."""
    Pyro5.config.DETAILED_TRACEBACK = True
    register_serializers()
    daemon = Pyro5.api.Daemon(host=DEFAULT_HOST, port=DEFAULT_PORT)
    Pyro5.api.serve(
        objects={
            RemoteCMMCorePlus: CORE_NAME,
            RemoteMDARunner: MDA_RUNNER_NAME,
        },
        daemon=daemon,
        use_ns=False,
        verbose=True,
    )


if __name__ == "__main__":
    main()
