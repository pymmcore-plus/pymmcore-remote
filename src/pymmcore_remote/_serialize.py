from __future__ import annotations

import atexit
import contextlib
import datetime
import re
from abc import ABC, abstractmethod
from collections import deque
from enum import IntEnum
from functools import lru_cache
from multiprocessing.shared_memory import SharedMemory
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeVar, cast

import numpy as np
import pymmcore
import Pyro5
import Pyro5.api
import useq
from pymmcore_plus import ConfigGroup, Device, DeviceAdapter
from pymmcore_plus.core import Configuration, DeviceProperty, Metadata, _constants
from Pyro5 import serializers

if TYPE_CHECKING:
    from collections.abc import Sized

T = TypeVar("T")

# --------------------- START CUSTOM SERIALIZER ---------------------

# https://github.com/pymmcore-plus/pymmcore-remote/issues/2
# because Pyro5 doesn't reserialize IntEnums as IntEnums, we need to do it ourselves

# find all the IntEnum classes in _constants
INT_ENUMS: tuple[type[IntEnum], ...] = tuple(
    obj
    for name in dir(_constants)
    if isinstance((obj := getattr(_constants, name)), type) and issubclass(obj, IntEnum)
)


class PymmcoreSerializer(serializers.MsgpackSerializer):
    serializer_id = 199

    # override the default serializer to turn IntEnums into dicts
    def dumps(self, data: Any) -> Any:
        if isinstance(data, IntEnum):
            data = {
                "__class__": f"{data.__class__.__module__}.{data.__class__.__name__}",
                "value": data.value,
            }
        return super().dumps(data)


# then register a custom dict-to-enum function to reserialize the dict into an IntEnum
def _dict_to_enum(classname: str, dct: dict) -> IntEnum:
    mod_name, class_name = classname.rsplit(".", 1)
    cls = getattr(__import__(mod_name, fromlist=[class_name]), class_name)
    return cast("type[IntEnum]", cls)(dct["value"])


for obj in INT_ENUMS:
    PymmcoreSerializer.register_dict_to_class(
        f"{obj.__module__}.{obj.__name__}", _dict_to_enum
    )

# --------------------- END CUSTOM SERIALIZER ---------------------

# register our custom serializer

PYMMCORE_SERIALIZER = "pymmcore-serializer"
serializer = PymmcoreSerializer()
serializers.serializers[PYMMCORE_SERIALIZER] = serializer
serializers.serializers_by_id[PymmcoreSerializer.serializer_id] = serializer


class Serializer(ABC, Generic[T]):
    # define these in subclasses

    @abstractmethod
    def to_dict(self, obj: T) -> dict: ...

    @abstractmethod
    def from_dict(self, classname: str, dct: dict) -> T: ...

    # -----------------

    @classmethod
    def type_(cls) -> type:
        return cls.__orig_bases__[0].__args__[0]  # type: ignore

    def _to_dict_(self, obj: T) -> dict:
        return {**self.to_dict(obj), "__class__": self.type_key()}

    def _from_dict_(self, classname: str, d: dict) -> T:
        d.pop("__class__", None)
        return self.from_dict(classname, d)

    @classmethod
    def register(cls) -> None:
        ser = cls()
        Pyro5.api.register_class_to_dict(cls.type_(), ser._to_dict_)
        Pyro5.api.register_dict_to_class(cls.type_key(), ser._from_dict_)

    @classmethod
    def type_key(cls) -> str:
        return f"{cls.type_().__module__}.{cls.type_().__name__}"


class SerMDASequence(Serializer[useq.MDASequence]):
    def to_dict(self, obj: useq.MDASequence) -> dict:
        return obj.model_dump(mode="json")

    def from_dict(self, classname: str, d: dict) -> useq.MDASequence:
        return useq.MDASequence.model_validate(d)


class SerDeviceProperty(Serializer[DeviceProperty]):
    def to_dict(self, obj: DeviceProperty) -> dict:
        from .server._server import CORE_NAME, GLOBAL_DAEMON

        return {
            "device_label": obj.device,
            "property_name": obj.name,
            # get URI for the device.core
            # FIXME: i don't think this is the right approach, we may be registering
            # the same object multiple times
            "core_uri": GLOBAL_DAEMON and GLOBAL_DAEMON.uriFor(CORE_NAME),
        }

    def from_dict(self, classname: str, d: dict) -> DeviceProperty:
        from pymmcore_remote.client import ClientCMMCorePlus

        # TODO: not sure if this is the best way to get the remote core object
        core_uri = d.pop("core_uri")
        core = ClientCMMCorePlus.instance(core_uri)
        return DeviceProperty(**d, mmcore=core)


class SerDeviceAdapter(Serializer[DeviceAdapter]):
    def to_dict(self, obj: DeviceAdapter) -> dict:
        from .server._server import CORE_NAME, GLOBAL_DAEMON

        return {
            "library_name": obj.name,
            "core_uri": GLOBAL_DAEMON and GLOBAL_DAEMON.uriFor(CORE_NAME),
        }

    def from_dict(self, classname: str, d: dict) -> DeviceAdapter:
        from pymmcore_remote.client import ClientCMMCorePlus

        core_uri = d.pop("core_uri")
        core = ClientCMMCorePlus.instance(core_uri)
        return DeviceAdapter(**d, mmcore=core)


class SerDevice(Serializer[Device]):
    def to_dict(self, obj: Device) -> dict:
        from .server._server import CORE_NAME, GLOBAL_DAEMON

        return {
            "device_label": obj.label,
            "core_uri": GLOBAL_DAEMON and GLOBAL_DAEMON.uriFor(CORE_NAME),
        }

    def from_dict(self, classname: str, d: dict) -> Device:
        from pymmcore_remote.client import ClientCMMCorePlus

        core_uri = d.pop("core_uri")
        core = ClientCMMCorePlus.instance(core_uri)
        return Device.create(d["device_label"], mmcore=core)


class SerRePattern(Serializer[re.Pattern]):
    def to_dict(self, obj: re.Pattern) -> dict:
        return {"pattern": obj.pattern}

    def from_dict(self, classname: str, d: dict) -> re.Pattern:
        return re.compile(d["pattern"])


class SerConfigGroup(Serializer[ConfigGroup]):
    def to_dict(self, obj: ConfigGroup) -> dict:
        from .server._server import CORE_NAME, GLOBAL_DAEMON

        return {
            "group_name": obj._name,
            "core_uri": GLOBAL_DAEMON and GLOBAL_DAEMON.uriFor(CORE_NAME),
        }

    def from_dict(self, classname: str, d: dict) -> ConfigGroup:
        from pymmcore_remote.client import ClientCMMCorePlus

        core_uri = d.pop("core_uri")
        core = ClientCMMCorePlus.instance(core_uri)
        return ConfigGroup(**d, mmcore=core)


class SerMDAEvent(Serializer[useq.MDAEvent]):
    def to_dict(self, obj: useq.MDAEvent) -> dict:
        return obj.model_dump(mode="json")

    def from_dict(self, classname: str, d: dict) -> useq.MDAEvent:
        return useq.MDAEvent.model_validate(d)


class SerConfiguration(Serializer[Configuration]):
    def to_dict(self, obj: Configuration) -> dict:
        return obj.dict()

    def from_dict(self, classname: str, d: dict) -> Configuration:
        return Configuration.create(**d)


class SerMetadata(Serializer[Metadata]):
    def to_dict(self, obj: Metadata) -> dict:
        return dict(obj)

    def from_dict(self, classname: str, d: dict) -> Metadata:
        return Metadata(**d)


class SerTimeDelta(Serializer[datetime.timedelta]):
    def to_dict(self, obj: datetime.timedelta) -> dict:
        return {"val": str(obj)}

    def from_dict(self, classname: str, d: dict) -> datetime.timedelta:
        return datetime.timedelta(d["val"])


class SerCMMError(Serializer[pymmcore.CMMError]):
    def to_dict(self, obj: pymmcore.CMMError) -> dict:
        try:
            msg = obj.getMsg()
        except Exception:  # pragma: no cover
            msg = ""
        return {"msg": msg}

    def from_dict(self, classname: str, d: dict) -> pymmcore.CMMError:
        return pymmcore.CMMError(str(d.get("msg")))


def remove_shm_from_resource_tracker() -> None:
    """Monkey-patch multiprocessing.resource_tracker so SharedMemory won't be tracked.

    More details at: https://github.com/python/cpython/issues/82300
    """
    from multiprocessing import resource_tracker

    def fix_register(name: Sized, rtype: str) -> None:  # pragma: no cover
        if rtype == "shared_memory":
            return
        resource_tracker._resource_tracker.register(name, rtype)

    resource_tracker.register = fix_register

    def fix_unregister(name: Sized, rtype: str) -> None:  # pragma: no cover
        if rtype == "shared_memory":
            return
        return resource_tracker._resource_tracker.unregister(name, rtype)

    resource_tracker.unregister = fix_unregister

    if "shared_memory" in resource_tracker._CLEANUP_FUNCS:  # type: ignore [attr-defined]
        del resource_tracker._CLEANUP_FUNCS["shared_memory"]  # type: ignore [attr-defined]


def register_numpy_serializer() -> None:
    # if we're using msgpack, check for msgpack_numpy to serialize numpy arrays
    if Pyro5.config.SERIALIZER == "msgpack":
        with contextlib.suppress(ImportError):
            import msgpack_numpy

            msgpack_numpy.patch()
            return

    # otherwise use shared memory, which will fail over the network
    class SerNDArray(Serializer[np.ndarray]):
        SHM_SENT: ClassVar[deque[SharedMemory]] = deque(maxlen=15)

        def to_dict(self, obj: np.ndarray) -> dict:
            shm = SharedMemory(create=True, size=obj.nbytes)
            SerNDArray.SHM_SENT.append(shm)
            b: np.ndarray = np.ndarray(obj.shape, dtype=obj.dtype, buffer=shm.buf)
            b[:] = obj[:]
            return {
                "shm": shm.name,
                "shape": obj.shape,
                "dtype": str(obj.dtype),
            }

        def from_dict(self, classname: str, d: dict) -> np.ndarray:
            """Convert dict from `ndarray_to_dict` back to np.ndarray."""
            shm = SharedMemory(name=d["shm"], create=False)
            array: np.ndarray = np.ndarray(
                d["shape"], dtype=d["dtype"], buffer=shm.buf
            ).copy()
            shm.close()
            shm.unlink()
            return array

    @atexit.register  # pragma: no cover
    def _cleanup() -> None:
        for shm in SerNDArray.SHM_SENT:
            shm.close()
            with contextlib.suppress(FileNotFoundError):
                shm.unlink()

    remove_shm_from_resource_tracker()
    SerNDArray.register()


@lru_cache  # only register once
def register_serializers() -> None:
    # use our custom serializer
    Pyro5.config.SERIALIZER = PYMMCORE_SERIALIZER

    register_numpy_serializer()
    for i in globals().values():
        if isinstance(i, type) and issubclass(i, Serializer) and i != Serializer:
            i.register()
