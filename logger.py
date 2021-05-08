# This script does all that is necessary to setup the 
# Beaglebone, the ADC and the AWG
# and then logs the raw data to a file.

# Something similar to this should be the template for 
# autonomous operations of the setup


import os,sys,signal
import spi_awg as AWG
import analogue_IO
import setup_BB
import follower
import time # For testing only
import config
import numpy as np
import logging


def signal_handler(signum, frame):
  if signum == signal.SIGINT:
    print "Ctrl-C received, exitting"
    finish()

def startup():
  global f
  global ADC

  # Setup Logging
  logging.basicConfig(level=logging.INFO, stream=sys.stdout)

  setup_BB.setup_BB_slots()

  AWG.start(**config.hardware['AWG']) # start AWG

  args=config.test_params.copy()
  args.update(config.hardware['AWG'])

  if os.path.isfile("current.calib"):
    f = open("current.calib", "r")
    content = f.read()
    f.close()
    args.update(eval(content))
    metadata = args.pop("metadata")
    if not config.hardware["ADC"]["raw_file"] == "":
      f = open("%s.metadata" % (config.hardware["ADC"]["raw_file"]), "w")
      f.write(str(metadata))
      f.close()


  logging.info("[LOGGER] Starting the AWG")
  AWG.configure2SineWave(**args) # configure for 2 sinewaves

  logging.info("[LOGGER] Setting up analogue amplification")
  analogue_IO.enable(**config.hardware['IO']) # enable TX on analogue board

  logging.info("[LOGGER] Loading ADC PRU code")
  ADC = follower.follower()
  logging.info("[LOGGER] TX Power on and start sampling")
  ADC.power_on()

def setPhase(x):
  AWG.setPhase(x)
def setAmplitude(x):
  AWG.setAmplitude(x)

def logger():
  global ADC
  args=config.hardware['ADC'].copy()
  args.update({'selected_freq': config.test_params['tx_freq']})
  ADC.follow_stream(**args)
  finish()

def finish():
  print "Finished"

  ADC.stop()
  ADC.power_off()

  analogue_IO.disable() # disable TX
  AWG.finish() # free GPIO ports
  exit(0)

if __name__ == "__main__":
  signal.signal(signal.SIGINT, signal_handler)
  startup()
  logger()
  setPhase(150)
  finish()
