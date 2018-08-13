import json
import collections

class Sample:
    def __init__(self, timestamp, data):
        self.timestamp = timestamp
        self.data = data

    def to_json(self):
        return json.dumps(dict(timestamp=self.timestamp, data=self.data.tolist()))

class SampleBuffer:
	def __init__(self, maximum_age_seconds=None):
		self.values = collections.deque()
		self.maximum_age_seconds = maximum_age_seconds

	def extend(self, *samples):
		# Remove any old items
		if self.maximum_age_seconds is not None:
			while len(self.values) > 0 and self.values[0].timestamp < samples[-1].timestamp - self.maximum_age_seconds:
				self.values.popleft()

		self.values.extend(samples)
