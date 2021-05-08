# This is for configuring the AWG over a bit-banged SPI bus created by PRU1.

# This cannot be used at the same time as the ADC, as that uses PRU1 as well. 


import pypruss						# The Programmable Realtime Unit Library
import numpy as np					# Needed for braiding the pins with the delays
import mmap,struct
import Adafruit_BBIO.GPIO as GPIO
import Adafruit_BBIO.PWM as PWM
import time
import logging

REGISTERS_GAIN = {'tx': 0x35,
                  'X':  0x34,
                  'Y':  0x33,
                  'Z':  0x32 }

REGISTERS_PS  =  {'tx': 0x43,
                  'X':  0x42,
                  'Y':  0x41,
                  'Z':  0x40 }

def start(PWM_freq=1e7, PWM_duty_cycle=50, clock_divider=2):
	GPIO.setup("P8_30",GPIO.OUT)	#SPI CS for AWG
	GPIO.output("P8_30",GPIO.HIGH)	#Set CS high initally - i.e. disabled
	GPIO.setup("P9_23",GPIO.OUT)	#AFG External trigger.  NB check JP1 setting too!
	GPIO.setup("P9_24",GPIO.OUT)	#What is this for?  Possibly old code for the old SPI non bit banged bus?
	PWM.start("P8_34",PWM_duty_cycle,PWM_freq) 	# setup ADC master clock 13e6 = 25khz  ~ NCO sees 50MHz clock - connects to J10 on AFG

# NCO removed P8_46 because of a device tree conflict with SPI_overlay_PRU1
#	PWM.start("P8_46",50,50e6) # 100e5

	pypruss.modprobe()					# This only has to be called once pr boot


# This appears to be a clock function BUT what for?  Seems to be for old SPI non bit banged bus?  Is this non longer needed?
def c():
	GPIO.output("P9_24",GPIO.HIGH)
	GPIO.output("P9_24",GPIO.LOW)

# This appears to be a trigger or CS line BUT what for?  Seems to be for old SPI non bit banged bus?  Is this no longer needed?
def trigger():
	logging.debug("[AWG] Triggerring")
	GPIO.output("P9_23",GPIO.HIGH)
	GPIO.output("P9_23",GPIO.LOW)




def sendData(addr,data,rx=0):
	if(rx==0):
		data = [int((0x00 << 24) + (addr << 16) + data)]
	else:
		data = [int((0x80 << 24) + (addr << 16) + 0x0000)]
	
	# data = [0x80272345]	
	GPIO.output("P8_30",GPIO.LOW)
	pypruss.init()						# Init the PRU
	pypruss.open(0)						# Open PRU event 0 which is PRU0_ARM_INTERRUPT
	pypruss.pruintc_init()					# Init the interrupt controller
	pypruss.pru_write_memory(1, 0, data)			# Load the data in the PRU ram
	pypruss.exec_program(1, "arm/spi_awg.bin")		# Load firmware "mem_write.bin" on PRU 0
	pypruss.wait_for_event(0)				# Wait for event 0 which is connected to PRU0_ARM_INTERRUPT
	pypruss.clear_event(0)					# Clear the event
	# data = [0x12345678]
	pypruss.pru_write_memory(1, 0, data)			# Load the data in the PRU ram
	GPIO.output("P8_30",GPIO.HIGH)
	if (rx == 1):

		PRU_ICSS = 0x4A300000  
		PRU_ICSS_LEN = 512*1024 

		# RAM0_START = 0x00000000
		# RAM1_START = 0x00002000
		RAM2_START = 0x00012000


		with open("/dev/mem", "r+b") as f:
			ddr_mem = mmap.mmap(f.fileno(), PRU_ICSS_LEN, offset=PRU_ICSS) 
			# local = struct.unpack('LLLL', ddr_mem[RAM1_START:RAM1_START+16])
			shared = struct.unpack('L', ddr_mem[RAM2_START:RAM2_START+4])
		f.close()
	pypruss.exit()							# Exit
	if (rx == 1):
		return shared[0]
	else:
		return 0


def writeData(addr,value,label="",validate=1):
        tries = 3
	for attempt in range(tries):
		c()
		sendData(addr,value)
		c()
		sendData(0x1D,0x0001)
		c()
		out = sendData(addr,0x0000,rx=1)
	        if out==value or not validate:
                  logging.debug("[AWG] Write command successful '%s', Sent '%s', Read back '%s'" % (label,hex(value),hex(out)))
                  break
                elif validate and attempt == tries - 1:
                  raise IOError("Failed to send command to the AWG for %s after %d attempts" % (label, tries))
                else:
                  logging.warning("[AWG] Write command unsuccessful '%s', Sent '%s', Read back '%s'" % (label,hex(value),hex(out)))
	return out

def getData(addr,label="",output=1):
	c()
	out = sendData(addr,0x0000,rx=1)
	if label != "":
		logging.debug("[AWG] Result of read command %s=%s" % (label,hex(out)))
	return out
		

def getRegisterMap():
	map = []
	for x in range(0x34,0x38):
		out = getData(x)
		print hex(x),hex(out)
		if (out != 0):
			map.append([x,hex(out)])
	print ""
	print ""
	for x in map:
		print hex(x[0]),x[1]


def program():
	GPIO.output("P9_23",GPIO.HIGH)
	writeData(0x1E,0x0000,label="Program mode", validate=1)
def run():
	getData(0x1E,label="Current run mode?")
	writeData(0x1E,0x0001,label="Run mode", validate=1)
	trigger()
	getData(0x1E,label="Current run mode?")

def configureGaussian():
	program()
	writeData(0x27,0x0030,label="Gaussian Mode")
	writeData(0x31,0xFF00,label="DC value")
	writeData(0x35,0x4000,label="DC gain")
	run()
def configureDC():
	# not working yet?  not going to work through rf transformer
	program()
	writeData(0x27,0x0001,label="DC Mode")
	writeData(0x31,0x0000,label="DC value")
	writeData(0x35,0x4000,label="DC gain")
	run()
def configureSawtooth():
	program()
	writeData(0x27,0x1111,label="Sawtooth Mode") # sawtooth dac1 dac2
	writeData(0x37,0xF0F0,label="Step length")
	writeData(0x35,0x5000,label="DC gain")
	run()
def configureSineWave():
	program()
	writeData(0x27,0x0031,label="Sinewave Mode")
	writeData(0x45,0x0000,label="Static phase/freq")
	writeData(0x3E,0x0002,label="Freq MSB") # 0x00 0x48
	writeData(0x3F,0x0000,label="Freq LSB")
	writeData(0x35,0x0800,label="DC gain")
	run()
def configure2SineWave( tx_freq=5000,
                        tx_dcgain=1.0, bc1_dcgain=0.1, bc2_dcgain=0.1, bc3_dcgain=0.1, 
                        bc1_ps=0.0, bc2_ps=0.0, bc3_ps=0.0, 
                        PWM_freq=1e7, PWM_duty_cycle=50, clock_divider=2):

        # Prepare the parameters:
        freq=int(tx_freq*(2**24*clock_divider/PWM_freq))
        freqMSB=freq>>8
        freqLSB=(freq&0xFF)<<8
        PS2=int((bc1_ps%360) / 360.0 * 0x10000)
        PS3=int((bc2_ps%360) / 360.0 * 0x10000)
        PS4=int((bc3_ps%360) / 360.0 * 0x10000)

	program()
        writeData(0x27,0x3131,label="Sinewave Mode 1&2")
        writeData(0x26,0x3131,label="Sinewave Mode 3&4")
        writeData(0x45,0x0000,label="Static phase/freq")
        writeData(0x3E,freqMSB,label="Freq MSB") # 0x03 0x62
        writeData(0x3F,freqLSB,label="Freq LSB")
        setGain("tx", tx_dcgain)
        setGain("X", bc1_dcgain)
        setGain("Y", bc2_dcgain)
        setGain("Z", bc3_dcgain)
        setPhaseShift("tx", 0)
        setPhaseShift("X", bc1_ps, deg=True)
        setPhaseShift("Y", bc2_ps, deg=True)
        setPhaseShift("Z", bc3_ps, deg=True)
        run()

def setGain(channel, gain, oneshot=False):
        if oneshot:
          program()
        if not channel in REGISTERS_GAIN:
          raise KeyError("Channel '%s' is not a valid channel name" % channel)
        if gain >= 2 or gain <= -2:
          raise OverflowError("Gain (%f) must be a number between -2 and 2" % gain)
        DCGain=int(0x400*abs(gain))<<4|(0x8000 if gain < 0 else 0x0000)
        writeData(REGISTERS_GAIN[channel], DCGain, "DC gain %s" % str(channel))
        if oneshot:
          run()

def setPhaseShift(channel, offset, deg=False, oneshot=False):
        if oneshot:
          program()
        if not channel in REGISTERS_PS:
          raise KeyError("Channel '%s' is not a valid channel name" % channel)
        if deg:
          mod=360.0
        else:
          mod=np.pi*2
        PS=int((offset%mod) / mod * 0x10000)
        writeData(REGISTERS_PS[channel], PS, "Phase Offset %s" % str(channel))
        if oneshot:
          run()

	
def finish():
	GPIO.cleanup()
if __name__ == "__main__":
	start()
	configure2SineWave()
