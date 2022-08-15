test_params = dict(
  tx_freq=5000,         #max is PWM_freq/clock_divider but this theoretical max is also the AWG's resolution
                        #  This affects the value of the 0x3E and 0x3F registers, a 24bit value calculated thus:
                        #  DDS_TW=int(tx_freq*(clock_divider*2**24/PWM_freq)
  tx_dcgain=1.0,        #Transmission coil DC gain. Valid values are between ]-2.0 and +2.0[
  bc1_dcgain=0.0,       #Bucking coil 1 DC gain. Valid values are between ]-2.0 and +2.0[
  bc2_dcgain=0.0,       #Bucking coil 2 DC gain. Valid values are between ]-2.0 and +2.0[
  bc3_dcgain=0.0,       #Bucking coil 3 DC gain. Valid values are between ]-2.0 and +2.0[
  bc1_ps=0.0,           #Bucking coil 1 phase shift in degrees.
  bc2_ps=0.0,           #Bucking coil 2 phase shift in degrees.
  bc3_ps=0.0,            #Bucking coil 3 phase shift in degrees.
  
  duration =10,     # produce signal for 10 seconds if not specified in function call
)

hardware = dict(
  AWG = dict(
    PWM_freq=32e7,       #Frequency of pulses sent to the AWG, in Hz
    PWM_duty_cycle=50,  #Duty cycle of the pulse, in percents
    clock_divider=2,     #The AD9106 Evaluation Board has a clock divider, what is is set to?
                        #  Default=8, must reflect the physical state
  ),

  AWGon=True,		# set AWG and signal generation on. Default should be True
  
  
  
  IO = dict(
    gain=3              #Analog gain, integer in [0, 1, 2, 3]
  ),
)
