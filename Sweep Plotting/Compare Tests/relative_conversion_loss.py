
# Author: Ian Cassidy

'''
Plots the difference in conversion loss between exactly two CSV tests.

Tests can be located in different DUT folders or subdirectories.

Measurements are interpolated onto a common input-power grid restricted
to the overlapping Pin range. No extrapolation is performed.

Delta CL = CL_Test2 - CL_Test1

Negative Delta CL means Test 2 has lower conversion loss.
'''

import matplotlib.pyplot as plt
from pathlib import Path
import pandas as pd
import numpy as np

data_folder = Path("Data")

# Find CSV files in all subdirectories
csv_files = sorted(data_folder.rglob("*.csv"))

if len(csv_files) < 2:
    raise ValueError(f"At least two CSV files are required in {data_folder.resolve()}.")

# Select exactly two tests
print("\nAvailable tests:")

for i, file in enumerate(csv_files, 1):
    print(f"{i}: {file.relative_to(data_folder)}")

test1_number = int(input("\nSelect Test 1 (reference): ")) - 1
test2_number = int(input("Select Test 2 (comparison): ")) - 1

if not (0 <= test1_number < len(csv_files)):
    raise ValueError("Invalid Test 1 selection.")

if not (0 <= test2_number < len(csv_files)):
    raise ValueError("Invalid Test 2 selection.")

if test1_number == test2_number:
    raise ValueError("Please select two different tests.")

test1_path = csv_files[test1_number]
test2_path = csv_files[test2_number]

print(f"\nTest 1: {test1_path}")
print(f"Test 2: {test2_path}")

# Read CSV files
df1 = pd.read_csv(test1_path)
df2 = pd.read_csv(test2_path)

# Extract Pin and output power
# Assumes column 0 = Pin, column 1 = fundamental output,
# and column 2 = second-harmonic output.

required_columns = 3

if df1.shape[1] < required_columns or df2.shape[1] < required_columns:
    raise ValueError("Each CSV must contain Pin and two output-power columns.")

# Convert measurement columns to numeric
for df in (df1, df2):
    for col in df.columns[:3]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df.dropna(subset=df.columns[:3], inplace=True)

    # Average duplicate Pin measurements, if present
    df = df.sort_values("Pin") if "Pin" in df.columns else df

# Explicitly use the first column as Pin
pin_col1 = df1.columns[0]
pin_col2 = df2.columns[0]

# Rename to standard column names
df1 = df1.rename(columns={
    pin_col1: "Pin",
    df1.columns[1]: "Pout_f0",
    df1.columns[2]: "Pout_2f0"
})

df2 = df2.rename(columns={
    pin_col2: "Pin",
    df2.columns[1]: "Pout_f0",
    df2.columns[2]: "Pout_2f0"
})

# Sort and average any duplicate input-power values
df1 = df1[["Pin", "Pout_f0", "Pout_2f0"]]
df2 = df2[["Pin", "Pout_f0", "Pout_2f0"]]

df1 = df1.groupby("Pin", as_index=False).mean().sort_values("Pin")
df2 = df2.groupby("Pin", as_index=False).mean().sort_values("Pin")

# Determine common input-power range
Pin_min = max(df1["Pin"].min(), df2["Pin"].min())
Pin_max = min(df1["Pin"].max(), df2["Pin"].max())

if Pin_min >= Pin_max:
    raise ValueError("The tests do not have an overlapping input-power range.")

# Create a common grid using all measured Pin values in the overlap
Pin1 = df1.loc[df1["Pin"].between(Pin_min, Pin_max), "Pin"].to_numpy()
Pin2 = df2.loc[df2["Pin"].between(Pin_min, Pin_max), "Pin"].to_numpy()
Pin_common = np.unique(np.concatenate((Pin1, Pin2)))

# Interpolate both tests onto the common grid
Pout1_2f0 = np.interp(Pin_common, df1["Pin"], df1["Pout_2f0"])
Pout2_2f0 = np.interp(Pin_common, df2["Pin"], df2["Pout_2f0"])

# Calculate conversion loss
CL1_2f0 = Pin_common - Pout1_2f0
CL2_2f0 = Pin_common - Pout2_2f0

# Difference in conversion loss: Test 2 - Test 1
Delta_CL_2f0 = CL2_2f0 - CL1_2f0

# Plot
plt.figure(f)
plt.plot(Pin_common, Delta_CL_2f0, marker=".", label="2nd Harmonic")
plt.axhline(0, color="black", linestyle="--", linewidth=1)
plt.xlabel("Input Power (dBm)")
plt.ylabel(r"$\Delta CL$ (dB)")
plt.title(
    "Conversion Loss Difference\n"
    f"Test 2 - Test 1\n"
    f"{test2_path.stem} - {test1_path.stem}"
)

plt.grid(True)
plt.legend()
plt.tight_layout()
plt.show()
