# Author: Ian Cassidy
# Data loading and plotting used by sweep_gui.py

'''
Reads pin_sweep and p_freq_in_sweep CSVs and draws them onto a matplotlib Figure
embedded in the GUI. Same calculations as the scripts in "Sweep Plotting/":

    Conversion loss  CL (dB) = Pin (dBm) - Pout (dBm)
    Delta CL         = CL(Test 2) - CL(Test 1), interpolated over the overlapping Pin range
'''

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import cm
from matplotlib.colors import Normalize

PLOT_CL = "Conversion loss vs input power"
PLOT_POUT = "Output power vs input power"
PLOT_CL_MAP = "Conversion loss map (frequency sweep)"
PLOT_POUT_MAP = "Output power map (frequency sweep)"
PLOT_BEST_CL = "Best conversion loss vs frequency"
PLOT_DELTA_CL = "ΔCL between two tests"

PLOT_TYPES = [PLOT_CL, PLOT_POUT, PLOT_CL_MAP, PLOT_POUT_MAP, PLOT_BEST_CL, PLOT_DELTA_CL]

MAX_LEGEND_ENTRIES = 12


class PlotError(Exception):
    """A plot that cannot be drawn with the current selection."""


def harmonic_name(mode):
    return "f0" if mode == 1 else f"{mode}f0"


def harmonic_title(mode):
    return {1: "Fundamental (f0)", 2: "2nd harmonic (2f0)", 3: "3rd harmonic (3f0)"}.get(
        mode, f"{mode}th harmonic ({mode}f0)")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class TestData:
    """One measurement: Pout per harmonic, indexed by Pin, one column per fundamental frequency (GHz)."""

    def __init__(self, label, by_mode, path=None, kind=None):
        self.label = label
        self.by_mode = by_mode       # {mode: DataFrame(index=Pin, columns=fundamental GHz)}
        self.path = path
        self.kind = kind

    @property
    def modes(self):
        return sorted(self.by_mode)

    @property
    def fundamentals(self):
        funds = set()
        for frame in self.by_mode.values():
            funds.update(frame.columns)
        return sorted(funds)

    def pout(self, mode, fund):
        """(Pin, Pout) arrays for one harmonic at one fundamental frequency, NaNs removed."""
        series = self.by_mode[mode][fund]
        pin = series.index.to_numpy(dtype=float)
        y = series.to_numpy(dtype=float)
        mask = ~np.isnan(y) & ~np.isnan(pin)
        order = np.argsort(pin[mask])
        return pin[mask][order], y[mask][order]

    def nearest_fund(self, freq, mode=None):
        funds = np.array(sorted(self.by_mode[mode].columns) if mode in self.by_mode else self.fundamentals)
        if freq is None:
            freq = float(np.median(funds))
        return float(funds[np.argmin(np.abs(funds - freq))])


def _clean(text):
    return str(text).replace("*", "").replace('"', "").strip()


def from_frame(df, label, path=None, kind=None):
    """Build TestData from a sweep DataFrame (Pin column + '<freq>GHz' columns)."""
    df = df.copy()
    df.columns = [_clean(c) for c in df.columns]
    pin_col = df.columns[0]
    for col in df.columns:
        df[col] = pd.to_numeric(df[col].astype(str).map(_clean), errors="coerce")
    df = df.dropna(subset=[pin_col])

    columns = []
    for col in df.columns[1:]:
        try:
            columns.append((col, float(col.lower().replace("ghz", "").strip())))
        except ValueError:
            continue
    if not columns:
        raise PlotError(f"No '<frequency>GHz' columns found in {label}.")

    # Sweep scripts write each frequency step as a group: f0, 2*f0, ... (one column per harmonic).
    # A column that is an integer multiple (>1) of the current group's base frequency is a
    # harmonic of it; anything else starts a new group. Works for narrow and wide sweeps.
    pin = df[pin_col].to_numpy(dtype=float)
    by_mode = {}
    base = None
    for col, freq in columns:
        if freq <= 0:
            continue
        mode = 1
        if base is not None:
            ratio = freq / base
            if round(ratio) >= 2 and abs(ratio - round(ratio)) < 1e-3 * ratio:
                mode = int(round(ratio))
        if mode == 1:
            base = freq
        by_mode.setdefault(mode, {})[round(freq / mode, 6)] = df[col].to_numpy(dtype=float)
    if not by_mode:
        raise PlotError(f"No usable frequency columns in {label}.")

    by_mode = {
        m: pd.DataFrame(cols, index=pd.Index(pin, name="Pin")).sort_index(axis=1)
        for m, cols in by_mode.items()
    }
    return TestData(label, by_mode, path=path, kind=kind)


def load_test(path):
    path = Path(path)
    df = pd.read_csv(path)
    label = f"{path.parent.name} – {path.stem}"
    return from_frame(df, label, path=path, kind=path.parent.parent.name)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

def draw(fig, plot_type, tests, modes, freq=None, title=None):
    """Clear fig and draw plot_type. Returns a one-line status string."""
    fig.clear()
    if not tests:
        raise PlotError("Pick a test to plot.")
    if not modes:
        raise PlotError("Select at least one harmonic.")

    if plot_type in (PLOT_CL, PLOT_POUT):
        return _lines(fig, tests, modes, freq, cl=(plot_type == PLOT_CL), title=title)
    if plot_type in (PLOT_CL_MAP, PLOT_POUT_MAP):
        return _map(fig, tests, modes, cl=(plot_type == PLOT_CL_MAP))
    if plot_type == PLOT_BEST_CL:
        return _best_cl(fig, tests, modes)
    if plot_type == PLOT_DELTA_CL:
        return _delta_cl(fig, tests, modes, freq)
    raise PlotError(f"Unknown plot type: {plot_type}")


def _axes_per_mode(fig, modes, sharey=False):
    axes = []
    for i, _ in enumerate(modes):
        share = axes[0] if (sharey and axes) else None
        axes.append(fig.add_subplot(1, len(modes), i + 1, sharey=share))
    return axes


def _funds_for(test, freq, mode):
    if freq is None:
        return list(test.by_mode[mode].columns)
    return [test.nearest_fund(freq, mode)]


def _lines(fig, tests, modes, freq, cl, title=None):
    quantity = "Conversion Loss (dB)" if cl else "Output Power (dBm)"
    axes = _axes_per_mode(fig, modes)
    single = len(tests) == 1
    plotted = 0

    for ax, mode in zip(axes, modes):
        color_index = 0
        colorbar_norm = None
        n_lines = 0
        for test in tests:
            if mode not in test.by_mode:
                continue
            funds = _funds_for(test, freq, mode)
            by_freq_color = single and len(funds) > 1
            if by_freq_color:
                colorbar_norm = Normalize(min(funds), max(funds))
            for fund in funds:
                pin, pout = test.pout(mode, fund)
                if len(pin) == 0:
                    continue
                y = pin - pout if cl else pout
                if by_freq_color:
                    color = cm.viridis(colorbar_norm(fund))
                    label = None
                else:
                    color = f"C{color_index % 10}"
                    color_index += 1
                    label = test.label if len(funds) == 1 and freq is None else f"{test.label} @ {fund:.4f} GHz"
                ax.plot(pin, y, marker=".", markersize=3, linewidth=1.2, color=color, label=label)
                n_lines += 1
                plotted += 1

        ax.set_title(harmonic_title(mode))
        ax.set_xlabel("Input Power (dBm)")
        ax.set_ylabel(quantity)
        ax.grid(True, alpha=0.4)
        if colorbar_norm is not None:
            fig.colorbar(cm.ScalarMappable(norm=colorbar_norm, cmap=cm.viridis), ax=ax,
                         label="Fundamental frequency (GHz)")
        elif 0 < n_lines <= MAX_LEGEND_ENTRIES:
            ax.legend(fontsize=8)

    if plotted == 0:
        raise PlotError("The selected tests have no data for the selected harmonics yet.")

    names = ", ".join(dict.fromkeys(t.label.split(" – ")[0] for t in tests))
    fig.suptitle(title or f"{names}: {'Conversion Loss' if cl else 'Output Power'}")

    if cl:
        bits = []
        for mode in modes:
            best = _best_point(tests, mode, freq)
            if best:
                bits.append(f"{harmonic_name(mode)} min CL {best[0]:.2f} dB at Pin {best[1]:.1f} dBm, "
                            f"{best[2]:.4f} GHz ({best[3]})")
        return " | ".join(bits)
    return f"{plotted} curve(s) plotted."


def _best_point(tests, mode, freq=None):
    best = None
    for test in tests:
        if mode not in test.by_mode:
            continue
        for fund in _funds_for(test, freq, mode):
            pin, pout = test.pout(mode, fund)
            if len(pin) == 0:
                continue
            cl = pin - pout
            i = int(np.argmin(cl))
            if best is None or cl[i] < best[0]:
                best = (float(cl[i]), float(pin[i]), fund, test.label)
    return best


def _map(fig, tests, modes, cl):
    test = tests[0]
    funds = test.fundamentals
    if len(funds) < 2:
        raise PlotError("Maps need a frequency-sweep test (p_freq_in_sweep).")

    grids = {}
    for mode in modes:
        if mode not in test.by_mode:
            continue
        frame = test.by_mode[mode].sort_index().reindex(columns=funds)
        pin = frame.index.to_numpy(dtype=float)
        z = frame.to_numpy(dtype=float).T                       # rows = frequency, cols = Pin
        if cl:
            z = pin[None, :] - z
        grids[mode] = (pin, z)
    grids = {m: g for m, g in grids.items() if np.isfinite(g[1]).any()}
    if not grids:
        raise PlotError("The test has no data for the selected harmonics.")

    # Shared color scale so the harmonics can be compared directly (as in waterfall.py)
    vmin = np.nanmin([np.nanmin(z) for _, z in grids.values()])
    vmax = np.nanmax([np.nanmax(z) for _, z in grids.values()])
    cmap = "viridis_r" if cl else "viridis"
    label = "Conversion Loss (dB)" if cl else "Output Power (dBm)"

    axes = _axes_per_mode(fig, list(grids))
    status = []
    for ax, (mode, (pin, z)) in zip(axes, grids.items()):
        mesh = ax.pcolormesh(pin, funds, z, shading="nearest", cmap=cmap, vmin=vmin, vmax=vmax)
        fig.colorbar(mesh, ax=ax, label=label)
        ax.set_title(harmonic_title(mode))
        ax.set_xlabel("Input Power (dBm)")
        ax.set_ylabel("Fundamental frequency (GHz)")
        if cl and np.isfinite(z).any():
            r, c = np.unravel_index(np.nanargmin(z), z.shape)
            ax.plot(pin[c], funds[r], marker="*", markersize=14, color="red", markeredgecolor="white")
            status.append(f"{harmonic_name(mode)} min CL {z[r, c]:.2f} dB at {funds[r]:.4f} GHz, Pin {pin[c]:.1f} dBm")

    fig.suptitle(f"{test.label}: {label.split(' (')[0]}")
    note = " (only the first test is mapped)" if len(tests) > 1 else ""
    return (" | ".join(status) or "Map drawn.") + note


def _best_cl(fig, tests, modes):
    axes = _axes_per_mode(fig, modes)
    status = []
    for ax, mode in zip(axes, modes):
        overall = None
        for i, test in enumerate(tests):
            if mode not in test.by_mode:
                continue
            freqs, mins, pins = [], [], []
            for fund in test.by_mode[mode].columns:
                pin, pout = test.pout(mode, fund)
                if len(pin) == 0:
                    continue
                cl = pin - pout
                k = int(np.argmin(cl))
                freqs.append(fund)
                mins.append(cl[k])
                pins.append(pin[k])
            if not freqs:
                continue
            ax.plot(freqs, mins, marker="o", markersize=4, color=f"C{i % 10}", label=test.label)
            k = int(np.argmin(mins))
            if overall is None or mins[k] < overall[0]:
                overall = (mins[k], freqs[k], pins[k], test.label)
        ax.set_title(harmonic_title(mode))
        ax.set_xlabel("Fundamental frequency (GHz)")
        ax.set_ylabel("Minimum Conversion Loss (dB)")
        ax.grid(True, alpha=0.4)
        if 0 < len(tests) <= MAX_LEGEND_ENTRIES and ax.lines:
            ax.legend(fontsize=8)
        if overall:
            status.append(f"{harmonic_name(mode)} best {overall[0]:.2f} dB at {overall[1]:.4f} GHz, "
                          f"Pin {overall[2]:.1f} dBm ({overall[3]})")
    fig.suptitle("Best conversion loss over input power, per frequency")
    return " | ".join(status)


def _delta_cl(fig, tests, modes, freq):
    if len(tests) != 2:
        raise PlotError("ΔCL needs exactly two tests in the 'Tests to plot' list "
                        "(Test 1 = first, Test 2 = second).")
    t1, t2 = tests
    ax = fig.add_subplot(1, 1, 1)
    status = []
    for i, mode in enumerate(modes):
        if mode not in t1.by_mode or mode not in t2.by_mode:
            continue
        curves = []
        for t in (t1, t2):
            fund = t.nearest_fund(freq, mode)
            pin, pout = t.pout(mode, fund)
            if len(pin) < 2:
                break
            # Average duplicate Pin values, as relative_conversion_loss.py does
            s = pd.Series(pin - pout, index=pin).groupby(level=0).mean()
            curves.append((s.index.to_numpy(), s.to_numpy(), fund))
        if len(curves) < 2:
            continue
        lo = max(c[0].min() for c in curves)
        hi = min(c[0].max() for c in curves)
        if lo >= hi:
            continue
        grid = np.unique(np.concatenate([c[0][(c[0] >= lo) & (c[0] <= hi)] for c in curves]))
        cl1 = np.interp(grid, curves[0][0], curves[0][1])
        cl2 = np.interp(grid, curves[1][0], curves[1][1])
        delta = cl2 - cl1
        ax.plot(grid, delta, marker=".", markersize=3, color=f"C{i % 10}", label=harmonic_title(mode))
        k = int(np.argmin(delta))
        status.append(f"{harmonic_name(mode)}: mean ΔCL {np.mean(delta):+.2f} dB, "
                      f"best {delta[k]:+.2f} dB at Pin {grid[k]:.1f} dBm")

    if not ax.lines:
        raise PlotError("The two tests have no overlapping input-power range for the selected harmonics.")

    ax.axhline(0, color="black", linestyle="--", linewidth=1)
    ax.set_xlabel("Input Power (dBm)")
    ax.set_ylabel(r"$\Delta CL$ (dB)")
    ax.grid(True, alpha=0.4)
    ax.legend(fontsize=8)
    ax.set_title(f"Conversion Loss Difference: Test 2 − Test 1\n{t2.label}  −  {t1.label}", fontsize=10)
    return " | ".join(status) + "   (negative = Test 2 has lower CL)"