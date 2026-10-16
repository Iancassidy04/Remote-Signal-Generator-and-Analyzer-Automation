# Author: Ian Cassidy
# Sweep Input Power and Measure Output Power
# OCT 1st 2026

'''
Signal Generator (SG): KEYSIGHT N5183B EXG Vector Signal Generator

Signal Analyzer (SA): KEYSIGHT N9020A EXA Signal Analyzer

UVM, Votey Hall, Room 334B

'''

# Libraries
from datetime import date
import time
from pathlib import Path
import pyvisa as visa
import sys
import numpy as np
import pandas as pd

DUT = "SAW_MMDL301_STUBMATCH"

BW = 0.12 # GHz
f0 = 1.575 # Center frequency in GHz
Pin = np.linspace(-30, 20, 11) # Input power sweep from X dBm to Y dBm in Z steps
Fin = np.linspace(f0 - BW/2, f0 + BW/2, 51)
modes = [1, 2]                  # Harmonics to analyze (1 = fundamental, 2 = 2nd harmonic, etc.)

SPAN = 5e4                          # Frequency span in Hz
RBW = 1e2                        # Resolution bandwidth in Hz

# Obtain the VISA address (or alias) from Keysight Connection Expert
VISA_ADDRESS_SG = 'USB0::0x0957::0x1F01::MY59100943::0::INSTR'
VISA_ADDRESS_SA = 'USB0::0x2A8D::0x0B0B::MY53400410::0::INSTR'

# CSV location inside repo
timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")

csv_path = Path(f"Data/p_freq_in_sweep/{DUT}/{timestamp}.csv")

csv_path.parent.mkdir(parents=True, exist_ok=True)

# Create dataframe with one row for every Pin value
df = pd.DataFrame({"Pin": Pin})

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

inst_SA.write(":INIT:CONT OFF")         # Stop continuous sweeping
inst_SA.write(f":FREQ:CENT {f0}GHz")    # Center frequency
inst_SA.write(f":FREQ:SPAN {SPAN}")     # Frequency span
inst_SA.write(f":BAND:RES {RBW}")       # Resolution bandwidth
inst_SA.write(":SWE:TIME:AUTO ON")      # Let analyzer determine appropriate sweep time

# Wait for settings to finish
inst_SA.write("*WAI")

# Query actual sweep time selected by analyzer
sweep_time = float(inst_SA. query(":SWE:TIME?"))

print(f"Analyzer sweep time: {sweep_time:.3f} seconds")
proceed = input(f'The sweep will take {sweep_time * 1.1 * len(Pin) * len(Fin) * len(modes)} seconds.\nDo you want to proceed? (y/n): ')
if proceed.lower() != 'y':
    print("Aborting sweep.")
    inst_SG.close()
    inst_SA.close()
    sys.exit()

# Set startup parameters for the signal generator
inst_SG.write(f':SOURce:POWer {min(Pin)}DBM')
inst_SG.write(f':SOURce:FREQuency {f0}GHz')

# Turn on the output of the signal generator
inst_SG.write(':OUTPut:STATe ON')
results = {}

for F in Fin:
    inst_SA.write(f":FREQ:CENT {F}GHz")
    inst_SG.write(f':SOURce:FREQuency {F}GHz')

    current_freq = inst_SG.query(':SOURce:FREQuency?')

    for M in modes:
        harmonic_freq = M * F
        freq_col = f"{harmonic_freq:g}GHz"

        # Create array for this frequency
        results[freq_col] = np.full(len(Pin), np.nan)

        inst_SA.write(f":FREQ:CENT {harmonic_freq:g}GHz")
        inst_SG.write(f':SOURce:FREQuency {F}GHz')

        current_freq = inst_SG.query(':SOURce:FREQuency?')

        for i, P in enumerate(Pin):

            inst_SG.write(f':SOURce:POWer {P}DBM')
            inst_SA.write(":INIT:IMM")

            inst_SA.query("*OPC?")

            inst_SA.write(':CALCulate:MARKer1:MAXimum')

            peak_freq = inst_SA.query(':CALCulate:MARKer1:X?')
            peak_amp = inst_SA.query(':CALCulate:MARKer1:Y?')

            # Store result in dictionary
            results[freq_col][i] = float(peak_amp)

            print(f'Current Output Frequency: {current_freq}')
            print(f"Peak Frequency: {float(peak_freq):,.0f} Hz")
            print(f"Peak Amplitude: {float(peak_amp):.2f} dBm")

# Combine all results at once
results_df = pd.DataFrame(results)
df = pd.concat([df, results_df],axis=1)
df.to_csv(csv_path, index=False)

# Turn off the output of the signal generator
inst_SG.write(':OUTPut:STATe OFF')

# Close instrument connection
inst_SG.close()
inst_SA.close()

print('Done.')