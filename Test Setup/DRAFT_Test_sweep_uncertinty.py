# Author: Ian Cassidy
# Ensemble of Input Power vs Output Power Sweeps

"""
Characterizes output-power measurement uncertainty as a function of:
    - Input power
    - Frequency span
    - Resolution bandwidth (RBW)

For each SPAN/RBW combination, the script repeats the input-power sweep.
It records raw measurements and produces summary statistics.

Outputs:
    raw_measurements.csv
    uncertainty_summary.csv
    configuration_summary.csv

Uncertainty estimates:
    - Mean output power (dBm)
    - Standard deviation across repeated measurements (dB)
    - Standard error of the mean (dB)
    - Approximate 95% confidence interval (dB)
    - Mean and total measurement time
"""

# Libraries
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyvisa as visa

# Experiment configuration
Pin = np.linspace(-60, 20, 201)     # Input power, dBm
f0 = 1.575                          # Fundamental frequency, GHz
modes = [1, 2]                      # Fundamental and second harmonic

# Logarithmic sampling
SPAN_sweep = np.logspace(np.log10(5e2), np.log10(5e6), 5)       # Hz
RBW_sweep = np.logspace(np.log10(1e2), np.log10(1e6), 5)        # Hz

N_REPEATS = 3

# Measurements until save
SAVE_EVERY = 10

# VISA addresses
VISA_ADDRESS_SG = ("USB0::0x0957::0x1F01::MY59100943::0::INSTR")
VISA_ADDRESS_SA = ("USB0::0x2A8D::0x0B0B::MY53400410::0::INSTR")

# Output folder
output_dir = Path("Data/pin_sweep/uncertainty")
output_dir.mkdir(parents=True, exist_ok=True)

run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

raw_path = output_dir / f"{run_id}_raw_measurements.csv"
summary_path = output_dir / f"{run_id}_uncertainty_summary.csv"
config_path = output_dir / f"{run_id}_configuration_summary.csv"

VISA_TIMEOUT_MS = 120000

# Utility functions
def save_raw(records):
    """Appends newly acquired records to the raw CSV"""
    if not records:
        return

    pd.DataFrame(records).to_csv(
        raw_path,
        mode="a",
        index=False,
        header=not raw_path.exists(),
    )
    records.clear()

def summarize_raw(raw):
    """
    Calculate repeatability statistics for each combination of
    SPAN, RBW, harmonic, and input power.

    """

    keys = ["SPAN_Hz", "RBW_Hz", "mode", "Pin_dBm"]
    grouped = raw.groupby(keys, dropna=False)

    summary = grouped.agg(
        N=("Pout_dBm", "count"),
        mean_Pout_dBm=("Pout_dBm", "mean"),
        std_Pout_dB=("Pout_dBm", "std"),
        mean_point_time_s=("point_time_s", "mean"),
        std_point_time_s=("point_time_s", "std"),
    ).reset_index()

    # Standard error of the mean across independent repeats.
    summary["SEM_dB"] = (summary["std_Pout_dB"] / np.sqrt(summary["N"]))

    # Approximate 95% confidence interval using 1.96*SEM.
    summary["CI95_halfwidth_dB"] = 1.96 * summary["SEM_dB"]
    summary["CI95_lower_dBm"] = (summary["mean_Pout_dBm"] - summary["CI95_halfwidth_dB"])
    summary["CI95_upper_dBm"] = (summary["mean_Pout_dBm"] + summary["CI95_halfwidth_dB"])

    return summary

# Main experiment
rm = None
inst_SG = None
inst_SA = None

raw_buffer = []
configuration_records = []

try:
    # Connect to instruments
    rm = visa.ResourceManager(r"C:\Windows\System32\visa32.dll")

    print(f"\nConnecting to signal generator: {VISA_ADDRESS_SG}")
    inst_SG = rm.open_resource(VISA_ADDRESS_SG)

    print(f"Connecting to spectrum analyzer: {VISA_ADDRESS_SA}")
    inst_SA = rm.open_resource(VISA_ADDRESS_SA)

    inst_SG.timeout = VISA_TIMEOUT_MS
    inst_SA.timeout = VISA_TIMEOUT_MS

    inst_SG.clear()
    inst_SA.clear()

    print("Signal generator:", inst_SG.query("*IDN?").strip())
    print("Spectrum analyzer:", inst_SA.query("*IDN?").strip())

    # Configure generator
    inst_SG.write(f":SOURce:FREQuency {f0}GHz")
    inst_SG.write(f":SOURce:POWer {Pin[0]}DBM")
    inst_SG.write(":OUTPut:STATe ON")

    # Configure analyzer
    inst_SA.write(":INIT:CONT OFF")
    inst_SA.write(":CALCulate:MARKer1:STATe ON")
    inst_SA.write(":CALCulate:MARKer1:MODE POSition")

    total_configs = len(SPAN_sweep) * len(RBW_sweep)
    config_number = 0

    experiment_start = time.perf_counter()

    for SPAN in SPAN_sweep:
        for RBW in RBW_sweep:

            config_number += 1

            print(
                f"\nConfiguration {config_number}/{total_configs}: "
                f"SPAN={SPAN:.6g} Hz, RBW={RBW:.6g} Hz"
            )

            config_start = time.perf_counter()
            config_timestamp = datetime.now().isoformat(timespec="seconds")

            inst_SA.write(f":BAND:RES {RBW}")
            inst_SA.write(":SWE:TIME:AUTO ON")
            inst_SA.write(f":FREQ:SPAN {SPAN}")
            inst_SA.query("*OPC?")

            for repeat in range(1, N_REPEATS + 1):
                print(f"  Repeat {repeat}/{N_REPEATS}")

                for M in modes:
                    harmonic_freq = M * f0

                    # Center the analyzer at the harmonic being measured
                    inst_SA.write(f":FREQ:CENT {harmonic_freq}GHz")
                    inst_SA.query("*OPC?")

                    for i, P in enumerate(Pin):
                        point_start = time.perf_counter()
                        measurement_timestamp = datetime.now().isoformat(timespec="milliseconds")

                        # Set input power
                        inst_SG.write(f":SOURce:POWer {P}DBM")
                        inst_SG.query("*OPC?")

                        # Trigger and wait for one completed sweep
                        inst_SA.write(":INIT:IMM")
                        inst_SA.query("*OPC?")

                        # Find the largest peak within the current span
                        inst_SA.write(":CALCulate:MARKer1:MAXimum")

                        peak_freq_hz = float(inst_SA.query(":CALCulate:MARKer1:X?"))
                        peak_amp_dbm = float(inst_SA.query(":CALCulate:MARKer1:Y?"))

                        expected_freq_hz = MF0 * 1e9
                        frequency_error_hz = peak_freq_hz - expected_freq_hz

                        point_elapsed = (time.perf_counter() - point_start)

                        raw_buffer.append({
                            "run_id": run_id,
                            "configuration": config_number,
                            "configuration_timestamp": config_timestamp,
                            "repeat": repeat,
                            "measurement_timestamp": measurement_timestamp,
                            "SPAN_Hz": float(SPAN),
                            "RBW_Hz": float(RBW),
                            "f0_GHz": f0,
                            "mode": M,
                            "harmonic_freq_GHz": harmonic_freq,
                            "Pin_dBm": float(P),
                            "Pout_dBm": peak_amp_dbm,
                            "peak_freq_Hz": peak_freq_hz,
                            "point_time_s": point_elapsed,
                        })

                        if len(raw_buffer) >= SAVE_EVERY:
                            save_raw(raw_buffer)

                    # Save data after each harmonic sweep
                    save_raw(raw_buffer)

            config_elapsed = time.perf_counter() - config_start

            configuration_records.append({
                "configuration": config_number,
                "configuration_timestamp": config_timestamp,
                "SPAN_Hz": float(SPAN),
                "RBW_Hz": float(RBW),
                "N_REPEATS": N_REPEATS,
                "N_Pin_points": len(Pin),
                "N_harmonics": len(modes),
                "configuration_elapsed_s": config_elapsed,
                "elapsed_per_repeat_s": (
                    config_elapsed / N_REPEATS
                ),
            })

            # Preserve progress even if a later configuration fails
            pd.DataFrame(configuration_records).to_csv(
                config_path, index=False
            )

            print(
                f"  Configuration complete in "
                f"{config_elapsed:.1f} s "
                f"({config_elapsed / 60:.2f} min)"
            )

finally:
    # Always turn off the RF output and close VISA resources
    if inst_SG is not None:
        try:
            inst_SG.write(":OUTPut:STATe OFF")
        except Exception as exc:
            print("Warning: could not turn off RF output:", exc)

    save_raw(raw_buffer)

    if inst_SG is not None:
        inst_SG.close()

    if inst_SA is not None:
        inst_SA.close()

    if rm is not None:
        rm.close()

# Analyze measurements
if raw_path.exists():
    raw = pd.read_csv(raw_path)

    if not raw.empty:
        summary = summarize_raw(raw)
        summary.to_csv(summary_path, index=False)

        print("\nExperiment finished.")
        print(f"Raw data: {raw_path}")
        print(f"Uncertainty summary: {summary_path}")
        print(f"Configuration timing: {config_path}")

        print(
            "\nTotal elapsed time: "
            f"{time.perf_counter() - experiment_start:.1f} s"
        )
    else:
        print("No measurements were collected.")
else:
    print("No raw measurement file was created.")
