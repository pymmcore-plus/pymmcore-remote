import numpy as np
from useq import MDAEvent, MDASequence, TIntervalLoops

from pymmcore_remote import ClientCMMCorePlus, server_process

PORT = 55999

# this context manager ensures a server is running, or creates a new one if not.
with server_process(port=PORT):
    # create a proxy object that communicates with the MMCore object on the server
    with ClientCMMCorePlus(port=PORT) as core:
        # continue using core as usual:
        core.loadSystemConfiguration()

        # memory is shared between client and server as shared memory
        @core.mda.events.frameReady.connect
        def _onframe(frame: np.ndarray, event: MDAEvent, meta: dict) -> None:
            print(f"received frame shape {frame.shape}, index {event.index}")

        core.mda.run(MDASequence(time_plan=TIntervalLoops(interval=0.2, loops=8)))
