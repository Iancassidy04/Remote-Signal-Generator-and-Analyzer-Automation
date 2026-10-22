# Author: Ian Cassidy

'''
Plots conversion loss vs input power as a 2D plot

Intended for analyzing the diodes harmonic efficieny at a target frequency

'''

import matplotlib.pyplot as plt
from pathlib import Path
import pandas as pd

# CSV file
csv_path = Path(r"Data\pin_sweep\SMS_1p5mm_2stub_20p6mm_TL_v1\2026-10-13_17-30-22.csv")

df = pd.read_csv(csv_path)

# Get DUT and date from filename/path
DUT = csv_path.parent.name
date = csv_path.stem

# Input power column
Pin = df["Pin"]

# Conversion loss column
f0 = df.iloc[:, 1] 
f02 = df.iloc[:, 2]

# Plot conversion loss
plt.plot(Pin, Pin - f0, marker=".", label="Fundamental")
plt.plot(Pin, Pin - f02, marker=".", label="2nd Harmonic")
plt.xlabel("Input Power (dBm)")
plt.ylabel("Conversion Loss (dB)")
plt.title(f"{DUT}: Conversion Loss\n Test Date: {date}")
plt.grid(True)
plt.legend()    
plt.show()
