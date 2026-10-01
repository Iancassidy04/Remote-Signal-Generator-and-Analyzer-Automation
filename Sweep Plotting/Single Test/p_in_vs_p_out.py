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

# Plot every frequency column
for col in df.columns[1:]:
    plt.plot(Pin, df[col], marker=".", label=col)

plt.xlabel("Input Power (dBm)")
plt.ylabel("Output Power (dBm)")
plt.title(f"{DUT}: Input vs Output Power\n Test Date: {date}")
plt.grid(True)
plt.legend()    
plt.show()