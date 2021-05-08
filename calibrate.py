#!/usr/bin/python

# This script does all that is necessary to setup the 
# Beaglebone, the ADC and the AWG
# and then logs the raw data to a file.

# Something similar to this should be the template for 
# autonomous operations of the setup


import os,sys,signal
import Adafruit_BBIO.GPIO as GPIO
import spi_awg as AWG
import analogue_IO
import setup_BB
import follower
import time
import config
import numpy as np
import logging
import pprint
import os


def signal_handler(signum, frame):
  if signum == signal.SIGINT:
    print "Ctrl-C received, exitting"
    finish()

def startup():
  global f
  global ADC

  # Setup Logging
  logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

  setup_BB.setup_BB_slots()

  AWG.start(**config.hardware['AWG']) # start AWG

  args=config.test_params.copy()
  args.update(config.hardware['AWG'])
  logging.info("[CALIBRATION] Starting the AWG")
  AWG.configure2SineWave(**args) # configure for 2 sinewaves

def setPhase(x):
  AWG.setPhase(x)
def setAmplitude(x):
  AWG.setAmplitude(x)

def logger():
  global ADC
  args=config.hardware['ADC'].copy()
  args.update({'selected_freq': config.test_params['tx_freq']})
  calibrate()
  finish()

def finish():
  print "Finished"

  ADC.power_off()
  ADC.stop()

  analogue_IO.disable() # disable TX
  GPIO.cleanup() # free GPIO ports
  exit(0)

def calibrate():
  logging.info("[CALIBRATION] Starting calibration procedure")
  global ADC
  target_coeff = 1
  max_amp = 2**30 #Maximum signed int value / 2
  target_snr = 2
  parameters = {'bc': [], 'tx': []}
  args_adc = config.hardware['ADC'].copy()
  args_adc.update({'selected_freq': config.test_params['tx_freq']})
  zero_gains()
  analogue_IO.enable(**config.hardware['IO'])
  calib_metadata=dict()
  for chan in ["X", "Y", "Z"]:
    logging.info("[CALIBRATION] - Calibration, searching channel %s", chan)
    ADC = follower.follower()
    ADC.power_on()
    noise_level = get_trimmed_mean_amp(args_adc, chan, samples=10, max_dev=1.0)
    ADC.stop()
    logging.debug("[CALIBRATION] - Noise level = %f", noise_level)
    logging.debug("[CALIBRATION] - Find tx_coeff (what's the read amplitude it the current channel for a tx gain of 1)")
    tx_coeff = get_tx_coeff(args_adc, 0.0001, max_amp, 'tx', chan, noise_level)
    test_tx_gain = min(target_coeff, 0.3 * max_amp / tx_coeff)
    logging.debug("[CALIBRATION] - test_tx_gain = %f, tx_coeff = %f", test_tx_gain, tx_coeff)
    ADC = follower.follower()
    ADC.power_on()
    waveform_tx_only = ADC.get_sample_freq(**args_adc)
    ADC.stop()
    AWG.setGain('tx', 0, oneshot=True)
    logging.debug("[CALIBRATION] - Find bc_coeff (what's the read amplitude it the current channel for a bucking gain of 1)")
    bc_coeff = get_tx_coeff(args_adc, 0.0001, max_amp, chan, chan, noise_level)
    test_bc_gain = min(target_coeff, 0.7 * test_tx_gain * tx_coeff / bc_coeff, 0.3 * max_amp / bc_coeff)
    logging.debug("[CALIBRATION] - test_bc_gain = %f, bc_coeff = %f", test_bc_gain, bc_coeff)
    logging.debug("[CALIBRATION] - Use the coefficients we've found to find the best phase shift")
    AWG.program()
    AWG.setGain('tx', test_tx_gain)
    AWG.setGain(chan, test_bc_gain)
    AWG.run()
    best_phase = phase_min(args_adc, chan, samples=5)
    logging.info("[CALIBRATION] - Channel %s first pass results: tx=%f, bc=%f @ %f deg", chan, test_tx_gain, test_bc_gain, best_phase)
    # Now for the fine tuning:
    old_res = max_amp
    sig_test = -1
    for iter in range(10):
      if tx_coeff <= bc_coeff:
        tx_gain = target_coeff
        bc_gain = target_coeff * tx_coeff / bc_coeff
      else:
        bc_gain = target_coeff
        tx_gain = target_coeff * bc_coeff / tx_coeff
      logging.debug("[CALIBRATION] - Fine tuning, bc_gain = %f, tx_gain = %f", bc_gain, tx_gain)
      AWG.program()
      AWG.setGain('tx', tx_gain)
      AWG.setGain(chan, bc_gain)
      AWG.setPhaseShift(chan, best_phase, deg=True)
      AWG.run()
      current_amp = get_trimmed_mean_amp(args_adc, chan, ref_sample=waveform_tx_only)
      logging.debug("[CALIBRATION] - Bucking gain = %f, TX gain = %f, residual amp = %f" , bc_gain, tx_gain, current_amp)
      if abs(old_res) < abs(current_amp):
        sig_test *= -1
      old_res = current_amp
      if abs(current_amp) > target_snr * noise_level and iter < 10:
        #We still have work to do then...
        if tx_coeff <= bc_coeff:
          bc_coeff = (abs((target_coeff * tx_coeff) + sig_test * current_amp) / bc_gain + bc_coeff) / 2
        else:
          tx_coeff = (abs((target_coeff * bc_coeff) + sig_test * current_amp) / tx_gain + tx_coeff) / 2
        logging.debug("[CALIBRATION] - tx_coeff = %f, bc_coeff = %f", tx_coeff, bc_coeff)
      else:
        #We found acceptable parameters!
        logging.info("[CALIBRATION] - Channel %s residual signal amplitude: %f with tx=%f and bc=%f %f deg", chan, current_amp, tx_gain, bc_gain, best_phase)
        parameters['tx'].append(tx_gain)
        parameters['bc'].append({'gain': bc_gain, 'ps': best_phase})
        break
    # Record some metadata:
    if not calib_metadata.has_key("noise_level"):
      calib_metadata["noise_level"] = dict()
    if not calib_metadata.has_key("coeffs"):
      calib_metadata["coeffs"] = {'tx': dict(), 'bc': dict()}
    calib_metadata["coeffs"]["tx"][chan] = tx_coeff
    calib_metadata["coeffs"]["bc"][chan] = bc_coeff
    calib_metadata["noise_level"][chan] = noise_level
    if not calib_metadata.has_key("no_bucking_ps"):
      calib_metadata["no_bucking_ps"] = dict()
      for rec_chan in ["X", "Y", "Z"]:
        calib_metadata["no_bucking_ps"][rec_chan] = waveform_tx_only.get_phase_shift(ord(rec_chan) - ord('X'), deg=True)
  
  parameters["metadata"] = calib_metadata
  params = print_parameters(parameters)
  filename = time.strftime(str(config.test_params['tx_freq']) + "Hz_%Y%m%d-%H%M%S.calib")
  f = open(filename, 'w')
  f.write(str(params))
  f.close()
  if os.path.isfile('current.calib'):
    os.remove('current.calib')
  os.symlink(filename, 'current.calib')
  

def print_parameters(parameters):
  if not ('tx' in parameters and 'bc' in parameters):
    raise KeyError("The 'paramters' argumet to the 'print_parameters' function should  be a dictionary with at least the keys 'tx' and 'bc'")
  txmin = min(parameters['tx'])
  test_params =  {
   'bc1_dcgain': parameters['bc'][0]['gain'] / parameters['tx'][0] * txmin,
   'bc1_ps': parameters['bc'][0]['ps'],
   'bc2_dcgain': parameters['bc'][1]['gain'] / parameters['tx'][1] * txmin,
   'bc2_ps': parameters['bc'][1]['ps'],
   'bc3_dcgain': parameters['bc'][2]['gain'] / parameters['tx'][2] * txmin,
   'bc3_ps': parameters['bc'][2]['ps'],
   'tx_dcgain': txmin,
   'metadata': parameters['metadata']}
  pprint.pprint(test_params)
  return test_params

def get_tx_coeff(args_adc, start_gain, max_amp, chantx, chanrx, noise_level):
  txgain = start_gain / 2
  previous_tx = amplitude_tx = 0
  while txgain < 1 and amplitude_tx < max_amp / 2:
    txgain = min(2 * txgain, 1)
    AWG.setGain(chantx, txgain, oneshot=True)
    amplitude_tx = get_trimmed_mean_amp(args_adc, chanrx, samples=10)
    if amplitude_tx < previous_tx and amplitude_tx > 2 * noise_level:
      logging.debug("[CALIBRATION] - Saturation detected, jumping back. tx=%f, amp=%f", txgain, amplitude_tx)
      txgain /= 3
      previous_tx = 0
    else:
      previous_tx = amplitude_tx
    #print "CALIBRATION tx=%f,am=%f" % (txgain, amplitude_tx)
  return amplitude_tx / txgain
  
def phase_min(args_adc, chan, samples=3):
  amplitude_ps = []
  for phase in np.linspace(0, 360.0/64*63, 64):
    AWG.setPhaseShift(chan, phase, deg=True, oneshot=True)
    amplitude_ps.append(get_trimmed_mean_amp(args_adc, chan, samples=samples))
    print "CALIBPHASE: %d:%d" % (int(phase), int(amplitude_ps[-1]))
  fft = np.fft.rfft(np.square(amplitude_ps))
  angle = np.angle(fft[1], deg=True)%360
  minimum = (180 - angle) % 360
  return minimum

def get_trimmed_mean_amp(args_adc, chan, max_dev=None, samples=3, ref_sample=None):
  amps = []
  ADC = follower.follower()
  ADC.power_on()
  for i in range(samples):
    sample = ADC.get_sample_freq(**args_adc)
    sign = +1
    if ref_sample != None:
      if abs(sample.compare_phase_shift(ord(chan) - ord('X'), ref_sample)) > np.pi / 2:
        sign = -1
    amps.append(sign * sample.channels[ord(chan) - ord('X')].get_amplitude())
    #print "CALIBRATION - Last amp = %f" % (amps[-1])
  ADC.stop()
  avg = np.average(amps)
  if max_dev:
    max_dev_val = max_dev*avg
  else:
    max_dev_val = np.std(amps) * 2
  mask = np.abs(amps - avg) > max_dev_val
  return np.ma.array(amps, mask=mask).mean()


def zero_gains():
  AWG.program()
  for chan in AWG.REGISTERS_GAIN:
    AWG.setGain(chan, 0)
    AWG.setPhaseShift(chan, 0)
  AWG.run()

if __name__ == "__main__":
  signal.signal(signal.SIGINT, signal_handler)
  startup()
  logger()
  setPhase(150)
  finish()
