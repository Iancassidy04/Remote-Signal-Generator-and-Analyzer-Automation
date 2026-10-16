# Author: Ian Cassidy
# Oct 16th, 2026

'''
Quantifies the precision vs. speed trade-off (Pareto Frontier) for the desired input power sweep, target frequency and its harmonics

Narrower RBW lowers the instrument noise floor and increases selectivity, but increases sweep time.
Wider SPAN provides broader spectral visibility around harmonics, but lowers discrete frequency resolution.
Standard deviationand duration per point are used to plot the Measurement Uncertainty vs. Time Elapsed to find the knee.

Logarithmic spacing is used for efficiently searching the parameter space

'''

from matplotlib.lines import Line2D
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path

import pyvisa as visa
import pandas as pd
import numpy as np
import time
import sys

''' Initialize the Experiment '''

# Obtain the VISA address (or alias) from Keysight Connection Expert
VISA_ADDRESS_SG = 'USB0::0x0957::0x1F01::MY59100943::0::INSTR'
VISA_ADDRESS_SA = 'USB0::0x2A8D::0x0B0B::MY53400410::0::INSTR'

# Input Power, Span and RBW sweeps with logarithmic spacing

# Frequency span sweep
SPAN_sweep = np.array([
    10e1,
    10e2,
    30e2,
    100e2,
    300e2,
    1e3
])

# Resolution bandwidth sweep
RBW_sweep = np.array([
    10000,
    30000,
    1e5,
    3e5,
    4e5,
    6e6
])

Pdbm_in = np.linspace(-80, -50, 16)

F0 = 1.575        # Set fundamental frequency (GHz)
modes = [1, 2]      # Define harmonics
SAVE = 10           # Loops between data storage
N = 3               # Repeats


# Create output directorys
output_dir = Path("Uncertainty")
output_dir.mkdir(
    parents=True, 
    exist_ok=True
    )

run_id = datetime.now().strftime("%Y-%m-%d_%H-%M")
run_dir = output_dir / run_id
run_dir.mkdir(
    parents=True, 
    exist_ok=True
    )

config_path =  run_dir / "configuration.csv"
uncert_path = run_dir / "uncertainty.csv"
raw_path = run_dir / "raw.csv"


''' Utility functions '''

def save_raw(records):
    if records:
        pd.DataFrame(records).to_csv(raw_path, 
                            mode = "a", 
                        index = False,
                    header=not raw_path.exists(),) 
        records.clear()
    else:
        return

# Calculate repeatability statistics for each sweep combination
def summarize_raw(raw):
    keys = ["SPAN_Hz", "RBW_Hz", "mode", "Pin_dBm"]
    grouped = raw.groupby(keys, dropna=False)

    summary = grouped.agg(
        mean_point_time_s=("point_time_s", "mean"),
        std_point_time_s=("point_time_s", "std"),
        mean_Pout_dBm=("Pout_dBm", "mean"),
        std_Pout_dB=("Pout_dBm", "std"),
        N=("Pout_dBm", "count"),
    ).reset_index()

    # Standard error of the mean across independent repeats
    summary["SEM_dB"] = (summary["std_Pout_dB"] / np.sqrt(summary["N"]))

    # Approximate 95% confidence interval using 1.96*SEM.
    summary["CI95_halfwidth_dB"] = 4.303 * summary["SEM_dB"]
    summary["CI95_lower_dBm"] = (summary["mean_Pout_dBm"] - summary["CI95_halfwidth_dB"])
    summary["CI95_upper_dBm"] = (summary["mean_Pout_dBm"] + summary["CI95_halfwidth_dB"])
    return summary


''' Connect instruments and configure constant settings '''

rm = None
inst_SG = None
inst_SA = None
raw_buffer = []
configuration_records = []
experiment_start = time.perf_counter()

try:
    rm = visa.ResourceManager('C:\\Windows\\System32\\visa32.dll')      # Define VISA Resource Manager

    print('\nConnecting to: {}'.format(VISA_ADDRESS_SG))
    inst_SG = rm.open_resource(VISA_ADDRESS_SG)

    print('\nConnecting to: {}'.format(VISA_ADDRESS_SA))
    inst_SA = rm.open_resource(VISA_ADDRESS_SA)

    # Set I/O timeout
    inst_SG.timeout = 120000
    inst_SA.timeout = 120000

    # Clear the remote interface
    inst_SG.clear()
    inst_SA.clear()

    print("Spectrum analyzer:", inst_SA.query("*IDN?").strip())
    print("Signal generator:", inst_SG.query("*IDN?").strip())

    # Configure generator
    inst_SG.write(f":SOURce:POWer {Pdbm_in[0]}DBM")
    inst_SG.write(f":SOURce:FREQuency {F0}GHz")
    inst_SG.write(":OUTPut:STATe ON")

    # Configure analyzer
    inst_SA.write(":INIT:CONT OFF")
    inst_SA.write(":CALCulate:MARKer1:STATe ON")
    inst_SA.write(":CALCulate:MARKer1:MODE POSition")

    total_configs = len(SPAN_sweep) * len(RBW_sweep)
    config_number = 0


    ''' Sweep frequency span and resolution bandwidth '''

    for SPAN in SPAN_sweep:
        for RBW in RBW_sweep:

            config_timestamp = datetime.now().isoformat(timespec="seconds")
            config_start = time.perf_counter()
            config_number += 1

            # Configure signal analyzer
            inst_SA.write(f":FREQ:SPAN {SPAN}")
            inst_SA.write(":SWE:TIME:AUTO ON")
            inst_SA.write(f":BAND:RES {RBW}")
            inst_SA.query("*OPC?")

            for n in range(1, N + 1):
                for M in modes:
                    MF0 = M * F0

                    # Center the analyzer at the harmonic being measured
                    inst_SG.write(f":SOURce:FREQuency {MF0}GHz")
                    inst_SA.write(f":FREQ:CENT {MF0}GHz")
                    inst_SA.query("*OPC?")

                    for i, P in enumerate(Pdbm_in):
                        measurement_timestamp = datetime.now().isoformat(timespec="milliseconds")
                        # Start timing before changing input power
                        time_start = time.perf_counter()

                        # Set input power
                        inst_SG.write(f":SOURce:POWer {P}DBM")
                        inst_SG.query("*OPC?")

                        # Trigger a new analyzer sweep
                        inst_SA.write(":INIT:IMM")
                        inst_SA.query("*OPC?")

                        # Locate largest peak within span
                        inst_SA.write(":CALCulate:MARKer1:MAXimum")
                
                        peak_freq_hz = float(inst_SA.query(":CALCulate:MARKer1:X?"))
                        peak_amp_dbm = float(inst_SA.query(":CALCulate:MARKer1:Y?"))
                        
                        expected_freq_hz = MF0 * 1e9
                        frequency_error_hz = peak_freq_hz - expected_freq_hz

                        time_elapsed = (time.perf_counter() - time_start)

                        # Store raw measurement with sweep information
                        raw_buffer.append({
                            "measurement_timestamp": measurement_timestamp,
                            "configuration_timestamp": config_timestamp,
                            "frequency_error": frequency_error_hz,
                            "configuration": config_number,
                            "point_time_s": time_elapsed,
                            "peak_freq_Hz": peak_freq_hz,
                            "Pout_dBm": peak_amp_dbm,
                            "harmonic_freq_GHz": MF0,
                            "SPAN_Hz": float(SPAN),
                            "RBW_Hz": float(RBW),
                            "Pin_dBm": float(P),
                            "run_id": run_id,
                            "f0_GHz": F0,
                            "repeat": n,
                            "mode": M,
                            })
                        
                        # Periodically save accumulated raw measurements to CSV
                        if len(raw_buffer) >= SAVE:
                            save_raw(raw_buffer)

            config_elapsed = time.perf_counter() - config_start
            configuration_records.append({
                "N_REPEATS": N,
                "RBW_Hz": float(RBW),
                "SPAN_Hz": float(SPAN),
                "N_harmonics": len(modes),
                "N_Pin_points": len(Pdbm_in),
                "configuration": config_number,
                "configuration_elapsed_s": config_elapsed,
                "configuration_timestamp": config_timestamp,
                "elapsed_per_repeat_s": (config_elapsed / N),
                })

            # Preserve progress even if a later configuration fails
            pd.DataFrame(configuration_records).to_csv(config_path, index=False)


    ''' Save and evaluate results '''
finally:
    if inst_SG is not None:
        try:
            inst_SG.write(":OUTPut:STATe OFF")
        except Exception as exc:
            print("Warning: could not turn off RF output:", exc)

    try:
        save_raw(raw_buffer)
    except Exception as exc:
        print("Warning: could not save remaining raw data:", exc)


    # Close SG, SA, and VS resource manager
    for instrument in (inst_SG, inst_SA, rm):
        if instrument is not None:
            try:
                instrument.close()
            except Exception as exc:
                print("Warning: error closing resource:", exc)

# Analyze measurements
if raw_path.exists():
    raw = pd.read_csv(raw_path)

    if not raw.empty:
        summary = summarize_raw(raw)
        summary.to_csv(uncert_path, index=False)

        print("\nExperiment finished.")
        print(f"Raw data: {raw_path}")
        print(f"Uncertainty summary: {uncert_path}")
        print(f"Configuration timing: {config_path}")

        print(f"\nTotal elapsed time: \n {time.perf_counter() - experiment_start:.1f} s")
    else:
        print("No measurements were collected.")
else:
    print("No raw measurement file was created.")



''' Plot and evaluate precision vs. speed '''

# Load configuration timing from CSV for consistent plotting
if config_path.exists():
    config_df = pd.read_csv(config_path)
else:
    config_df = pd.DataFrame(configuration_records)

if not summary.empty and not config_df.empty:

    # Merge configuration-level timing with point-level uncertainty data
    plot_df = summary.merge(
        config_df[
            [
                "SPAN_Hz",
                "RBW_Hz",
                "elapsed_per_repeat_s"
            ]
        ],
        on=["SPAN_Hz", "RBW_Hz"],
        how="left"
    )

    # Short readable labels for the plot legends
    plot_df["config_label"] = (
        "Span=" + plot_df["SPAN_Hz"].map(lambda x: f"{x:.0e}") +
        " Hz, RBW=" + plot_df["RBW_Hz"].map(lambda x: f"{x:.0e}") +
        " Hz"
    )

    # Exclude invalid or undefined standard deviations
    valid_df = plot_df[
        np.isfinite(plot_df["std_Pout_dB"]) &
        np.isfinite(plot_df["elapsed_per_repeat_s"]) &
        (plot_df["elapsed_per_repeat_s"] > 0)
    ].copy()

    # Pareto-style plot: repeatability vs. elapsed time
    # Each point is one configuration at one input power.
    # Lower standard deviation and shorter time are better.

    fig, ax = plt.subplots()

    for mode in sorted(valid_df["mode"].unique()):
        mode_df = valid_df[valid_df["mode"] == mode]

        ax.scatter(
            mode_df["elapsed_per_repeat_s"],
            mode_df["std_Pout_dB"],
            label=f"{mode}f0",
            alpha=0.65,
            s=35
        )

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Elapsed time per complete repeat (s)")
    ax.set_ylabel("Output-power standard deviation (dB)")
    ax.set_title("Measurement Precision vs. Speed")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(title="Harmonic")
    fig.tight_layout()
    fig.savefig(run_dir / "pareto_precision_vs_time.png", dpi=300)
    plt.show()

    # Mean output power vs. input power
    # One subplot per harmonic one curve per span/RBW pair.

    for mode in sorted(summary["mode"].unique()):
        mode_df = summary[summary["mode"] == mode]

        fig, ax = plt.subplots(figsize=(11, 7))

        for label, group in mode_df.groupby(
            ["SPAN_Hz", "RBW_Hz"],
            sort=True
        ):
            span, rbw = label
            label = f"Span={span:.0e} Hz, RBW={rbw:.0e} Hz"
            group = group.sort_values("Pin_dBm")

            ax.plot(
                group["Pin_dBm"],
                group["mean_Pout_dBm"],
                marker=".",
                markersize=3,
                linewidth=1,
                label=label
            )

        ax.set_xlabel("Input power (dBm)")
        ax.set_ylabel("Mean measured output power (dBm)")
        ax.set_title(f"Mean Output Power vs. Input Power — {mode}f0")
        ax.grid(True, alpha=0.3)
        ax.legend(
            title="Span / RBW",
            fontsize=7,
            ncol=2
        )
        fig.tight_layout()
        fig.savefig(
            run_dir / f"mean_Pout_vs_Pin_mode_{mode}.png",
            dpi=300
        )
        plt.show()

    # Standard deviation vs. input power
    # Shows input-power regions where repeatability is poor.

    for mode in sorted(summary["mode"].unique()):
        mode_df = summary[summary["mode"] == mode]

        fig, ax = plt.subplots(figsize=(11, 7))

        for label, group in mode_df.groupby(
            ["SPAN_Hz", "RBW_Hz"],
            sort=True
        ):
            span, rbw = label
            label = f"Span={span:.0e} Hz, RBW={rbw:.0e} Hz"
            group = group.sort_values("Pin_dBm")

            ax.plot(
                group["Pin_dBm"],
                group["std_Pout_dB"],
                marker=".",
                markersize=3,
                linewidth=1,
                label=label
            )

        ax.set_xlabel("Input power (dBm)")
        ax.set_ylabel("Output-power standard deviation (dB)")
        ax.set_title(f"Standard Deviation vs. Input Power — {mode}f0")
        ax.grid(True, alpha=0.3)
        ax.legend(
            title="Span / RBW",
            fontsize=7,
            ncol=2
        )
        fig.tight_layout()
        fig.savefig(
            run_dir / f"std_Pout_vs_Pin_mode_{mode}.png",
            dpi=300
        )
        plt.show()