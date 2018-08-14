"""Models"""

import json
import threading
import collections

class Sample:
    """A sampling of sensor data at a specific time"""

    def __init__(self, timestamp, data):
        """
        Constructs a new sample.

        timestamp: A (float) UNIX timestamp of when the sample was collected.
        data: A numpy array of sensor data.
        """

        self.timestamp = timestamp
        self.data = data

    def to_json(self):
        return json.dumps(dict(timestamp=self.timestamp, data=self.data.tolist()))

class SampleBuffer:
    """
    A thread-safe buffer of multiple samples, with automatic garbage
    collection of older entries.
    """

    def __init__(self, maximum_age_seconds=None):
        """
        Constructs a new sample buffer.

        maximum_age_seconds: The oldest entry to be maintained in the buffer.
        Anything older will be dropped the next time samples are added to the
        buffer.
        """

        self._values = collections.deque()
        self._lock = threading.Lock()
        self.maximum_age_seconds = maximum_age_seconds

    def copy(self):
        with self._lock:
            return list(self._values)

    def extend(self, *samples):
        """Adds one or more samples to the buffer"""

        with self._lock:
            # Remove any old items
            if self.maximum_age_seconds is not None:
                while len(self._values) > 0 and self._values[0].timestamp < samples[-1].timestamp - self.maximum_age_seconds:
                    self._values.popleft()

            self._values.extend(samples)
