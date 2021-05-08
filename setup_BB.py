# This script is responsible for setting up the relevant GPIO of the beagleboard, for use by the onboard PRU's (programmable realtime units) 


import os

def setup_BB_slots():
	f = open("/sys/devices/bone_capemgr.9/slots","r")
	if len(filter(lambda x: "SPI-OVERLAY-PRU1" in x, f.readlines())) == 0:
		print "Initialising slot manager"
		os.system("sh add_spi_pru1_overlay")
	f.close()

