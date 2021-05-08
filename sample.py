import numpy as np

class waveform(object):
  def __init__(self, frequency=None, value=0j):
    self.frequency = frequency
    self.value = value

  def get_amplitude(self, reference=None):
    return np.absolute(self.value - self._check_reference(reference).value)

  def get_phase_shift(self, reference=None, deg=0):
    if reference:
      return np.angle(self.value / self._check_reference(reference).value, deg)
    else:
      return np.angle(self.value, deg)

  def _check_reference(self, reference=None):
    if reference:
      if reference.frequency != self.frequency:
        raise ValueError('The two waiveforms being compared are not at the same frequency!')
    else:
      reference = waveform()
    return reference

class sample(object):
  def __init__(self, reference, channels = []):
    self.reference = reference
    self.channels = []
    for channel in channels:
      self.add_channel(channel)

  def add_channel(self, channel):
    if channel.frequency != self.reference.frequency:
      raise ValueError('Samples can only contain waveforms of same frequency')
    self.channels.append(channel)

  def get_phase_shift(self, channel, deg=0):
    return self.channels[channel].get_phase_shift(self.reference, deg)

  def compare_phase_shift(self, channel, sample, deg=0):
    ps1 = self.get_phase_shift(channel)
    ps2 = sample.get_phase_shift(channel)
    result = (ps1 - ps2 + np.pi) % (2*np.pi) - np.pi
    if deg:
      result *= 180/np.pi
    return result

  def __str__(self):
    ostring="%d;%d" % (self.reference.get_amplitude(), int(self.reference.get_phase_shift(deg=1)))
    for channel in self.channels:
      ostring += ";%d;%d" % (channel.get_amplitude(), int(channel.get_phase_shift(deg=1)))
    return ostring

