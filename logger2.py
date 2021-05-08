# This script does all that is necessary to setup the 
# Beaglebone, the ADC and the AWG
# and then logs the raw data to a file.

# Something similar to this should be the template for 
# autonomous operations of the setup


import os,sys,signal,getopt
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


  setup_BB.setup_BB_slots()
  
  if config.hardware['AWGon']==True:
     None
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

   
  if config.hardware['AWGon']==True:
      logging.info("[LOGGER] Starting the AWG")
      AWG.configure2SineWave(**args) # configure for 2 sinewaves

      logging.info("[LOGGER] Setting up analogue amplification")
      analogue_IO.enable(**config.hardware['IO']) # enable TX on analogue board
  else:
      logging.info("[LOGGER] Signal generation Tx is off")
  
  
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
            -f,--rawfile        raw data location. String
            -t,--maxtime       logger quit after t in seconds 
            -o,--AWGon          Signal generator and transmitter on or off. (1,0)
            """
      sys.exit(2)
    for opt, arg in opts:
      if opt == '-h':
         print(""""test.py -f <rawfile> -t <maxtime>
            Passed arguments overwrite the settings saved in config.py!
            -f,--rawfile        raw data location. String
            -t,--maxtime       logger quit after t in seconds
            -o,--AWGon          Signal generator and transmitter on or off. (1,0)
            """)
         sys.exit()
      elif opt in ("-f", "--rawfile"):
        if not isinstance(arg , str):
            raise TypeError('"raw_data" must be an string!')
            sys.exit()
        config.hardware["ADC"]["raw_file"]= arg
        logging.info(["Saving raw data in: ", arg])
      elif opt in ("-t", "--maxtime"):
        try:
            arg= float(arg)
            if arg <= 0:  
                raise ValueError()
        except ValueError:
            raise ValueError('"--maxtime" (-t) must be a positive number ')
        config.hardware["ADC"]["max_dt"]= arg
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
    logger()
    setPhase(150)
    finish()



