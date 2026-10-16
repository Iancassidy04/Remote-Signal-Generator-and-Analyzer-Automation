# Ian Cassidy
# Test Connection to Signal Generator
# OCT 1st 2026

import time
import pyvisa as visa
import sys

# Programmatically query the Python version and print information
print('\nSystem version fn(sys.ver)):\n\t{}'.format(sys.version))

# Obtain the VISA address (or alias) from Keysight Connection Expert
VISA_ADDRESS = 'USB0::0x0957::0x1F01::MY59100943::0::INSTR'

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


# Set startup parameters for the signal generator
inst.write(':SOURce:POWer 0DBM')
inst.write(':SOURce:FREQuency 1GHz')

# Turn on the output of the signal generator
inst.write(':OUTPut:STATe ON')

for i in range(1, 6):
    inst.write(f':SOURce:FREQuency {i}GHz')             # Set the frequency of the signal generator to i GHz
    current_freq = inst.query(':SOURce:FREQuency?')     # Verify the current frequency setting

    print(f'Current Frequency: {current_freq}')
    time.sleep(1.0)

# Turn off the output of the signal generator
inst.write(':OUTPut:STATe OFF')

# Close instrument connection
inst.close()

print('Done.')