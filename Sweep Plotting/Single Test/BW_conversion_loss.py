# Author: Ian Cassidy

'''
Plots conversion loss vs input power for a range of frequencies as 3D plot

Intended for comparing the filters passband and the diodes harmonic efficiency

'''

import matplotlib.pyplot as plt
from pathlib import Path
import pandas as pd
import numpy as np

# File
file = Path(r"Data\p_freq_in_sweep\MMDL301_series_Shunt_Cap1_series_TL\2026-10-05_20-35-13.csv")

# Read CSV
df = pd.read_csv(file)

# Clean column names
df.columns = (
    df.columns
    .astype(str)
    .str.replace("*", "", regex=False)
    .str.replace('"', "", regex=False)
    .str.strip()
)

# First column is Pin
pin_col = df.columns[0]

# Convert Pin to numbers
df[pin_col] = pd.to_numeric(df[pin_col], errors="coerce")

# Convert all measurement columns to numbers
for col in df.columns[1:]:
    df[col] = (
        df[col]
        .astype(str)
        .str.replace("*", "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
    )

    df[col] = pd.to_numeric(df[col], errors="coerce")

# Get frequencies
frequencies = []
frequency_columns = []

for col in df.columns[1:]:
    try:
        frequency = float(
            col.replace("GHz", "")
               .replace("ghz", "")
               .strip()
        )

        # Convert GHz -> Hz
        frequencies.append(frequency * 1e9)

        # Keep actual CSV column name
        frequency_columns.append(col)

    except ValueError:
        pass

frequencies = np.array(frequencies)

# Separate f0 and 2f0
avg_freq = np.nanmean(frequencies)

f0_list = []
f20_list = []

for F, col in zip(frequencies, frequency_columns):
    if F < avg_freq:
        f0_list.append((F, col))
    else:
        f20_list.append((F, col))

# Color based on average Pout
average_pout = []

for freq, col in f0_list:

    average_pout.append(
        np.nanmean(df[col].values)
    )

min_avg = min(average_pout)
max_avg = max(average_pout)

colors = []

for avg in average_pout:
    if max_avg == min_avg:
        ratio = 0.5
    else:
        ratio = (avg - min_avg) / (max_avg - min_avg)

    blue = np.array([0.2, 0.5, 0.9])    # Light blue
    red = np.array([0.9, 0.2, 0.2])     # Light red

    color = blue * (1 - ratio) + red * ratio
    colors.append(color)

# F0 CONVERSION LOSS WATERFALL
plt.figure(figsize=(10, 7))

# Vertical offset between traces
offset = 5

for i, (f0, col) in enumerate(f0_list):
    CL = df[pin_col].values - df[col].values    # Conversion loss
    CL_offset = CL + i * offset                 # Offset each frequency

    plt.plot(
        df[pin_col].values,
        CL_offset,
        color=colors[i],
        linewidth=1.5
    )

    # Frequency label at right side
    valid = ~np.isnan(CL_offset)

    if np.any(valid):
        last_index = np.where(valid)[0][-1]

        plt.text(
            df[pin_col].values[last_index] + 0.2,
            CL_offset[last_index],
            f"{f0 / 1e9:.5g} GHz",
            fontsize=8,
            va="center"
        )

plt.xlabel("Pin (dBm)")
plt.ylabel("Conversion Loss + Offset (dB)")

plt.title(
    "f0 Conversion Loss vs Input Power\n"
    "Frequency Waterfall"
)

plt.grid(True, alpha=0.3)
plt.tight_layout()

# 2f0 CONVERSION LOSS WATERFALL

# Use the same color scheme based on average Pout
average_pout_2 = []
for freq, col in f20_list:
    average_pout_2.append(np.nanmean(df[col].values))

min_avg = min(average_pout_2)
max_avg = max(average_pout_2)

colors_2 = []

for avg in average_pout_2:
    if max_avg == min_avg:
        ratio = 0.5
    else:
        ratio = (avg - min_avg) / (max_avg - min_avg)

    blue = np.array([0.2, 0.5, 0.9])
    red = np.array([0.9, 0.2, 0.2])

    color = blue * (1 - ratio) + red * ratio
    colors_2.append(color)

plt.figure(figsize=(10, 7))

for i, (f20, col) in enumerate(f20_list):
    CL = df[pin_col].values - df[col].values    # Conversion loss
    CL_offset = CL + i * offset                 # Vertical offset

    plt.plot(
        df[pin_col].values,
        CL_offset,
        color=colors_2[i],
        linewidth=1.5
    )

    valid = ~np.isnan(CL_offset)

    if np.any(valid):
        last_index = np.where(valid)[0][-1]

        plt.text(
            df[pin_col].values[last_index] + 0.2,
            CL_offset[last_index],
            f"{f20 / 1e9:.5g} GHz",
            fontsize=8,
            va="center"
        )

plt.xlabel("Pin (dBm)")
plt.ylabel("Conversion Loss + Offset (dB)")

plt.title(
    "2f0 Conversion Loss vs Input Power\n"
    "Frequency Waterfall"
)

plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# BEST f0 CL
best_f0 = None
for f0, col in f0_list:

    CL = df[pin_col].values - df[col].values
    index = np.nanargmin(CL)
    best_CL = CL[index]
    best_Pin = df[pin_col].values[index]

    if best_f0 is None or best_CL < best_f0["CL"]:
        best_f0 = {
            "frequency": f0,
            "CL": best_CL,
            "Pin": best_Pin
        }

print("\nBEST f0:")
print(f"Frequency = {best_f0['frequency'] / 1e9:.5g} GHz")
print(f"Pin       = {best_f0['Pin']:.2f} dBm")
print(f"CL        = {best_f0['CL']:.2f} dB")

# BEST 2f0 CL
best_2f0 = None
for f20, col in f20_list:

    CL = df[pin_col].values - df[col].values
    print(CL)
    index = np.nanargmin(CL)

    best_CL = CL[index]
    best_Pin = df[pin_col].values[index]

    if best_2f0 is None or best_CL < best_2f0["CL"]:
        best_2f0 = {
            "frequency": f20,
            "CL": best_CL,
            "Pin": best_Pin
        }

print("\nBEST 2f0:")
print(f"Frequency = {best_2f0['frequency'] / 1e9:.5g} GHz")
print(f"Pin       = {best_2f0['Pin']:.2f} dBm")
print(f"CL        = {best_2f0['CL']:.2f} dB")