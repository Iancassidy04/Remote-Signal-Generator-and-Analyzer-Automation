
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

# File
file = Path(r'Data\p_freq_in_sweep\BEST_B9416_series_MMDL301_SD\2026-10-01_17-08-18.csv')

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

        # Keep the actual CSV column name
        frequency_columns.append(col)

    except ValueError:
        pass

frequencies = np.array(frequencies)

# Find average frequency
avg_freq = np.nanmean(frequencies)

# Separate f0 and 2f0
f0_list = []
f20_list = []

for F, col in zip(frequencies, frequency_columns):
    if F < avg_freq:
        f0_list.append((F, col))
    else:
        f20_list.append((F, col))

# Calculate average Pout for each frequency
average_pout = []

for f0, col in f0_list:
    average_pout.append(np.nanmean(df[col].values))

# Find minimum and maximum average Pout
min_avg = min(average_pout)
max_avg = max(average_pout)

# Create color range
colors = []

for avg in average_pout:

    if max_avg == min_avg:
        ratio = 0.5
    else:
        ratio = (avg - min_avg) / (max_avg - min_avg)

    # Light blue
    blue = np.array([0.2, 0.5, 0.9])

    # Light red
    red = np.array([0.9, 0.2, 0.2])

    color = blue * (1 - ratio) + red * ratio

    colors.append(color)

# f0 2D PLOT
plt.figure()
for i, (f0, col) in enumerate(f0_list):

    plt.plot(df[pin_col], df[col], color=colors[i], label=f"{f0 / 1e9:.5g} GHz")

plt.xlabel("Pin (dBm)")
plt.ylabel("Measured Power (dBm)")
plt.title("Measured f0 Output Power vs Input Power")
plt.grid(True)
plt.legend()

# f0 3D PLOT
fig = plt.figure()
ax = fig.add_subplot(111, projection="3d")

for i, (f0, col) in enumerate(f0_list):

    # Frequency value repeated for every Pin
    frequency = np.full(len(df), f0 / 1e9)
    ax.plot(df[pin_col].values, frequency, df[col].values, color=colors[i])

ax.set_xlabel("Pin (dBm)")
ax.set_ylabel("Frequency (GHz)")
ax.set_zlabel("Measured Power (dBm)")
ax.set_title("f0 Output Power vs Pin and Frequency")

# 2f0 2D PLOT
plt.figure()
for i, (f20, col) in enumerate(f20_list):
    plt.plot(df[pin_col], df[col], color=colors[i], label=f"{f20 / 1e9:.5g} GHz")

plt.xlabel("Pin (dBm)")
plt.ylabel("Measured Power (dBm)")
plt.title("Measured 2f0 Output Power vs Input Power")
plt.grid(True)
plt.legend()

# 2f0 3D PLOT
fig = plt.figure()
ax = fig.add_subplot(111, projection="3d")

for i, (f20, col) in enumerate(f20_list):

    # Frequency value repeated for every Pin
    frequency = np.full(len(df), f20 / 1e9)

    print(df[col].values)
    ax.plot(df[pin_col].values, frequency, df[col].values, color=colors[i])

ax.set_xlabel("Pin (dBm)")
ax.set_ylabel("Frequency (GHz)")
ax.set_zlabel("Measured Power (dBm)")

ax.set_title("2f0 Output Power vs Pin and Frequency")

plt.show()
