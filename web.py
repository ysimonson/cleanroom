from muse import Muse
from time import sleep
from optparse import OptionParser
import os
import json
import collections
import tornado.ioloop
import tornado.web
import tornado.websocket
import threading
import logging
import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi

NOTCH_B, NOTCH_A = butter(4, np.array([55, 65]) / (256 / 2), btype='bandstop')
SLEEP_TIME = 0.1
RAW_BUFFER_LENGTH_SECS = 1
CHANNEL_INDICES = [0, 1, 2, 3]
SAMPLING_FREQUENCY = 256

class Sample:
    def __init__(self, timestamp, data):
        self.timestamp = timestamp
        self.data = data

    def to_json(self):
        return json.dumps(dict(timestamp=self.timestamp, data=self.data.tolist()))

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

class ExtractThread(threading.Thread):
    buffer = []

    def __init__(self, options):
        super().__init__()
        self.options = options

    def run(self):
        muse = Muse(address=self.options.address, callback=self.handle_packet,
                    backend=self.options.backend, interface=self.options.interface,
                    name=self.options.name)

        muse.connect()
        print('Connected')
        muse.start()
        print('Streaming')

        while True:
            try:
                sleep(SLEEP_TIME)
            except:
                break

        muse.stop()
        muse.disconnect()
        print('Disonnected')

    def handle_packet(self, data, timestamps):
        # Add new entries
        for i in range(12):
            self.buffer.append(Sample(timestamps[i], data[:, i]))

        # Remove old entries
        # TODO: this could be more efficient w/ a binary search
        while len(self.buffer) > 0 and self.buffer[0].timestamp < timestamps[-1] - RAW_BUFFER_LENGTH_SECS:
            self.buffer.pop(0)

class ProcessingThread(threading.Thread):
    """
    Thread for taking in raw EEG data, calculating frequency band data, and
    sending everything off to the websocket controllers. All of the
    interesting math is from https://github.com/NeuroTechX/bci-workshop
    """

    def run(self):
        last_timestamp = None
        eeg_buffer = np.zeros((int(SAMPLING_FREQUENCY), len(CHANNEL_INDICES)))
        filter_state = None

        while True:
            if last_timestamp is None:
                samples = ExtractThread.buffer
            else:
                samples = [s for s in ExtractThread.buffer if s.timestamp > last_timestamp]

            if samples:
                last_timestamp = samples[-1].timestamp
                timestamps = np.array([sample.timestamp for sample in samples])
                ch_data = np.array([sample.data[:4] for sample in samples])
                eeg_buffer, filter_state = self.update_buffer(eeg_buffer, ch_data, notch=True, filter_state=filter_state)

                # calculate feature vector, then split it up to its respective bands
                feat_vector = self.compute_feature_vector(eeg_buffer)
                delta_vector, theta_vector, alpha_vector, beta_vector = np.split(feat_vector, 4)

                # distribute data out to websocket buffers
                for sample in samples:
                    RawStreamHandler.enqueue_message(sample.to_json())
                DeltaStreamHandler.enqueue_message(Sample(last_timestamp, delta_vector).to_json())
                ThetaStreamHandler.enqueue_message(Sample(last_timestamp, theta_vector).to_json())
                AlphaStreamHandler.enqueue_message(Sample(last_timestamp, alpha_vector).to_json())
                BetaStreamHandler.enqueue_message(Sample(last_timestamp, beta_vector).to_json())

            sleep(SLEEP_TIME)

    def update_buffer(self, data_buffer, new_data, notch=False, filter_state=None):
        """
        Concatenates "new_data" into "data_buffer", and returns an array with
        the same size as "data_buffer"
        """
        if new_data.ndim == 1:
            new_data = new_data.reshape(-1, data_buffer.shape[1])

        if notch:
            if filter_state is None:
                filter_state = np.tile(lfilter_zi(NOTCH_B, NOTCH_A),
                                       (data_buffer.shape[1], 1)).T
            new_data, filter_state = lfilter(NOTCH_B, NOTCH_A, new_data, axis=0,
                                             zi=filter_state)

        new_buffer = np.concatenate((data_buffer, new_data), axis=0)
        new_buffer = new_buffer[new_data.shape[0]:, :]

        return new_buffer, filter_state

    def compute_feature_vector(self, eeg_data):
        """
        Extract the features from the EEG.

        Args:
            eeg_data (numpy.ndarray): array of dimension [number of samples,
                    number of channels]

        Returns:
            (numpy.ndarray): feature matrix of shape [number of feature points,
                number of different features]
        """
        
        # Compute the PSD
        win_sample_length, _ = eeg_data.shape

        # Apply Hamming window
        w = np.hamming(win_sample_length)
        data_win_centered = eeg_data - np.mean(eeg_data, axis=0)  # Remove offset
        data_win_centered_ham = (data_win_centered.T * w).T

        nfft = self.nextpow2(win_sample_length)
        y = np.fft.fft(data_win_centered_ham, n=nfft, axis=0) / win_sample_length
        psd = 2 * np.abs(y[0 : int(nfft / 2), :])
        f = SAMPLING_FREQUENCY / 2 * np.linspace(0, 1, int(nfft / 2))

        # SPECTRAL FEATURES
        # Average of band powers
        # Delta <4
        ind_delta, = np.where(f < 4)
        mean_delta = np.mean(psd[ind_delta, :], axis=0)

        # Theta 4-8
        ind_theta, = np.where((f >= 4) & (f <= 8))
        mean_theta = np.mean(psd[ind_theta, :], axis=0)

        # Alpha 8-12
        ind_alpha, = np.where((f >= 8) & (f <= 12))
        mean_alpha = np.mean(psd[ind_alpha, :], axis=0)

        # Beta 12-30
        ind_beta, = np.where((f >= 12) & (f < 30))
        mean_beta = np.mean(psd[ind_beta, :], axis=0)

        feature_vector = np.concatenate((mean_delta, mean_theta, mean_alpha,
                                         mean_beta), axis=0)

        feature_vector = np.log10(feature_vector)

        return feature_vector

    def nextpow2(self, i):
        """
        Find the next power of 2 for number i
        """
        n = 1
        while n < i:
            n *= 2
        return n

def flush_message_queues():
    RawStreamHandler.flush_message_queue()
    DeltaStreamHandler.flush_message_queue()
    ThetaStreamHandler.flush_message_queue()
    AlphaStreamHandler.flush_message_queue()
    BetaStreamHandler.flush_message_queue()

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

    extract_thread = ExtractThread(options)
    extract_thread.daemon = True
    extract_thread.start()

    processing_thread = ProcessingThread()
    processing_thread.daemon = True
    processing_thread.start()

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
