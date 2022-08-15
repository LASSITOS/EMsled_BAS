# This script does all that is necessary to setup the 
# Beaglebone, the ADC and the AWG
# and then logs the raw data to a file.

# Something similar to this should be the template for 
# autonomous operations of the setup


import os,sys,signal,getopt
import spi_awg as AWG
import analogue_IO
import setup_BB

import time # For testing only
import config_sigGen as config
import numpy as np
import logging


def signal_handler(signum, frame):
  if signum == signal.SIGINT:
    print "Ctrl-C received, exiting"
    finish()

def startup():
  global f


  setup_BB.setup_BB_slots()
  
  AWG.start(**config.hardware['AWG']) # start AWG

  args=config.test_params.copy()
  args.update(config.hardware['AWG'])

   
  if config.hardware['AWGon']==True:
      logging.info("[LOGGER] Starting the AWG")
      AWG.configure2SineWave(**args) # configure for 2 sinewaves

  else:
      logging.info("[LOGGER] Signal generation Tx is off")
  
  

def setPhase(x):
  AWG.setPhase(x)
def setAmplitude(x):
  AWG.setAmplitude(x)


def finish():
  logging.info("Finished")

  ADC.stop()
  ADC.power_off()

  analogue_IO.disable() # disable TX
  AWG.finish() # free GPIO ports
  logging.info("[LOGGER] The End")
  exit(0)

def check_input(argv):
    # check input arguments
    try:
      opts, args = getopt.getopt(argv,"hf:t:o:",["rawfile=","maxtime=","AWGon=" ])
    except getopt.GetoptError:
      print """"test.py -f <rawfile> -t <maxtime>
            Passed arguments overwrite the settings saved in config.py!
            -t,--maxtime       logger quit after t in seconds 
            -o,--AWGon          Signal generator and transmitter on or off. (1,0)
            """
      sys.exit(2)
    for opt, arg in opts:
      if opt == '-h':
         print(""""test.py -f <rawfile> -t <maxtime>
            Passed arguments overwrite the settings saved in config.py!
            -t,--maxtime       logger quit after t in seconds
            -o,--AWGon          Signal generator and transmitter on or off. (1,0)
            """)
         sys.exit()
      elif opt in ("-t", "--maxtime"):
        try:
            arg= float(arg)
            if arg <= 0:  
                raise ValueError()
        except ValueError:
            raise ValueError('"--maxtime" (-t) must be a positive number ')
        config.test_params["duration"]= arg
        logging.info(['Stopping data logging after : ', str(arg),' s'] )
        
      elif opt in ("-o", "--AWGon"):
        if int(arg)==1:
            config.hardware["AWGon"]= True
            logging.info('Transmitter signal set to on' )
        else:
            config.hardware["AWGon"]= False
            logging.info('Transmitter signal is off' )
    


if __name__ == "__main__":
    
    
    # setup log and logfile
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,)# filename='logging.log',)
  
    check_input(sys.argv[1:])

    #  start signal generator and data logger
    signal.signal(signal.SIGINT, signal_handler)
    startup()
    time.sleep(config.test_params["duration"])
    setPhase(150)
    time.sleep(0.5)
    finish()



