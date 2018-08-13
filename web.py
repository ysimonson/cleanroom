from cleanroom import Extractor, Transformer
from time import sleep
from optparse import OptionParser
import os
import tornado.ioloop
import tornado.web
import tornado.websocket
import threading
import logging

SLEEP_TIME = 0.1

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

class DeltaStreamHandler(StreamHandler):
    pass

class ThetaStreamHandler(StreamHandler):
    pass

class AlphaStreamHandler(StreamHandler):
    pass

class BetaStreamHandler(StreamHandler):
    pass

def flush_message_queues():
    RawStreamHandler.flush_message_queue()
    DeltaStreamHandler.flush_message_queue()
    ThetaStreamHandler.flush_message_queue()
    AlphaStreamHandler.flush_message_queue()
    BetaStreamHandler.flush_message_queue()

def background_worker(options):
    last_timestamp = None

    def send_samples_to_message_queue(buffer, stream_handler):
        for sample in buffer.values:
            if last_timestamp is None or last_timestamp < sample.timestamp:
                stream_handler.enqueue_message(sample.to_json())

    extractor = Extractor(address=options.address, backend=options.backend, interface=options.interface, name=options.name)
    extractor.start()

    transformer = Transformer()

    try:
        while True:
            transformer.transform(extractor.buffer.values)

            send_samples_to_message_queue(extractor.buffer, RawStreamHandler)
            send_samples_to_message_queue(transformer.delta_buffer, DeltaStreamHandler)
            send_samples_to_message_queue(transformer.theta_buffer, ThetaStreamHandler)
            send_samples_to_message_queue(transformer.alpha_buffer, AlphaStreamHandler)
            send_samples_to_message_queue(transformer.beta_buffer, BetaStreamHandler)

            if len(extractor.buffer.values) > 0:
                last_timestamp = extractor.buffer.values[-1].timestamp

            sleep(SLEEP_TIME)
    except:
        extractor.stop()
        raise

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

    t = threading.Thread(target=background_worker, args=(options,))
    t.daemon = True
    t.start()

    handlers = [
        (r"/", MainHandler),
        (r"/stream/raw", RawStreamHandler),
        (r"/stream/delta", DeltaStreamHandler),
        (r"/stream/theta", ThetaStreamHandler),
        (r"/stream/alpha", AlphaStreamHandler),
        (r"/stream/beta", BetaStreamHandler),
    ]

    app = tornado.web.Application(handlers, template_path=os.path.join(os.path.dirname(__file__), "templates"))
    app.listen(options.port)
    
    callback = tornado.ioloop.PeriodicCallback(flush_message_queues, SLEEP_TIME * 1000)
    callback.start()
    
    tornado.ioloop.IOLoop.current().start()

if __name__ == "__main__":
    main()
