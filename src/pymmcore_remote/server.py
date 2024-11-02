# src/pymmcore_remote/server.py
from collections.abc import Iterable, Sequence
from functools import partial
from typing import Any, Protocol

import Pyro5
import Pyro5.api
import Pyro5.core
import Pyro5.errors
from click import Path
from pymmcore_plus import CMMCorePlus
from pymmcore_plus.core.events import CMMCoreSignaler
from pymmcore_plus.mda import MDAEngine, MDARunner
from pymmcore_plus.mda.events import MDASignaler
from useq import MDAEvent

from ._serialize import register_serializers
from ._util import wrap_for_pyro

MDA_RUNNER_NAME = "pymmcore.mda.MDARunner"
CORE_NAME = "pymmcore.CMMCorePlus"
DEFAULT_PORT = 54333
DEFAULT_HOST = "127.0.0.1"
DEFAULT_URI = f"PYRO:{CORE_NAME}@{DEFAULT_HOST}:{DEFAULT_PORT}"


class ClientSideCallbackHandler(Protocol):
    """Protocol for callback handlers on the client side."""

    def receive_server_callback(self, signal_name: str, args: tuple) -> None:
        """Will be called by server with name of signal, and tuple of args."""


class _CallbackMixin:
    def __init__(self, signal_type: type, events: Any) -> None:
        self._callback_handlers: set[ClientSideCallbackHandler] = set()

        for name in {
            name
            for name in dir(signal_type)
            if not name.startswith("_") and name != "all"
        }:
            attr = getattr(events, name)
            if hasattr(attr, "connect"):
                # FIXME: devicePropertyChanged will not work on Remote
                attr.connect(partial(self.emit_signal, name))

    def connect_client_side_callback(self, handler: ClientSideCallbackHandler) -> None:
        self._callback_handlers.add(handler)

    def disconnect_client_side_callback(
        self, handler: ClientSideCallbackHandler
    ) -> None:
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
    """CMMCorePlus with Pyro5 serialization."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        CMMCorePlus.__init__(self, *args, **kwargs)
        _CallbackMixin.__init__(self, CMMCoreSignaler, self.events)
        self._mda_runner = RemoteMDARunner()
        if DAEMON:
            self._mda_runner_uri = DAEMON.register(
                self._mda_runner, "existing_mda_runner"
            )

    def get_mda_runner_uri(self) -> Pyro5.core.URI:
        """Return the URI of the remote MDARunner instance."""
        return self._mda_runner_uri

    def run_mda(  # type: ignore [override]
        self,
        events: Iterable[MDAEvent],
        *,
        output: Path | str | object | Sequence[Path | str | object] | None = None,
        block: bool = False,
    ) -> None:
        """Run an MDA sequence in another thread on the server side."""
        # overriding to return None, so as not to serialize the thread object
        super().run_mda(events, output=output, block=block)


@Pyro5.api.expose
@Pyro5.api.behavior(instance_mode="single")
@wrap_for_pyro
class RemoteMDARunner(MDARunner, _CallbackMixin):
    """MDARunner with Pyro5 serialization."""

    def __init__(self) -> None:
        MDARunner.__init__(self)
        _CallbackMixin.__init__(self, MDASignaler, self.events)
        self._engine = MDAEngine(CMMCorePlus.instance())


DAEMON: Pyro5.api.Daemon | None = None


def serve() -> None:
    """Start a Pyro5 server with a remote CMMCorePlus instance."""
    global DAEMON
    Pyro5.config.DETAILED_TRACEBACK = True
    register_serializers()
    DAEMON = Pyro5.api.Daemon(host=DEFAULT_HOST, port=DEFAULT_PORT)
    Pyro5.api.serve(
        objects={
            RemoteCMMCorePlus: CORE_NAME,
            # RemoteMDARunner: MDA_RUNNER_NAME,
        },
        daemon=DAEMON,
        use_ns=False,
        verbose=True,
    )


if __name__ == "__main__":
    serve()
