from muse import Muse
from time import sleep
from optparse import OptionParser
import os
import json
import tornado.ioloop
import tornado.web
import tornado.websocket
import threading
import logging

PUBLISH_INTERVAL = 100

class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render("index.html")

class StreamHandler(tornado.websocket.WebSocketHandler):
    @classmethod
    def message_queue(cls):
        if not hasattr(cls, "_message_queue"):
            cls._message_queue = []
        return cls._message_queue

    @classmethod
    def listeners(cls):
        if not hasattr(cls, "_listeners"):
            cls._listeners = set()
        return cls._listeners

    def open(self):
        self.listeners().add(self)

    def on_close(self):
        try:
            self.listeners().remove(self)
        except:
            # Listener may have already been removed
            pass

    @classmethod
    def enqueue_message(cls, message):
        cls.message_queue().append(message)

    @classmethod
    def flush_message_queue(cls):
        queue = cls.message_queue()

        if not len(queue):
            return

        removable = set()
        message = "\n".join(queue) + "\n"
        queue.clear()

        for listener in cls.listeners():
            try:
                listener.write_message(message)
            except tornado.iostream.StreamClosedError:
                # `on_close` should capture most dropped listeners, but not
                # all. This will remove any remaining dropped listeners.
                removable.add(listener)
            except:
                logging.error("Error sending message", exc_info=True)

        if len(removable):
            cls.listeners().difference_update(removable)

class RawStreamHandler(StreamHandler):
    pass

class RhythmStreamHandler(StreamHandler):
    pass

def start_eeg_thread(options):
    def handle_packet(data, timestamps):
        for i in range(12):
            j = json.dumps(dict(data=data[:, i].tolist(), timestamp=timestamps[i]))
            RawStreamHandler.enqueue_message(j)

    def thread_runner():
        muse = Muse(address=options.address, callback=handle_packet,
                    backend=options.backend, interface=options.interface,
                    name=options.name)

        muse.connect()
        print('Connected')
        muse.start()
        print('Streaming')

        while True:
            try:
                sleep(1)
            except:
                break

        muse.stop()
        muse.disconnect()
        print('Disonnected')

    t = threading.Thread(target=thread_runner)
    t.daemon = True
    t.start()

def start_app(options):
    handlers = [
        (r"/", MainHandler),
        (r"/stream/raw", RawStreamHandler),
        (r"/stream/rhythm", RhythmStreamHandler),
    ]

    app = tornado.web.Application(handlers, template_path=os.path.join(os.path.dirname(__file__), "templates"))
    app.listen(options.port)
    
    callback = tornado.ioloop.PeriodicCallback(RawStreamHandler.flush_message_queue, PUBLISH_INTERVAL)
    callback.start()
    
    tornado.ioloop.IOLoop.current().start()

def main():
    parser = OptionParser()
    parser.add_option("-a", "--address",
                      dest="address", type='string', default=None,
                      help="Device mac adress.")
    parser.add_option("-n", "--name",
                      dest="name", type='string', default=None,
                      help="Name of the device.")
    parser.add_option("-b", "--backend",
                      dest="backend", type='string', default="auto",
                      help="pygatt backend to use. Can be `auto`, `gatt` or `bgapi`. Defaults to `auto`.")
    parser.add_option("-i", "--interface",
                      dest="interface", type='string', default=None,
                      help="The interface to use, `hci0` for gatt or a com port for bgapi.")
    parser.add_option("-p", "--port",
                      dest="port", type='int', default=8888,
                      help="Port to run the HTTP server on. Defaults to `8888`.")

    (options, _) = parser.parse_args()

    start_eeg_thread(options)
    start_app(options)

if __name__ == "__main__":
    main()
