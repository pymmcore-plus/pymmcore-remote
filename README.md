# pymmcore-remote

[![License](https://img.shields.io/pypi/l/pymmcore-remote.svg?color=green)](https://github.com/pymmcore-plus/pymmcore-remote/raw/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/pymmcore-remote.svg?color=green)](https://pypi.org/project/pymmcore-remote)
[![Python Version](https://img.shields.io/pypi/pyversions/pymmcore-remote.svg?color=green)](https://python.org)
[![CI](https://github.com/pymmcore-plus/pymmcore-remote/actions/workflows/ci.yml/badge.svg)](https://github.com/pymmcore-plus/pymmcore-remote/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/pymmcore-plus/pymmcore-remote/branch/main/graph/badge.svg)](https://codecov.io/gh/pymmcore-plus/pymmcore-remote)

**Remote process communication for pymmcore-plus**

-----------

This package provides experimental support for running
[pymmcore-plus](https://github.com/pymmcore-plus/pymmcore-plus) in a remote
process and communicating with it via RPC (currently mediated by
[Pyro5](https://github.com/irmen/Pyro5))

## Installation

For now, please install from the main branch on github:

```bash
pip install git+https://github.com/pymmcore-plus/pymmcore-remote
```

`pymmcore-remote` must be installed on *both* the server (microscope) side, and the client (controller) side.

On the microscope machine, you must also install micromanager device adapters:

```sh
mmcore install
```

More detail available in the
[pymmcore-plus documentation](https://pymmcore-plus.github.io/pymmcore-plus/install/#installing-micro-manager-device-adapters)

## Usage

Start a server on the machine with the microscope:

```sh
mmcore-remote
```

> You can also specify the port with `--port` and the hostname with `--host`.
Run `mmcore-remote --help` for more options.

Then, on the client side (or in a separate process), connect to the server using
using `pymmcore_remote.ClientCMMCorePlus`.  `ClientCMMCorePlus` accepts `host` and `port`
arguments that must match the server (if you override the defaults).

```python
from pymmcore_remote import ClientCMMCorePlus

with ClientCMMCorePlus() as core:
    core.loadSystemConfiguration("path/to/config.cfg")
    # continue using core as you would with pymmcore_plus.CMMCorePlus
```

Commands are serialized and sent to the server, which executes them in the
context of a `CMMCorePlus` object. The results are then serialized and sent
back to the client.

See the [pymmcore-plus documentation](https://pymmcore-plus.github.io/pymmcore-plus/) for standard usage of the CMMCorePlus object.

## Considerations

This package is experimental: The goal is for the API to be identical to that of
`pymmcore-plus`, but there may be some differences, and various serialization
issues may still be undiscovered. Please [open an
issue](https://github.com/pymmcore-plus/pymmcore-remote/issues/new) if you
encounter any problems.

Data is currently shared between processes using python's shared memory module,
which is a fast and efficient way to share memory buffers directly.  However,
this won't work for network access between different machines, so please open
an issue to discuss your use case.
