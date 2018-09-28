# Fake Roast provides fake roast temperatures to Artisan.
#
# Temperature data is read by Artisan using the 'external program' support,
# which invokes a command to fetch current temperature readings. Typically
# Artisan is configured to run a command such as
# `tail -n 1 /dev/shm/roast_temperatures.json`, and this program is invoked to
# simulate a roast by writing to that file, e.g. via:
#
#   $ python3 fake_roast.py --dest=/dev/shm/roast_temperatures.json

import argparse
import json
import numpy
import time

parser = argparse.ArgumentParser(
  description='Provides fake sensor readings to Artisan')
parser.add_argument('--dest', type=str, required=True,
                    help='destination file to write to')
parser.add_argument('--sensors', type=str, default='bt,et',
                    help='comma separated sensors to enable: bt, et, met')
parser.add_argument('--relative_error', type=float, default=0,
                    help='relative error to add to signal')
parser.add_argument('--sample_period', type=float, default=3,
                    help='how often to "read" new temperatures')
parser.add_argument('--send_read_at', type=str, default='yes',
                    help='if truish, send read time to Artisan')

args = parser.parse_args()

def add_error(temp):
  '''Add error to the provided sensor reading.'''
  return temp * numpy.random.uniform(1 - args.relative_error, 1 + args.relative_error)

class DefaultRoast:
  def bt(self, t):
    if t < 30:
      # rising towards charge: ends at 357F @ 30s
      return 352 + t/2
    elif t < 139:
      # falling to TP and next 30s of rise: ends at 227F @ 139s
      return (t - 120) ** 2 / 55 + 220
    elif t < 367:
      # from TP, through ramp until approaching fc: ends at 370F @ 367s
      return 139.7 + t/1.6
    elif t < 417:
      # approaching FC, ends at 385F @ 417s
      return 390 - 1.36**((466-t)/10)
    elif t < 568:
      # pretend linear through FC and RD until drop
      return (t - 440)/6 + 389.3
    else:
      # pretend flat after drop
      return 410

  def et(self, t):
    return 440

  def met(self, t):
    return self.DefaultRoast.et(t) + 20

roast = DefaultRoast()
sensors = args.sensors.split(',')
enable_bt = ('bt' in sensors)
enable_et = ('et' in sensors)
enable_met = ('met' in sensors)

output = open(args.dest, 'wb')
start = time.time()

try:
  while True:
    t = float(time.time() - start)
    temperatures = [None, None, None]
    if enable_et: temperatures[0] = roast.et(t)
    if enable_bt: temperatures[1] = roast.bt(t)
    if enable_met: temperatures[2] = roast.met(t)
    temperatures = [temp and add_error(temp) for temp in temperatures]

    data = {'temperatures': temperatures}
    if args.send_read_at:
     data['read_at'] = float(start + t)

    output.write(json.dumps(data))
    output.write("\n")
    output.flush()

    time.sleep(args.sample_period)
except KeyboardInterrupt:
  pass
