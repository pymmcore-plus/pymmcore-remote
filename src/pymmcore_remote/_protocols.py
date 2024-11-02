from typing import Protocol


class CallbackProtocol(Protocol):
    def receive_server_callback(self, signal_name: str, args: tuple) -> None:
        """Will be called by server with name of signal, and tuple of args."""
