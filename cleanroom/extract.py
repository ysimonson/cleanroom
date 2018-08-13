from .muse import Muse
from .models import Sample, SampleBuffer

DEFAULT_MAXIMUM_AGE_SECONDS = 1

class Extractor:
    def __init__(self, address=None, backend=None, interface=None, name=None, maximum_age_seconds=DEFAULT_MAXIMUM_AGE_SECONDS):
        self.buffer = SampleBuffer(maximum_age_seconds=maximum_age_seconds)

        self.muse = Muse(
            address=address,
            callback=self._handle_packet,
            backend=backend,
            interface=interface,
            name=name
        )

    def start(self):
        self.muse.connect()
        self.muse.start()

    def stop(self):
        self.muse.stop()
        self.muse.disconnect()

    def _handle_packet(self, data, timestamps):
        self.buffer.extend(*[Sample(timestamps[i], data[:, i]) for i in range(12)])
