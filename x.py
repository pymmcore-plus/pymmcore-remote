import numpy as np
from useq import MDAEvent, MDASequence, TIntervalLoops

from pymmcore_remote.client import MMCoreProxy

with MMCoreProxy() as core:
    print(core)

    @core.mda.events.frameReady.connect
    def _onframe(frame: np.ndarray, event: MDAEvent, meta: dict) -> None:
        print(frame.shape, event, meta)

    core.loadSystemConfiguration()
    print(core.getLoadedDevices())

    core.mda.run(MDASequence(time_plan=TIntervalLoops(interval=0.2, loops=8)))
