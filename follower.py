import pypruss
import numpy as np
import struct
import Adafruit_BBIO.GPIO as GPIO
import time
from sample import sample,waveform
import logging
import os
#from gpspoller import GpsPoller  `  bgh


class follower(object):

    PRU_MAX_LONG_SAMPLES  =   0x00040000
    PRU0_OFFSET_SRAM_HEAD =   0x1000
    PRU0_OFFSET_DRAM_PBASE =  0x1004
    PRU0_OFFSET_SPIN_COUNT =  0x1008
    PRU0_OFFSET_RES1 =        0x100C
    PRU0_OFFSET_SRAM_TAIL =   0x1010
    PRU0_OFFSET_DRAM_HEAD =   0x1014
    PRU0_OFFSET_RES2 =        0x1018
    PRU0_OFFSET_RES3 =        0x101C
    PRU_EVTOUT_0 = 3


    def __init__(self, pru = 0, pru0_fw="arm/pru00.bin", pru1_fw="arm/pru01.bin"):
        if pru == 0:
            pru_dataram = pypruss.PRUSS0_PRU0_DATARAM
        else:
            pru_dataram = pypruss.PRUSS0_PRU1_DATARAM

        self._spare = 0
        self._ofile = None
        self._gpsp = None

        logging.debug("[ADC] setting up power control line")
        GPIO.setup("P9_18",GPIO.OUT)

        logging.debug("[ADC] pruss init")
        pypruss.init()						# Init the PRU

        logging.debug("[ADC] pruss open")
        ret = pypruss.open(self.PRU_EVTOUT_0)

        logging.debug("[ADC] pruss intc init")
        pypruss.pruintc_init()					# Init the interrupt controller

        logging.debug("[ADC] mapping memory")
        self._data = pypruss.map_prumem(pru_dataram)
        
        logging.debug("[ADC] data segment len=%d" % len(self._data))
        
        logging.debug("[ADC] setting tail")
        self._tail = 0
        struct.pack_into('l', self._data, self.PRU0_OFFSET_DRAM_HEAD, self._tail)

        logging.debug("[ADC] mapping extmem")
        self._extmem = pypruss.map_extmem()
        logging.debug("[ADC] ext segment len=%d" % len(self._extmem))

        logging.debug("[ADC] setup mem")
        self.ddrMem = pypruss.ddr_addr()
        logging.debug("[ADC] V extram_base = 0x%x" % self.ddrMem)

        self._pru01_phys = int(open("/sys/class/uio/uio1/maps/map1/addr", 'r').read(), 16)
        struct.pack_into('L', self._data, self.PRU0_OFFSET_SRAM_HEAD, 0)
        struct.pack_into('L', self._data, self.PRU0_OFFSET_DRAM_PBASE, self._pru01_phys)
        struct.pack_into('L', self._data, self.PRU0_OFFSET_SPIN_COUNT, 0)
        struct.pack_into('L', self._data, self.PRU0_OFFSET_RES1, 0x00000000)
        struct.pack_into('L', self._data, self.PRU0_OFFSET_SPIN_COUNT, 0)
        struct.pack_into('L', self._data, self.PRU0_OFFSET_SPIN_COUNT, 0)
        struct.pack_into('L', self._data, self.PRU0_OFFSET_RES2, 0xbabedead)
        struct.pack_into('L', self._data, self.PRU0_OFFSET_RES3, 0xbeefcafe)
        
        logging.debug("[ADC] loading pru01 code")
        pypruss.exec_program(1, pru1_fw)

        logging.debug("[ADC] loading pru00 code")
        pypruss.exec_program(0, pru0_fw)

    def power_on(self=None):
        logging.debug("[ADC] Powering the ADC on")
        GPIO.output("P9_18",GPIO.HIGH)
        #Wait for everything to come to life
        self._tail = struct.unpack_from("l", self._data, self.PRU0_OFFSET_DRAM_HEAD)[0]
        for i in range(10 * self.PRU_MAX_LONG_SAMPLES / (4096 * 16)):
          i = np.fft.rfft(self.get_sample_block(4096 * 16))

    def power_off(self=None):
        logging.debug("[ADC] Powering the ADC off")
        GPIO.output("P9_18",GPIO.LOW)
        self.close_file()
        self.stop_gps_polling()

    def stop(self):
        logging.debug("[ADC] Stopping the PRUs")
        struct.pack_into('L', self._data, self.PRU0_OFFSET_RES1, 0xdeadbeef)
        time.sleep(0.5)
        pypruss.pru_disable(0)

    def read_uint(self, offset=0):
        return self.readData('L', offset, 1)[0]

    def readData(self, dtype='l', offset=0, samples = 1):
        return struct.unpack_from(dtype*samples, self._extmem, offset)

    def get_sample_block(self, bytes_in_block = 4096):

        # In theory we could wrap around the end of the buffer but in practice 
        # (self.PRU_MAX_LONG_SAMPLES) should be a multiple of bytes_in_block
        # This allows for much simpler code
        head_offset = self._tail
        if (head_offset + bytes_in_block - 1) > self.PRU_MAX_LONG_SAMPLES:
          head_offset=0

        self._spare = 0
        while ( True ):
            tail_offset = struct.unpack_from("l", self._data, self.PRU0_OFFSET_DRAM_HEAD)[0]
            diff = (tail_offset - head_offset) % self.PRU_MAX_LONG_SAMPLES
            if (diff >= bytes_in_block) and (diff <= self.PRU_MAX_LONG_SAMPLES - bytes_in_block):
                break
            self._spare = 1
            time.sleep(0.02)

        # dtype='4<u4' means an array of dimension 4 of 4 unsigned integer written in little endian
        # (16 bytes per row, hence the /16 for the offsets and counts)
        result = np.frombuffer(self._extmem, dtype='4<i4', count=bytes_in_block/16, offset=head_offset)
        result.dtype = np.int32

        self._tail = (head_offset + bytes_in_block) % self.PRU_MAX_LONG_SAMPLES

        return result

    def close_file(self):
        if self._ofile:
          self._ofile.close()

    def stop_gps_polling(self):
        if self._gpsp:
          self._gpsp.running = False
          self._gpsp.join() # wait for the thread to finish what it's doing

    #SPS: Samples Per Second, this must be calibrated
    def follow_stream(self, SPS=40000, dispFFT=False, axis=[0,15000,-1e12,1e12], FFTchannels=[1,2,3], selected_freq=None, raw_file="", max_dt=0):
        if raw_file != "":
          # Disable displaying anything if we're writing to a file
          dispFFT = False
          self._ofile = open(raw_file, "w")
     #     self._gpsp = GpsPoller()    bgh
     #     self._gpsp.start()          bgh

        if dispFFT:
          import matplotlib
          matplotlib.use('GTKCairo')
          import matplotlib.pyplot as plt
          plt.ion()
          plt.show()
        
        quit = False
        t0=time.time()
        samples_count = 4096
        bytes_in_block = samples_count * 16 #4 channels, 4B per sample

        fftfreq = np.fft.rfftfreq(samples_count, d=1.0/SPS) # /16 -> /4 channels /4 bytes per channel
        if selected_freq:
          selected_index = np.argmin(np.abs(fftfreq - selected_freq))

        self._tail = struct.unpack_from("l", self._data, self.PRU0_OFFSET_DRAM_HEAD)[0]

        while (not quit):
            if max_dt>0:
                if (time.time()-t0)>max_dt:
                    quit=True
                    
            samples=self.get_sample_block(bytes_in_block)
            #Invert dimensions
            channels = np.transpose(samples)
            if raw_file != "":                                                                                                                                         
               np.save(self._ofile, {"time": time.time(), "chans": channels})
    #           np.save(self._ofile, {"time": time.time(), "lat": self._gpsp.gpsd.fix.latitude, "lon": self._gpsp.gpsd.fix.longitude, "chans": channels})                   
               continue                                                                                                                                                
            
            if axis != None and dispFFT and self._spare:
              plt.axis(axis)
            ostring=""
            for chan in FFTchannels:
              fft = np.fft.rfft(channels[chan]) / samples_count

              #Disregard the DC component.
              fft[0] = 0
              
              if selected_freq == None:
                selected_index = np.argmax(np.absolute(fft))
              ostring += "Channel " + str(chan) + ": %-*sHz = %-*s\t" %  (5, int(fftfreq[selected_index]), 12, int(np.absolute(fft[selected_index]))) 
              #ostring += "%s," %  (int(np.absolute(fft[selected_index]))) 
              if dispFFT and self._spare:
                plt.plot(fftfreq, np.absolute(fft), label="Channel %d"%chan)
                #plt.plot(channels[chan], label="Channel %d"%chan)
              #print fftfreq[np.argmax(np.absolute(fft))]
            print ostring
            if dispFFT and self._spare:
              plt.legend()
              plt.draw()
              plt.pause(0.001)
              plt.cla()
            


    def get_sample_freq(self, selected_freq, SPS=40000, dispFFT=False, FFTchannels=[1,2,3], axis=None, raw_file=""):
        samples_count = 4096
        bytes_in_block = samples_count * 16 #4 channels, 4B per sample
        fftfreq = np.fft.rfftfreq(samples_count, d=1.0/SPS) # /16 -> /4 channels /4 bytes per channel
        selected_index = np.argmin(np.abs(fftfreq - selected_freq))
        
        #self._tail = struct.unpack_from("l", self._data, self.PRU0_OFFSET_DRAM_HEAD)[0]
        samples=self.get_sample_block(bytes_in_block)

        #Invert dimensions
        channels = np.transpose(samples)

        ref_wave = waveform(selected_freq, np.fft.rfft(channels[0])[selected_index] / samples_count)
        selected_sample = sample(ref_wave)
        for chan in FFTchannels:
          fft = np.fft.rfft(channels[chan]) / samples_count
          chan_wave=waveform(selected_freq, fft[selected_index])
          selected_sample.add_channel(chan_wave)
        return selected_sample
