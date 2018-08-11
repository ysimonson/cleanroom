from muse import Muse
from time import sleep
from optparse import OptionParser

parser = OptionParser()
parser.add_option("-a", "--address",
                  dest="address", type='string', default=None,
                  help="device mac adress.")
parser.add_option("-n", "--name",
                  dest="name", type='string', default=None,
                  help="name of the device.")
parser.add_option("-b", "--backend",
                  dest="backend", type='string', default="auto",
                  help="pygatt backend to use. can be auto, gatt or bgapi")
parser.add_option("-i", "--interface",
                  dest="interface", type='string', default=None,
                  help="The interface to use, 'hci0' for gatt or a com port for bgapi")

(options, args) = parser.parse_args()

def process(data, timestamps):
    for i in range(12):
    	print(data[:, i], timestamps[i])

muse = Muse(address=options.address, callback=process,
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
