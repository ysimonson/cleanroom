from .muse import Muse
from .models import Sample, SampleBuffer

DEFAULT_MAXIMUM_AGE_SECONDS = 1

class Extractor:
    """Extracts data from the Muse headset into a buffer of samples"""

    def __init__(self, address=None, backend=None, interface=None, name=None, maximum_age_seconds=DEFAULT_MAXIMUM_AGE_SECONDS):
        """
        Creates a new extractor.

        address: An optional string specifying the MAC address of the Muse headset for quicker discovery.
        backend: The pygatt backend to use. Can be `auto`, `gatt`, or `bgapi`. Defaults to `auto`.
        interface: The pygatt interface to use. `hci0` for gatt or a COM port for bgapi.
        name: The name of the Muse headset, if multiple are within discovery range.
        maximum_age_seconds: The oldest entry to be maintained in the buffer.
        Anything older will be dropped the next time samples are added to the
        buffer.
        """

        self.buffer = SampleBuffer(maximum_age_seconds=maximum_age_seconds)

        self.muse = Muse(
            address=address,
            callback=self._handle_packet,
            backend=backend,
            interface=interface,
            name=name
        )

    def start(self):
        """Starts listening"""
        self.muse.connect()
        self.muse.start()

    def stop(self):
        """Stops listening"""
        self.muse.stop()
        self.muse.disconnect()

    def _handle_packet(self, data, timestamps):
        self.buffer.extend(*[Sample(timestamps[i], data[:, i]) for i in range(12)])
