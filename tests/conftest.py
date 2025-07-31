from __future__ import annotations

import subprocess
import sys
import time
from typing import TYPE_CHECKING, Any

import Pyro5.api
import Pyro5.core
import pytest

from pymmcore_remote import ClientCMMCorePlus, server

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
    with ClientCMMCorePlus() as mmcore:
        mmcore.unloadAllDevices()
        mmcore.loadSystemConfiguration()
        mmcore.waitForSystem()
        yield mmcore
