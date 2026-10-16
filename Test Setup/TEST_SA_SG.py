# Ian Cassidy
# Test Connection to Signal Generator and Signal Analyzer
# OCT 1st 2026

'''
Signal Generator (SG): KEYSIGHT N5183B EXG Vector Signal Generator

Signal Analyzer (SA): KEYSIGHT N9020A EXA Signal Analyzer

UVM, Votey Hall, Room 334B

'''

# Libraries
import time
import pyvisa as visa
import sys

# Obtain the VISA address (or alias) from Keysight Connection Expert
VISA_ADDRESS_SG = 'USB0::0x0957::0x1F01::MY59100943::0::INSTR'
VISA_ADDRESS_SA = 'USB0::0x2A8D::0x0B0B::MY53400410::0::INSTR'

# Define VISA Resource Manager
rm = visa.ResourceManager('C:\\Windows\\System32\\visa32.dll')


# Open connection to the instrument via the related VISA address:
try:
    print('\nConnecting to: {}'.format(VISA_ADDRESS_SG))
    inst_SG = rm.open_resource(VISA_ADDRESS_SG)
except Exception:
    print('Unable to connect to Instrument at {}.  Aborting.\n'
          .format(VISA_ADDRESS_SG))
    sys.exit()

try:
    print('\nConnecting to: {}'.format(VISA_ADDRESS_SA))
    inst_SA = rm.open_resource(VISA_ADDRESS_SA)
except Exception:
    print('Unable to connect to Instrument at {}.  Aborting.\n'
          .format(VISA_ADDRESS_SA))
    sys.exit()

# Set I/O timeout to 5 seconds
inst_SG.timeout = 5000
inst_SA.timeout = 5000

# Clear the remote interface
inst_SG.clear()
inst_SA.clear()

# Check connections and print instrument identification
IDN_SG = str(inst_SG.query('*IDN?'))
IDN_SA = str(inst_SA.query('*IDN?'))
print('Connected to: {}'.format(IDN_SG))
print('Connected to: {}'.format(IDN_SA))

# Set startup parameters for the signal generator
inst_SG.write(':SOURce:POWer 0DBM')
inst_SG.write(':SOURce:FREQuency 1GHz')

# Turn on the output of the signal generator
inst_SG.write(':OUTPut:STATe ON')

for i in range(1, 6):
    inst_SG.write(f':SOURce:FREQuency {i}GHz')              # Set output frequency
    current_freq = inst_SG.query(':SOURce:FREQuency?')      # Verify the current frequency setting

    time.sleep(0.5)                                         # Wait for the signal to stabilize
    
    inst_SA.write(':CALCulate:MARKer1:MAXimum')             # Query the frequency of Marker 1 at the peak of the signal
    peak_freq = inst_SA.query(':CALCulate:MARKer1:X?')      # Find the position of Marker 1 on the frequency axis
    peak_amp = inst_SA.query(':CALCulate:MARKer1:Y?')       # Read the amplitude at that peak

    print(f'Current Ouput Frequency: {current_freq}')
    print(f"Peak Frequency: {float(peak_freq):,} Hz")
    print(f"Peak Amplitude: {float(peak_amp)} dBm")

    time.sleep(0.5)                                         # Wait for the signal to stabilize before the next iteration

# Turn off the output of the signal generator
inst_SG.write(':OUTPut:STATe OFF')

# Close instrument connection
inst_SG.close()
inst_SA.close()

print('Done.')