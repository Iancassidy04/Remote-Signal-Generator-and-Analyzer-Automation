import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from matplotlib.colors import Normalize

file = Path(r'Data\p_freq_in_sweep\SAW_MMDL301_STUBMATCH\2026-10-14_17-53-09.csv')

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
    df[col] = pd.to_numeric(
        df[col]
        .astype(str)
        .str.replace("*", "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip(),
        errors="coerce"
    )

# Remove rows without valid input power
df = df.dropna(subset=[pin_col]).copy()


frequencies = []
frequency_columns = []

for col in df.columns[1:]:
    try:
        frequency = float(
            col.lower().replace("ghz", "").strip()
        )

        # Convert GHz to Hz
        frequencies.append(frequency * 1e9)
        frequency_columns.append(col)

    except ValueError:
        continue

frequencies = np.array(frequencies)

if len(frequencies) == 0:
    raise ValueError(
        "No frequency columns found. Check the CSV headers."
    )

# Split frequency sweep into f0 and 2f0 groups
avg_freq = np.nanmean(frequencies)

f0_list = []
f20_list = []

for F, col in zip(frequencies, frequency_columns):
    if F < avg_freq:
        f0_list.append((F, col))
    else:
        f20_list.append((F, col))


pin = df[pin_col].to_numpy(dtype=float)

# Sort input powers for consistent plotting
pin_order = np.argsort(pin)
pin = pin[pin_order]

# Reorder rows in the dataframe
df = df.iloc[pin_order].reset_index(drop=True)

# Frequency axes in GHz
f0_freq = np.array([F / 1e9 for F, col in f0_list])
f20_freq = np.array([F / 1e9 for F, col in f20_list])


def get_measurement_matrix(freq_list):
    """
    Returns a matrix with shape:
        (number of frequencies, number of input powers)

    Each matrix element is one measured output-power value.
    """
    return np.vstack([
        df[col].to_numpy(dtype=float)
        for F, col in freq_list
    ])


# Output power matrices, in dBm
pout_f0 = get_measurement_matrix(f0_list)
pout_f20 = get_measurement_matrix(f20_list)

# Conversion loss in dB:
# CL = Pin - Pout
# Broadcast Pin across all frequencies
cl_f0 = pin[np.newaxis, :] - pout_f0
cl_f20 = pin[np.newaxis, :] - pout_f20


def global_norm(data):
    valid = data[np.isfinite(data)]

    if len(valid) == 0:
        return Normalize(vmin=0, vmax=1)

    vmin = valid.min()
    vmax = valid.max()

    if vmin == vmax:
        vmax = vmin + 1

    return Normalize(vmin=vmin, vmax=vmax)


# Same scale for f0 and 2f0 output power
pout_norm = global_norm(
    np.concatenate([
        pout_f0.ravel(),
        pout_f20.ravel()
    ])
)

# Same scale for f0 and 2f0 conversion loss
cl_norm = global_norm(
    np.concatenate([
        cl_f0.ravel(),
        cl_f20.ravel()
    ])
)



def plot_waterfall(
    pin,
    frequencies,
    values,
    title,
    colorbar_label,
    cmap,
    norm
):
    """
    X axis: input power (dBm)
    Y axis: frequency (GHz)
    Color: measured value

    Each measurement is represented by its own colored cell.
    """

    if len(frequencies) == 0:
        print(f"Skipping empty plot: {title}")
        return

    fig, ax = plt.subplots(figsize=(12, 7))

    # pcolormesh creates a 2D color-mapped surface.
    # Frequency and Pin determine the position of each value.
    mesh = ax.pcolormesh(
        pin,
        frequencies,
        values,
        shading="nearest",
        cmap=cmap,
        norm=norm,
        rasterized=True
    )

    # Colorbar
    cbar = fig.colorbar(mesh, ax=ax, pad=0.02)
    cbar.set_label(colorbar_label)

    ax.set_xlabel("Input Power, Pin (dBm)")
    ax.set_ylabel("Frequency (GHz)")
    ax.set_title(title)

    ax.grid(False)
    fig.tight_layout()


# ============================================================
# f0 OUTPUT POWER
# ============================================================

plot_waterfall(
    pin=pin,
    frequencies=f0_freq,
    values=pout_f0,
    title="f0 Output Power vs Input Power and Frequency",
    colorbar_label="Output Power (dBm)",
    cmap="turbo",
    norm=pout_norm
)




plot_waterfall(
    pin=pin,
    frequencies=f0_freq,
    values=cl_f0,
    title="f0 Conversion Loss vs Input Power and Frequency",
    colorbar_label="Conversion Loss (dB)",
    cmap="viridis",
    norm=cl_norm
)


plot_waterfall(
    pin=pin,
    frequencies=f20_freq,
    values=pout_f20,
    title="2f0 Output Power vs Input Power and Frequency",
    colorbar_label="Output Power (dBm)",
    cmap="turbo",
    norm=pout_norm
)


plot_waterfall(
    pin=pin,
    frequencies=f20_freq,
    values=cl_f20,
    title="2f0 Conversion Loss vs Input Power and Frequency",
    colorbar_label="Conversion Loss (dB)",
    cmap="viridis",
    norm=cl_norm
)


plt.show()