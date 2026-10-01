# Ian Cassidy
# Test Connection to Signal Analyzer
# OCT 1st 2026

from time import time
import pyvisa as visa
import sys

# Programmatically query the Python version and print information
print('\nSystem version fn(sys.ver)):\n\t{}'.format(sys.version))

# Obtain the VISA address (or alias) from Keysight Connection Expert
VISA_ADDRESS = 'USB0::0x2A8D::0x0B0B::MY53400410::0::INSTR'

# Define VISA Resource Manager
rm = visa.ResourceManager('C:\\Windows\\System32\\visa32.dll')

# Open connection to the instrument via the related VISA address:
try:
    print('\nConnecting to: {}'.format(VISA_ADDRESS))
    inst = rm.open_resource(VISA_ADDRESS)
except Exception:
    print('Unable to connect to Instrument at {}.  Aborting.\n'
          .format(VISA_ADDRESS))
    sys.exit()

# Set I/O timeout to 5 seconds
inst.timeout = 5000

# Clear the remote interface
inst.clear()

IDN = str(inst.query('*IDN?'))
print('Connected to: {}'.format(IDN))

inst.write(':CALCulate:MARKer1:MAXimum')        # Query the frequency of Marker 1 at the peak of the signal
peak_freq = inst.query(':CALCulate:MARKer1:X?') # Find the position of Marker 1 on the frequency axis
peak_amp = inst.query(':CALCulate:MARKer1:Y?')  # Read the amplitude at that peak

print(f"Peak Frequency: {float(peak_freq):,} Hz")
print(f"Peak Amplitude: {float(peak_amp)} dBm")

# Close instrument connection
inst.close()

print('Done.')