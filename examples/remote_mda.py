import numpy as np
from useq import MDAEvent, MDASequence, TIntervalLoops

from pymmcore_remote import MMCorePlusProxy

with MMCorePlusProxy() as core:
    core.loadSystemConfiguration()

    @core.mda.events.frameReady.connect
    def _onframe(frame: np.ndarray, event: MDAEvent, meta: dict) -> None:
        print(f"received frame shape {frame.shape}, index {event.index}")

    core.mda.run(MDASequence(time_plan=TIntervalLoops(interval=0.2, loops=8)))
