import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

# CSV file
csv_path = Path(r"Data/pin_sweep/THRU/2026-10-01_13-41-31.csv")

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
