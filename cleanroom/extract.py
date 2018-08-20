from .muse import Muse
from .models import Sample
import time
from multiprocessing import Process, Queue

def _target(queue, address=None, backend=None, interface=None, name=None):
    def add_to_queue(data, timestamps):
        for i in range(12):
            queue.put(Sample(timestamps[i], data[:, i]))

    try:
        muse = Muse(
            address=address,
            callback=add_to_queue,
            backend=backend,
            interface=interface,
            name=name
        )

        muse.connect()
        muse.start()

        try:
            while True:
                time.sleep(1)
        finally:
            muse.stop()
            muse.disconnect()
    except Exception as e:
        queue.put(e)

def get_raw(**kwargs):
    q = Queue()
    p = Process(target=_target, args=(q,), kwargs=kwargs)
    p.daemon = True
    p.start()

    while True:
        item = q.get()

        if isinstance(item, Exception):
            raise item
        else:
            yield item
