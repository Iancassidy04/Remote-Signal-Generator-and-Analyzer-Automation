# Author: Ian Cassidy
# Instrument control and sweep engine used by sweep_gui.py

'''
Signal Generator (SG): KEYSIGHT N5183B EXG Vector Signal Generator

Signal Analyzer (SA): KEYSIGHT N9020A EXA Signal Analyzer

Runs the same measurement as "Sweep Tests/input_power_v2.py" (single frequency)
and "Sweep Tests/input_power_frequency.py" (input power + frequency), but driven
by a SweepConfig instead of variables at the top of a script, so the GUI can run it
in a background thread, report progress, and stop it safely.

CSV format is unchanged:  Pin, <M*f0>GHz, ...  (one column per harmonic per frequency)
'''

from dataclasses import dataclass, field
from pathlib import Path
import threading
import time
import math
import random

import numpy as np
import pandas as pd

VISA_LIBRARY = r"C:\Windows\System32\visa32.dll"

PIN_SWEEP = "pin_sweep"
FREQ_SWEEP = "p_freq_in_sweep"


class SweepAborted(Exception):
    """Raised when the user cancels or stops a sweep."""


# ---------------------------------------------------------------------------
# VISA helpers
# ---------------------------------------------------------------------------

def get_resource_manager():
    import pyvisa as visa  # imported here so plotting works on PCs without pyvisa

    try:
        return visa.ResourceManager(VISA_LIBRARY)
    except Exception:
        return visa.ResourceManager()  # fall back to the default VISA backend


def list_resources():
    """Return every VISA address visible to this PC."""
    rm = get_resource_manager()
    try:
        return list(rm.list_resources())
    finally:
        rm.close()


def identify(address, timeout_ms=5000):
    """Open an instrument, return its *IDN? string, and close it again."""
    rm = get_resource_manager()
    try:
        inst = rm.open_resource(address)
        try:
            inst.timeout = timeout_ms
            inst.clear()
            return inst.query("*IDN?").strip()
        finally:
            inst.close()
    finally:
        rm.close()


# ---------------------------------------------------------------------------
# Sweep configuration
# ---------------------------------------------------------------------------

@dataclass
class SweepConfig:
    dut: str
    sweep_type: str            # PIN_SWEEP or FREQ_SWEEP
    pin_start: float           # dBm
    pin_stop: float            # dBm
    pin_points: int
    f0: float                  # GHz (center frequency)
    modes: list                # harmonics, e.g. [1, 2]
    span: float                # Hz
    rbw: float                 # Hz
    sg_address: str
    sa_address: str
    data_root: Path            # e.g. <repo>/Data
    bw: float = 0.0            # GHz, frequency sweep only
    f_points: int = 1          # frequency sweep only
    dry_run: bool = False
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d_%H-%M-%S"))

    @property
    def pin(self):
        return np.linspace(self.pin_start, self.pin_stop, self.pin_points)

    @property
    def fin(self):
        if self.sweep_type == FREQ_SWEEP and self.f_points > 1:
            return np.linspace(self.f0 - self.bw / 2, self.f0 + self.bw / 2, self.f_points)
        return np.array([self.f0])

    @property
    def n_measurements(self):
        return len(self.pin) * len(self.fin) * len(self.modes)

    @property
    def csv_path(self):
        return Path(self.data_root) / self.sweep_type / self.dut / f"{self.timestamp}.csv"


# ---------------------------------------------------------------------------
# Sweep runner
# ---------------------------------------------------------------------------

class SweepRunner:
    """
    Runs one sweep. Communicates with the GUI only through callbacks:
        emit(message_tuple)  -> ("log", text) | ("progress", done, total, elapsed)
                                | ("data", dataframe) | ("idn", role, address, idn)
        confirm(text)        -> bool, asked once the analyzer sweep time is known
    """

    def __init__(self, cfg, emit, confirm, stop_event=None):
        self.cfg = cfg
        self.emit = emit
        self.confirm = confirm
        self.stop_event = stop_event or threading.Event()
        self.csv_path = None

    def log(self, text):
        self.emit(("log", text))

    def _open(self):
        cfg = self.cfg
        if cfg.dry_run:
            sg = SimulatedSG()
            return sg, SimulatedSA(sg), None

        rm = get_resource_manager()
        instruments = []
        for role, address in (("signal generator", cfg.sg_address),
                              ("signal analyzer", cfg.sa_address)):
            self.log(f"Connecting to {role}: {address}")
            try:
                instruments.append(rm.open_resource(address))
            except Exception as e:
                for inst in instruments:
                    inst.close()
                rm.close()
                raise ConnectionError(f"Unable to connect to the {role} at {address}.\n{e}")
        return instruments[0], instruments[1], rm

    def run(self):
        cfg = self.cfg
        sg = sa = rm = None
        try:
            sg, sa, rm = self._open()

            # Set I/O timeout to 5 seconds and clear the remote interface
            for inst in (sg, sa):
                inst.timeout = 5000
                inst.clear()

            # Check connections and print instrument identification
            idn_sg = sg.query("*IDN?").strip()
            idn_sa = sa.query("*IDN?").strip()
            self.log(f"SG: {idn_sg}")
            self.log(f"SA: {idn_sa}")
            if not cfg.dry_run:
                self.emit(("idn", "SG", cfg.sg_address, idn_sg))
                self.emit(("idn", "SA", cfg.sa_address, idn_sa))

            sa.write(":INIT:CONT OFF")                   # Single-sweep mode, triggered per point
            sa.write(f":FREQ:CENT {cfg.f0}GHz")          # Center frequency
            sa.write(f":FREQ:SPAN {cfg.span}")           # Frequency span
            sa.write(f":BAND:RES {cfg.rbw}")             # Resolution bandwidth
            sa.write(":SWE:TIME:AUTO ON")                # Analyzer picks the sweep time
            sa.query("*OPC?")                            # Wait for settings to finish

            sweep_time = float(sa.query(":SWE:TIME?"))
            # Make sure *OPC? never times out on slow (narrow RBW) sweeps
            sa.timeout = int(max(5000, sweep_time * 1000 * 5 + 2000))

            n = cfg.n_measurements
            estimate = sweep_time * 1.1 * n
            self.log(f"Analyzer sweep time: {sweep_time:.3f} s  ->  estimated run time {fmt_duration(estimate)}")

            summary = (
                f"Device: {cfg.dut}\n"
                f"Sweep: {cfg.pin_start:g} to {cfg.pin_stop:g} dBm, {cfg.pin_points} points"
                + (f"\nFrequency: {cfg.fin[0]:.4f} to {cfg.fin[-1]:.4f} GHz, {len(cfg.fin)} points"
                   if len(cfg.fin) > 1 else f"\nFrequency: {cfg.f0:g} GHz")
                + f"\nHarmonics: {', '.join(str(m) for m in cfg.modes)}"
                f"\nRBW {fmt_hz(cfg.rbw)}, span {fmt_hz(cfg.span)}"
                f"\n\nMeasurements: {n}"
                f"\nAnalyzer sweep time: {sweep_time:.3f} s"
                f"\nEstimated duration: {fmt_duration(estimate)}"
                + ("\n\nWARNING: input power above +20 dBm." if max(cfg.pin_start, cfg.pin_stop) > 20 else "")
                + f"\n\nSaving to: {cfg.csv_path.parent.name}/{cfg.csv_path.name}"
                + "\n\nStart the sweep?"
            )
            if not self.confirm(summary):
                raise SweepAborted("Sweep cancelled before starting.")

            self.csv_path = cfg.csv_path
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            self.log(f"Saving to {self.csv_path}")

            pin = cfg.pin
            df = pd.DataFrame({"Pin": pin})

            # Startup parameters for the signal generator, then RF on
            sg.write(f":SOURce:POWer {min(pin)}DBM")
            sg.write(f":SOURce:FREQuency {cfg.fin[0]}GHz")
            sg.write(":OUTPut:STATe ON")

            done = 0
            t0 = time.time()
            for F in cfg.fin:
                sg.write(f":SOURce:FREQuency {F}GHz")
                for M in cfg.modes:
                    harmonic_freq = M * F
                    col = f"{harmonic_freq:g}GHz"
                    df[col] = np.nan
                    col_idx = df.columns.get_loc(col)

                    sa.write(f":FREQ:CENT {harmonic_freq:g}GHz")

                    for i, P in enumerate(pin):
                        if self.stop_event.is_set():
                            raise SweepAborted("Sweep stopped by user.")

                        sg.write(f":SOURce:POWer {P}DBM")

                        # Trigger one analyzer sweep and wait for it to finish
                        sa.write(":INIT:IMM")
                        sa.query("*OPC?")

                        # Peak search
                        sa.write(":CALCulate:MARKer1:MAXimum")
                        peak_freq = float(sa.query(":CALCulate:MARKer1:X?"))
                        peak_amp = float(sa.query(":CALCulate:MARKer1:Y?"))

                        df.iat[i, col_idx] = peak_amp
                        df.to_csv(self.csv_path, index=False)   # Save after every measurement

                        done += 1
                        self.log(f"f0 {F:.4f} GHz | M={M} | Pin {P:7.2f} dBm | "
                                 f"peak {peak_freq / 1e9:.6f} GHz  {peak_amp:8.2f} dBm")
                        self.emit(("progress", done, n, time.time() - t0))
                        self.emit(("data", df.copy()))

            self.log("Sweep complete.")
            return self.csv_path

        finally:
            if sg is not None:
                try:
                    sg.write(":OUTPut:STATe OFF")       # RF off, even after an error or stop
                    self.log("SG RF output OFF.")
                except Exception as e:
                    self.log(f"!! Could not turn SG output off: {e}")
            if sa is not None:
                try:
                    sa.write(":INIT:CONT ON")            # Leave the analyzer free-running
                except Exception:
                    pass
            for inst in (sg, sa, rm):
                if inst is not None:
                    try:
                        inst.close()
                    except Exception:
                        pass


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt_duration(seconds):
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_hz(value):
    for unit, mult in (("GHz", 1e9), ("MHz", 1e6), ("kHz", 1e3)):
        if abs(value) >= mult:
            return f"{value / mult:g} {unit}"
    return f"{value:g} Hz"


# ---------------------------------------------------------------------------
# Simulated instruments for "Dry run" (no hardware needed)
# ---------------------------------------------------------------------------

def _scpi_value(cmd):
    token = cmd.split()[-1].upper()
    for unit, mult in (("GHZ", 1e9), ("MHZ", 1e6), ("KHZ", 1e3), ("HZ", 1.0), ("DBM", 1.0)):
        if token.endswith(unit):
            return float(token[: -len(unit)]) * mult
    return float(token)


def _db_sum(*levels):
    return 10 * math.log10(sum(10 ** (p / 10) for p in levels))


class SimulatedSG:
    def __init__(self):
        self.timeout = 5000
        self.freq = 1e9
        self.power = -100.0
        self.on = False

    def clear(self):
        pass

    def close(self):
        pass

    def write(self, cmd):
        c = cmd.upper()
        if "OUTP" in c:
            self.on = c.strip().endswith("ON")
        elif "POW" in c:
            self.power = _scpi_value(cmd)
        elif "FREQ" in c:
            self.freq = _scpi_value(cmd)

    def query(self, cmd):
        c = cmd.upper()
        if "*IDN?" in c:
            return "Simulated,N5183B,DRYRUN,1.0"
        if "FREQ" in c:
            return str(self.freq)
        return "1"


class SimulatedSA:
    """Toy Schottky-doubler model: good enough to exercise the GUI and plots."""

    def __init__(self, sg):
        self.sg = sg
        self.timeout = 5000
        self.center = 1e9
        self.span = 5e4
        self.rbw = 100.0

    def clear(self):
        pass

    def close(self):
        pass

    def write(self, cmd):
        c = cmd.upper()
        if "CENT" in c:
            self.center = _scpi_value(cmd)
        elif "SPAN" in c:
            self.span = _scpi_value(cmd)
        elif "BAND" in c:
            self.rbw = _scpi_value(cmd)
        elif "INIT:IMM" in c:
            time.sleep(0.004)

    def _level(self):
        floor = -110 + 10 * math.log10(max(self.rbw, 1) / 100)
        sg = self.sg
        if not sg.on:
            return floor + random.gauss(0, 1.5)
        M = max(1, round(self.center / sg.freq))
        if abs(self.center - M * sg.freq) > self.span / 2:
            return floor + random.gauss(0, 1.5)
        pin = sg.power
        detune = (sg.freq / 1e9 - 1.578) / 0.06
        match = 3 * detune ** 2
        if M == 1:
            p = pin - 3 - match
        elif M == 2:
            p = -_db_sum(-(2 * pin - 18), -(pin - 9)) - 2 * match
        else:
            p = -_db_sum(-(3 * pin - 45), -(pin - 20)) - 3 * match
        return _db_sum(p, floor) + random.gauss(0, 0.15)

    def query(self, cmd):
        c = cmd.upper()
        if "*IDN?" in c:
            return "Simulated,N9020A,DRYRUN,1.0"
        if "*OPC?" in c:
            return "1"
        if "SWE:TIME?" in c:
            return "0.004"
        if "MARK" in c and "X?" in c:
            return str(self.center)
        if "MARK" in c and "Y?" in c:
            return f"{self._level():.3f}"
        return "0"