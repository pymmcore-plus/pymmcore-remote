from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast, overload

import Pyro5.api
import Pyro5.errors
from cachetools import LRUCache
from pymmcore_plus.core.events import CMMCoreSignaler
from pymmcore_plus.mda.events import MDASignaler
from typing_extensions import override

from . import server
from ._serialize import register_serializers

if TYPE_CHECKING:
    from psygnal import SignalInstance
    from pymmcore_plus import CMMCorePlus
    from pymmcore_plus.mda import MDARunner


class MDARunnerProxy(Pyro5.api.Proxy):
    """Proxy for MDARunner object on server."""

    def __init__(self, uri: Pyro5.api.URI | str, connected_socket: Any = None) -> None:
        super().__init__(uri, connected_socket)
        events = ClientSideMDASignaler()
        object.__setattr__(self, "events", events)
        _DaemonThread.instance("CallbackDaemon").api_daemon.register(events)
        self.connect_client_side_callback(events)  # must come after register()

    # this is a lie... but it's more useful than -> Self
    def __enter__(self) -> MDARunner:
        """Use as a context manager."""
        return super().__enter__()  # type: ignore [no-any-return]


class MMCorePlusProxy(Pyro5.api.Proxy):
    """Proxy for CMMCorePlus object on server."""

    _mda_runner: MDARunnerProxy
    _instances: ClassVar[dict[str, MMCorePlusProxy]] = {}

    @classmethod
    def instance(cls, uri: Pyro5.api.URI | str) -> MMCorePlusProxy:
        """Return the instance for the given URI, creating it if necessary."""
        if str(uri) not in cls._instances:
            cls._instances[str(uri)] = cls(uri)
        return cls._instances[str(uri)]

    def __init__(self, uri: Pyro5.api.URI | str, connected_socket: Any = None) -> None:
        register_serializers()
        super().__init__(uri, connected_socket=connected_socket)
        self._instances[str(self._pyroUri)] = self

        # check that the connection is valid
        try:
            self._pyroBind()
        except Pyro5.errors.CommunicationError as e:
            raise ConnectionRefusedError(
                f"Failed to connect to server at {uri}.\n"
                "Is the pymmcore-plus server running? "
                "You can start it with: 'mmcore-remote'"
            ) from e

        # create a proxy object to receive and connect CMMCoreSignaler events
        # here on the client side
        events = ClientSideCMMCoreSignaler()
        object.__setattr__(self, "events", events)
        # listen for callbacks/signals coming from the server
        # and register the callback handler
        _DaemonThread.instance("CallbackDaemon").api_daemon.register(events)
        # connect our local callback handler to the server's signaler
        self.connect_client_side_callback(events)  # must come after register()

    # this is a lie... but it's more useful than -> Self
    def __enter__(self) -> CMMCorePlus:
        """Use as a context manager."""
        return super().__enter__()  # type: ignore [no-any-return]


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
    _instances: ClassVar[dict[str, _DaemonThread]] = {}

    @classmethod
    def instance(cls, name: str = "DaemonThread") -> _DaemonThread:
        if name not in cls._instances:
            cls._instances[name] = cls(name)
        return cls._instances[name]

    def __init__(self, name: str = "DaemonThread") -> None:
        self.api_daemon = Pyro5.api.Daemon()
        self._stop_event = threading.Event()
        super().__init__(target=self.api_daemon.requestLoop, name=name, daemon=True)
        self.start()


PT = TypeVar("PT", bound=Pyro5.api.Proxy)


class ProxyHandler(ABC, Generic[PT]):
    """A wrapper around multiple Pyro proxies.

    PyMMCore objects are often used in their own event callbacks. This presents a
    problem for Pyro objects, as these callbacks are executed by Pyro worker threads,
    which will need ownership over their own proxy. Thus handling PyMMCore object
    callbacks requires organized transfer of multiple proxy objects - that is the goal
    of this class.
    """

    _instances: ClassVar[dict[str, ProxyHandler]] = {}

    @property
    @abstractmethod
    def _proxy_type(self) -> type[PT]:
        """Return the proxy type handled by this class."""
        ...

    @classmethod
    def instance(cls, uri: Pyro5.api.URI | str | None = None) -> Any:
        """Return the instance for the given URI, creating it if necessary."""
        key = str(uri)
        if key not in cls._instances:
            cls._instances[key] = cls(uri)
        return cls._instances[key]

    def __init__(self, uri: Pyro5.api.URI | str, connected_socket: Any = None) -> None:
        self._connected_socket = connected_socket
        self._uri = uri
        # FIXME: There are many reasons why a cache with maximum capacity is a bad idea.
        # First, there seems no reasonable maximum size. (Currently it's just a magic
        # number). Second, there seems no reasonable eviction policy. LRU could be
        # problematic if there are (maxsize) event callbacks. Suppose maxsize=2 - if you
        # call snapImage on a CMMCorePlus proxy, and there are two imageSnapped
        # callbacks, the second callback would then try to evict the original proxy held
        # by the snapImage caller (assuming different Pyro worker threads for each
        # callback). MRU might actually be most reasonable in this case...
        self._proxy_cache: LRUCache[threading.Thread, PT] = LRUCache(maxsize=4)
        self._proxy_lock = threading.Lock()
        self._instances[str(self._uri)] = self

    def _proxy_attr(self, name: str) -> Any:
        """Retrieves an attribute on the appropriate proxy object for this thread."""
        cache = self._proxy_cache
        thread = threading.current_thread()
        if thread not in cache:
            with self._proxy_lock:
                if len(cache) < cache.maxsize:
                    # Cache not full - we can just add a new one
                    proxy = self._proxy_type(
                        uri=self._uri, connected_socket=self._connected_socket
                    )
                else:
                    # Cache full - repurpose lru proxy for the current thread
                    _lru_thread, proxy = cache.popitem()
                    proxy._pyroClaimOwnership()
                # Insert the new thread-proxy mapping
                cache[thread] = proxy

        # Delegate the call this thread's proxy
        attr = getattr(cache[thread], name)
        return attr

    # Note this method must exist explicitly to enable context manager behavior
    def __enter__(self) -> Any:
        """Use as a context manager."""
        return self._proxy_attr("__enter__")()

    # Note this method must exist explicitly to enable context manager behavior
    def __exit__(
        self, exc_type: type | None, exc_value: Exception | None, traceback: str | None
    ) -> None:
        """Use as a context manager."""
        self._proxy_attr("__exit__")(
            exc_type=exc_type, exc_value=exc_value, traceback=traceback
        )

    def __getattr__(self, name: str) -> Any:
        """Delegate to an appropriate MMCorePlusProxy."""
        return self._proxy_attr(name)


class ClientMDARunner(ProxyHandler[MDARunnerProxy]):
    """A handle on a CMMCorePlus instance running outside of this process."""

    @property
    def _proxy_type(self) -> type[MDARunnerProxy]:
        return MDARunnerProxy


# TODO: Consider adding CMMCorePlus as supertype
class ClientCMMCorePlus(ProxyHandler[MMCorePlusProxy]):
    """A handle on a CMMCorePlus instance running outside of this process."""

    @overload
    def __init__(
        self,
        *,
        port: int,
        object_id: str | None = None,
        host: str | None = None,
        connected_socket: Any = None,
    ) -> None: ...
    @overload
    def __init__(
        self,
        uri: Pyro5.api.URI | str,
        *,
        connected_socket: Any = None,
    ) -> None: ...
    def __init__(
        self,
        uri: Pyro5.api.URI | str | None = None,
        *,
        object_id: str | None = None,
        host: str | None = None,
        port: int | None = None,
        connected_socket: Any = None,
    ) -> None:
        if uri is None:
            object_id = server.CORE_NAME if object_id is None else object_id
            host = server.DEFAULT_HOST if host is None else host
            port = server.DEFAULT_PORT if port is None else port
            uri = f"PYRO:{object_id}@{host}:{port}"
        super().__init__(uri=uri, connected_socket=connected_socket)

        # Create a proxy handler for the mda runner so it too can receive server signals
        self.mda = ClientMDARunner(uri=self.get_mda_runner_uri())

    @property
    def _proxy_type(self) -> type[MMCorePlusProxy]:
        return MMCorePlusProxy

    # Overridden to provide a nice (although tehcnically wrong) type hint :)
    @override
    def __enter__(self) -> CMMCorePlus:
        """Use as a context manager."""
        super().__enter__()
        return cast("CMMCorePlus", self)
