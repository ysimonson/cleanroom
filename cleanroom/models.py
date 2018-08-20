"""Models"""

import json

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
