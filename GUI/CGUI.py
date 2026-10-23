# Author: Ian Cassidy
# Sweep control and plotting GUI

'''
Signal Generator (SG): KEYSIGHT N5183B EXG Vector Signal Generator

Signal Analyzer (SA): KEYSIGHT N9020A EXA Signal Analyzer

Left side  - Run Sweep: device name, instrument addresses, sweep and analyzer
             settings for the conversion-loss tests.
Right side - Plot Data: pick old (or just-finished) measurements from drop downs
             and plot conversion loss, output power, maps, best CL and delta CL.

Device names, instrument addresses and the last settings used are remembered in
GUI/gui_history.json and offered in the drop downs next time.

Run from anywhere:   python GUI/sweep_gui.py
'''

import json
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText
from pathlib import Path

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

import instruments
from instruments import SweepConfig, SweepRunner, SweepAborted, PIN_SWEEP, FREQ_SWEEP, fmt_duration
import plotting

GUI_DIR = Path(__file__).resolve().parent
REPO_ROOT = GUI_DIR.parent
HISTORY_FILE = GUI_DIR / "gui_history.json"
DATA_ROOT = REPO_ROOT / "Data"
DRY_RUN_ROOT = REPO_ROOT / "Data_dry_run"

SWEEP_TYPE_LABELS = {
    PIN_SWEEP: "Input power (single frequency)",
    FREQ_SWEEP: "Input power + frequency",
}

# Lab defaults (from README / Sweep Tests)
DEFAULT_SG = "USB0::0x0957::0x1F01::MY59100943::0::INSTR"
DEFAULT_SA = "USB0::0x2A8D::0x0B0B::MY53400410::0::INSTR"

DEFAULTS = {
    "dut": "",
    "sweep_type": PIN_SWEEP,
    "pin_start": "-60",
    "pin_stop": "20",
    "pin_points": "201",
    "f0": "1.575",
    "modes": "1, 2",
    "bw": "0.12",
    "f_points": "51",
    "rbw": "100",
    "span": "50k",
    "sg_address": DEFAULT_SG,
    "sa_address": DEFAULT_SA,
}

RBW_CHOICES = ["10", "30", "100", "300", "1k", "3k", "10k", "30k", "100k"]
SPAN_CHOICES = ["10k", "20k", "50k", "100k", "200k", "500k", "1M"]

INVALID_NAME_CHARS = set('<>:"/\\|?*')
MAX_LOG_LINES = 3000
LIVE_PLOT_INTERVAL = 0.5  # s


# ---------------------------------------------------------------------------
# History (remembered device names, instrument addresses, last settings)
# ---------------------------------------------------------------------------

class History:
    MAX_ITEMS = 25

    def __init__(self, path):
        self.path = path
        self.data = {"devices": [], "sg_addresses": [], "sa_addresses": [],
                     "instrument_ids": {}, "last": {}}
        try:
            self.data.update(json.loads(path.read_text()))
        except (OSError, ValueError):
            pass
        # Seed with the lab instruments so the drop downs are useful on first run
        for key, address in (("sg_addresses", DEFAULT_SG), ("sa_addresses", DEFAULT_SA)):
            if not self.data[key]:
                self.data[key].append(address)

    def remember(self, key, value):
        value = value.strip()
        if not value:
            return
        items = [v for v in self.data[key] if v != value]
        self.data[key] = [value] + items[: self.MAX_ITEMS - 1]

    def forget(self, key, value):
        self.data[key] = [v for v in self.data[key] if v != value]

    def save(self):
        try:
            self.path.write_text(json.dumps(self.data, indent=2))
        except OSError as e:
            print(f"Could not save history: {e}")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

SI_SUFFIX = {"k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "m": 1e-3}


def parse_number(text, name):
    """Accepts plain numbers, scientific notation and k/M/G suffixes (with or without 'Hz')."""
    t = text.strip().replace(" ", "")
    if t.lower().endswith("hz"):
        t = t[:-2]
    mult = 1.0
    if t and t[-1] in SI_SUFFIX:
        mult = SI_SUFFIX[t[-1]]
        t = t[:-1]
    try:
        return float(t) * mult
    except ValueError:
        raise ValueError(f"{name}: '{text}' is not a number.")


def parse_int(text, name, minimum=1):
    try:
        value = int(float(text.strip()))
    except ValueError:
        raise ValueError(f"{name}: '{text}' is not a whole number.")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}.")
    return value


def parse_modes(text):
    try:
        modes = [int(m) for m in text.replace(";", ",").split(",") if m.strip()]
    except ValueError:
        raise ValueError(f"Harmonics: '{text}' should look like 1, 2")
    if not modes or min(modes) < 1:
        raise ValueError("Harmonics: enter one or more whole numbers ≥ 1, e.g. 1, 2")
    return list(dict.fromkeys(modes))


def section(parent, title, **pack):
    frame = tk.LabelFrame(parent, text=title, padx=10, pady=5)
    frame.pack(fill="x", padx=10, pady=5, **pack)
    frame.columnconfigure(1, weight=1)
    return frame


def row_label(frame, row, text):
    tk.Label(frame, text=text).grid(row=row, column=0, sticky="w", pady=2)


def data_folders():
    """Folders in the repo that hold sweep data (Data, Data_dev-..., Data_dry_run)."""
    found = []
    for d in sorted(REPO_ROOT.iterdir()):
        if d.is_dir() and any((d / kind).is_dir() for kind in (PIN_SWEEP, FREQ_SWEEP)):
            found.append(d)
    return found


def display_path(path):
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

class App:

    def __init__(self, root):
        self.root = root
        root.title("RF Sweep Control")
        root.geometry("1500x920")
        root.minsize(1100, 700)

        self.history = History(HISTORY_FILE)
        self.msg_q = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.live_cfg = None
        self.live_df = None
        self.live_last_draw = 0.0
        self.test_cache = {}
        self.mode_vars = {}
        self.plot_list = []           # paths in the "Tests to plot" list
        self.plot_roots = {}          # display name -> Path
        self.test_files = {}          # test combobox label -> Path

        self.vars = {key: tk.StringVar(value=value) for key, value in DEFAULTS.items()}
        self.dry_run = tk.BooleanVar(value=False)

        paned = ttk.PanedWindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=0)
        paned.add(right, weight=1)

        self.build_sweep_panel(left)
        self.build_plot_panel(right)

        self.restore_last()
        self.refresh_device_choices()
        self.refresh_address_choices()
        self.refresh_plot_roots()
        self.update_sweep_fields()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.after(100, self.poll_queue)

    # ------------------------------------------------------------------ sweep panel

    def build_sweep_panel(self, parent):
        tk.Label(parent, text="Run Sweep", font=("TkDefaultFont", 13, "bold")).pack(anchor="w", padx=12, pady=(8, 0))

        # General ---------------------------------------------------------
        f = section(parent, "General")
        row_label(f, 0, "Device name:")
        self.dut_cb = ttk.Combobox(f, textvariable=self.vars["dut"], width=34)
        self.dut_cb.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        ttk.Button(f, text="Forget", width=7,
                   command=lambda: self.forget("devices", self.vars["dut"])).grid(row=0, column=2)
        self.save_to_label = tk.Label(f, fg="gray40", anchor="w", justify="left")
        self.save_to_label.grid(row=1, column=0, columnspan=3, sticky="w")

        # Device Addresses ------------------------------------------------
        f = section(parent, "Device Addresses")
        self.addr_cb = {}
        self.idn_labels = {}
        for i, (role, code, key, hist) in enumerate((("Signal Generator", "SG", "sg_address", "sg_addresses"),
                                                      ("Signal Analyzer", "SA", "sa_address", "sa_addresses"))):
            row_label(f, 2 * i, f"{role}:")
            cb = ttk.Combobox(f, textvariable=self.vars[key], width=34)
            cb.grid(row=2 * i, column=1, sticky="ew", padx=5, pady=2)
            ttk.Button(f, text="Test", width=5,
                       command=lambda r=code, k=key: self.test_instrument(r, self.vars[k].get())
                       ).grid(row=2 * i, column=2)
            ttk.Button(f, text="Forget", width=7,
                       command=lambda h=hist, k=key: self.forget(h, self.vars[k])).grid(row=2 * i, column=3)
            lbl = tk.Label(f, fg="gray40", anchor="w")
            lbl.grid(row=2 * i + 1, column=1, columnspan=3, sticky="w", padx=5)
            self.addr_cb[key] = cb
            self.idn_labels[key] = lbl
            self.vars[key].trace_add("write", lambda *_, k=key: self.update_idn_label(k))
        ttk.Button(f, text="Scan for VISA instruments", command=self.scan_instruments).grid(
            row=4, column=1, sticky="w", padx=5, pady=(4, 0))

        # Sweep type ------------------------------------------------------
        f = section(parent, "Sweep Type")
        for i, (value, text) in enumerate(SWEEP_TYPE_LABELS.items()):
            ttk.Radiobutton(f, text=text, value=value, variable=self.vars["sweep_type"],
                            command=self.update_sweep_fields).grid(row=0, column=i, sticky="w", padx=(0, 15))

        # Sweep settings --------------------------------------------------
        f = section(parent, "Sweep Settings (Conversion Loss)")
        self.freq_widgets = []
        fields = [
            ("Input power start (dBm):", "pin_start", False),
            ("Input power stop (dBm):", "pin_stop", False),
            ("Input power points:", "pin_points", False),
            ("Fundamental frequency f0 (GHz):", "f0", False),
            ("Harmonics (comma separated):", "modes", False),
            ("Frequency sweep width (GHz):", "bw", True),
            ("Frequency points:", "f_points", True),
        ]
        for i, (text, key, is_freq) in enumerate(fields):
            lbl = tk.Label(f, text=text)
            lbl.grid(row=i, column=0, sticky="w", pady=2)
            entry = tk.Entry(f, textvariable=self.vars[key], width=14)
            entry.grid(row=i, column=1, sticky="w", padx=5, pady=2)
            if is_freq:
                self.freq_widgets += [lbl, entry]
        self.sweep_summary = tk.Label(f, fg="gray25", anchor="w", justify="left")
        self.sweep_summary.grid(row=len(fields), column=0, columnspan=2, sticky="w", pady=(4, 0))

        # Analyzer settings -----------------------------------------------
        f = section(parent, "Analyzer Settings")
        row_label(f, 0, "Resolution BW (Hz):")
        ttk.Combobox(f, textvariable=self.vars["rbw"], values=RBW_CHOICES, width=12).grid(
            row=0, column=1, sticky="w", padx=5, pady=2)
        row_label(f, 1, "Span (Hz):")
        ttk.Combobox(f, textvariable=self.vars["span"], values=SPAN_CHOICES, width=12).grid(
            row=1, column=1, sticky="w", padx=5, pady=2)
        tk.Label(f, text="k / M / G suffixes accepted (e.g. 50k)", fg="gray40").grid(
            row=2, column=0, columnspan=2, sticky="w")

        for key in ("dut", "sweep_type", "pin_start", "pin_stop", "pin_points", "f0", "modes",
                    "bw", "f_points", "rbw", "span"):
            self.vars[key].trace_add("write", lambda *_: self.update_summary())

        # Run -------------------------------------------------------------
        f = section(parent, "Run", expand=True)
        f.pack_configure(fill="both")
        buttons = tk.Frame(f)
        buttons.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.run_btn = ttk.Button(buttons, text="Run Sweep", command=self.start_sweep)
        self.run_btn.pack(side="left")
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop_sweep, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        ttk.Checkbutton(buttons, text="Dry run (simulated instruments)", variable=self.dry_run,
                        command=self.update_summary).pack(side="left", padx=10)
        self.progress = ttk.Progressbar(f, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 2))
        self.progress_label = tk.Label(f, text="Idle", anchor="w")
        self.progress_label.grid(row=2, column=0, columnspan=2, sticky="w")
        self.log_box = ScrolledText(f, height=8, width=60, font=("TkFixedFont", 9), state="disabled")
        self.log_box.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(4, 0))
        f.rowconfigure(3, weight=1)

    # ------------------------------------------------------------------ plot panel

    def build_plot_panel(self, parent):
        tk.Label(parent, text="Plot Data", font=("TkDefaultFont", 13, "bold")).pack(anchor="w", padx=12, pady=(8, 0))
        top = tk.Frame(parent)
        top.pack(fill="x", padx=5)
        top.columnconfigure(1, weight=1)

        # Measurement picker ---------------------------------------------
        f = tk.LabelFrame(top, text="Measurement", padx=10, pady=5)
        f.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.p_root = tk.StringVar()
        self.p_kind = tk.StringVar()
        self.p_dut = tk.StringVar()
        self.p_test = tk.StringVar()

        row_label(f, 0, "Data folder:")
        self.p_root_cb = ttk.Combobox(f, textvariable=self.p_root, state="readonly", width=28)
        self.p_root_cb.grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        ttk.Button(f, text="Browse…", width=8, command=self.browse_data_folder).grid(row=0, column=2)

        row_label(f, 1, "Sweep type:")
        self.p_kind_cb = ttk.Combobox(f, textvariable=self.p_kind, state="readonly", width=28)
        self.p_kind_cb.grid(row=1, column=1, sticky="ew", padx=5, pady=2)

        row_label(f, 2, "Device:")
        self.p_dut_cb = ttk.Combobox(f, textvariable=self.p_dut, state="readonly", width=28)
        self.p_dut_cb.grid(row=2, column=1, sticky="ew", padx=5, pady=2)

        row_label(f, 3, "Test:")
        self.p_test_cb = ttk.Combobox(f, textvariable=self.p_test, state="readonly", width=28)
        self.p_test_cb.grid(row=3, column=1, sticky="ew", padx=5, pady=2)

        btns = tk.Frame(f)
        btns.grid(row=4, column=1, columnspan=2, sticky="w", padx=5, pady=(4, 0))
        ttk.Button(btns, text="Add to plot list →", command=self.add_to_plot_list).pack(side="left")
        ttk.Button(btns, text="Refresh", command=self.refresh_plot_roots).pack(side="left", padx=5)

        self.p_root_cb.bind("<<ComboboxSelected>>", lambda e: self.on_plot_root())
        self.p_kind_cb.bind("<<ComboboxSelected>>", lambda e: self.on_plot_kind())
        self.p_dut_cb.bind("<<ComboboxSelected>>", lambda e: self.on_plot_dut())
        self.p_test_cb.bind("<<ComboboxSelected>>", lambda e: self.refresh_plot_options())

        # Tests to plot ---------------------------------------------------
        f = tk.LabelFrame(top, text="Tests to plot (compare)", padx=10, pady=5)
        f.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        f.columnconfigure(0, weight=1)
        f.rowconfigure(0, weight=1)
        self.plot_listbox = tk.Listbox(f, height=6, width=48, selectmode="extended", exportselection=False)
        self.plot_listbox.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(f, orient="vertical", command=self.plot_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.plot_listbox.configure(yscrollcommand=sb.set)
        btns = tk.Frame(f)
        btns.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Button(btns, text="Remove", command=self.remove_from_plot_list).pack(side="left")
        ttk.Button(btns, text="Clear", command=self.clear_plot_list).pack(side="left", padx=5)
        tk.Label(btns, text="Empty list → plots the test picked on the left", fg="gray40").pack(side="left", padx=5)

        # Plot options ----------------------------------------------------
        f = tk.LabelFrame(top, text="Plot Options", padx=10, pady=5)
        f.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        self.p_type = tk.StringVar(value=plotting.PLOT_CL)
        self.p_freq = tk.StringVar(value="All")

        row_label(f, 0, "Plot type:")
        ttk.Combobox(f, textvariable=self.p_type, values=plotting.PLOT_TYPES, state="readonly",
                     width=34).grid(row=0, column=1, sticky="ew", padx=5, pady=2)
        row_label(f, 1, "Harmonics:")
        self.mode_frame = tk.Frame(f)
        self.mode_frame.grid(row=1, column=1, sticky="w", padx=5, pady=2)
        row_label(f, 2, "Frequency:")
        self.p_freq_cb = ttk.Combobox(f, textvariable=self.p_freq, state="readonly", width=16)
        self.p_freq_cb.grid(row=2, column=1, sticky="w", padx=5, pady=2)
        btns = tk.Frame(f)
        btns.grid(row=3, column=1, sticky="w", padx=5, pady=(4, 0))
        ttk.Button(btns, text="Plot", command=self.plot).pack(side="left")
        ttk.Button(btns, text="Save figure…", command=self.save_figure).pack(side="left", padx=5)

        # Figure ----------------------------------------------------------
        self.plot_status = tk.Label(parent, text="", anchor="w", justify="left", fg="gray20", wraplength=1000)
        self.plot_status.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
        fig_frame = tk.Frame(parent)
        fig_frame.pack(fill="both", expand=True, padx=10, pady=(0, 5))
        self.fig = Figure(figsize=(9, 5.5), dpi=100, constrained_layout=True)
        self.canvas = FigureCanvasTkAgg(self.fig, master=fig_frame)
        toolbar = NavigationToolbar2Tk(self.canvas, fig_frame, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.show_placeholder()

    def show_placeholder(self):
        self.fig.clear()
        ax = self.fig.add_subplot(1, 1, 1)
        ax.text(0.5, 0.5, "Pick a measurement and press Plot,\nor run a sweep to watch it live.",
                ha="center", va="center", fontsize=12, color="gray")
        ax.set_axis_off()
        self.canvas.draw_idle()

    # ------------------------------------------------------------------ settings / history

    def restore_last(self):
        for key, value in self.history.data.get("last", {}).items():
            if key in self.vars and value is not None:
                self.vars[key].set(value)
        self.dry_run.set(bool(self.history.data.get("last", {}).get("dry_run", False)))

    def save_last(self):
        self.history.data["last"] = {key: var.get() for key, var in self.vars.items()}
        self.history.data["last"]["dry_run"] = self.dry_run.get()
        self.history.save()

    def refresh_device_choices(self):
        names = list(self.history.data["devices"])
        for kind in (PIN_SWEEP, FREQ_SWEEP):
            folder = DATA_ROOT / kind
            if folder.is_dir():
                for d in sorted(folder.iterdir()):
                    if d.is_dir() and d.name not in names:
                        names.append(d.name)
        self.dut_cb["values"] = names

    def refresh_address_choices(self, scanned=()):
        for key, hist in (("sg_address", "sg_addresses"), ("sa_address", "sa_addresses")):
            values = list(self.history.data[hist])
            values += [a for a in scanned if a not in values]
            self.addr_cb[key]["values"] = values
            self.update_idn_label(key)

    def update_idn_label(self, key):
        address = self.vars[key].get().strip()
        idn = self.history.data["instrument_ids"].get(address)
        if not address:
            text = ""
        elif idn:
            parts = [p.strip() for p in idn.split(",")]
            text = " ".join(parts[:2]) + (f"  (S/N {parts[2]})" if len(parts) > 2 else "")
        else:
            text = "Not identified yet — press Test"
        self.idn_labels[key].configure(text=text)

    def forget(self, history_key, var):
        value = var.get().strip()
        if value and value in self.history.data[history_key]:
            self.history.forget(history_key, value)
            self.history.save()
            self.log(f"Removed '{value}' from the saved list.")
        self.refresh_device_choices()
        self.refresh_address_choices()

    # ------------------------------------------------------------------ instrument helpers

    def test_instrument(self, role, address):
        address = address.strip()
        if not address:
            messagebox.showwarning("No address", f"Enter the {role} VISA address first.")
            return
        self.log(f"Querying *IDN? at {address} …")

        def work():
            try:
                self.msg_q.put(("idn", role, address, instruments.identify(address)))
            except Exception as e:
                self.msg_q.put(("idn_error", role, address, str(e)))

        threading.Thread(target=work, daemon=True).start()

    def scan_instruments(self):
        self.log("Scanning for VISA instruments …")

        def work():
            try:
                self.msg_q.put(("scan", instruments.list_resources()))
            except Exception as e:
                self.msg_q.put(("log", f"VISA scan failed: {e}"))

        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ sweep

    def update_sweep_fields(self):
        state = "normal" if self.vars["sweep_type"].get() == FREQ_SWEEP else "disabled"
        for w in self.freq_widgets:
            w.configure(state=state)
        self.update_summary()

    def update_summary(self):
        dut = self.vars["dut"].get().strip() or "<device name>"
        root = DRY_RUN_ROOT if self.dry_run.get() else DATA_ROOT
        self.save_to_label.configure(
            text=f"Saves to {display_path(root)}/{self.vars['sweep_type'].get()}/{dut}/<timestamp>.csv")
        try:
            cfg = self.read_config(validate_addresses=False)
        except ValueError as e:
            self.sweep_summary.configure(text=str(e), fg="firebrick")
            return
        step = (cfg.pin_stop - cfg.pin_start) / (cfg.pin_points - 1) if cfg.pin_points > 1 else 0
        text = f"Pin step {step:.3g} dB · "
        if cfg.sweep_type == FREQ_SWEEP:
            fin = cfg.fin
            fstep = (fin[-1] - fin[0]) / (len(fin) - 1) * 1e3 if len(fin) > 1 else 0
            text += f"{fin[0]:.4f}–{fin[-1]:.4f} GHz, step {fstep:.3g} MHz\n"
        text += (f"{cfg.pin_points} powers × {len(cfg.fin)} freq × {len(cfg.modes)} harmonics "
                 f"= {cfg.n_measurements} measurements")
        self.sweep_summary.configure(text=text, fg="gray25")

    def read_config(self, validate_addresses=True):
        v = {k: var.get() for k, var in self.vars.items()}
        dut = v["dut"].strip()
        if validate_addresses:
            if not dut:
                raise ValueError("Enter a device name.")
            bad = INVALID_NAME_CHARS.intersection(dut)
            if bad:
                raise ValueError(f"Device name can't contain: {' '.join(sorted(bad))}")
        cfg = SweepConfig(
            dut=dut,
            sweep_type=v["sweep_type"],
            pin_start=parse_number(v["pin_start"], "Input power start"),
            pin_stop=parse_number(v["pin_stop"], "Input power stop"),
            pin_points=parse_int(v["pin_points"], "Input power points"),
            f0=parse_number(v["f0"], "Fundamental frequency"),
            modes=parse_modes(v["modes"]),
            span=parse_number(v["span"], "Span"),
            rbw=parse_number(v["rbw"], "Resolution BW"),
            sg_address=v["sg_address"].strip(),
            sa_address=v["sa_address"].strip(),
            data_root=DRY_RUN_ROOT if self.dry_run.get() else DATA_ROOT,
            dry_run=self.dry_run.get(),
        )
        if cfg.f0 <= 0:
            raise ValueError("Fundamental frequency must be > 0 GHz.")
        if cfg.span <= 0 or cfg.rbw <= 0:
            raise ValueError("Span and RBW must be > 0.")
        if cfg.rbw > cfg.span:
            raise ValueError("RBW should be smaller than the span.")
        if cfg.pin_points > 1 and cfg.pin_start == cfg.pin_stop:
            raise ValueError("Input power start and stop are equal.")
        if cfg.sweep_type == FREQ_SWEEP:
            cfg.bw = parse_number(v["bw"], "Frequency sweep width")
            cfg.f_points = parse_int(v["f_points"], "Frequency points")
            if cfg.bw < 0 or cfg.bw >= cfg.f0:
                raise ValueError("Frequency sweep width must be between 0 and f0.")
        if validate_addresses and not cfg.dry_run and not (cfg.sg_address and cfg.sa_address):
            raise ValueError("Enter both instrument addresses (or tick Dry run).")
        return cfg

    def start_sweep(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            cfg = self.read_config()
        except ValueError as e:
            messagebox.showerror("Check settings", str(e))
            return

        self.history.remember("devices", cfg.dut)
        if not cfg.dry_run:
            self.history.remember("sg_addresses", cfg.sg_address)
            self.history.remember("sa_addresses", cfg.sa_address)
        self.save_last()
        self.refresh_device_choices()
        self.refresh_address_choices()

        self.stop_event.clear()
        self.live_cfg = cfg
        self.live_df = None
        self.live_last_draw = 0.0
        self.progress.configure(value=0, maximum=cfg.n_measurements)
        self.progress_label.configure(text="Connecting …")
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.log(("=" * 20) + f" {cfg.dut} " + ("(DRY RUN) " if cfg.dry_run else "") + "=" * 20)

        self.worker = threading.Thread(target=self.sweep_worker, args=(cfg,), daemon=True)
        self.worker.start()

    def sweep_worker(self, cfg):
        runner = SweepRunner(cfg, emit=self.msg_q.put, confirm=self.confirm_from_thread,
                             stop_event=self.stop_event)
        try:
            self.msg_q.put(("done", runner.run()))
        except SweepAborted as e:
            self.msg_q.put(("aborted", str(e), runner.csv_path))
        except Exception as e:
            self.msg_q.put(("error", f"{type(e).__name__}: {e}", runner.csv_path))

    def confirm_from_thread(self, text):
        """Ask a yes/no question on the Tk thread and wait for the answer."""
        answer = {}
        ready = threading.Event()

        def ask():
            answer["ok"] = messagebox.askyesno("Confirm sweep", text)
            ready.set()

        self.root.after(0, ask)
        while not ready.wait(0.2):
            if self.stop_event.is_set():
                return False
        return answer.get("ok", False)

    def stop_sweep(self):
        if self.worker and self.worker.is_alive():
            self.stop_event.set()
            self.stop_btn.configure(state="disabled")
            self.log("Stopping after the current point …")

    def sweep_finished(self, csv_path, message):
        self.live_df = None
        self.run_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.progress_label.configure(text=message)
        if message != "Sweep complete.":
            self.log(message)
        self.refresh_device_choices()
        if csv_path and Path(csv_path).exists():
            self.select_measurement(Path(csv_path))
            self.plot(paths=[Path(csv_path)])

    # ------------------------------------------------------------------ queue / log

    def poll_queue(self):
        try:
            while True:
                msg = self.msg_q.get_nowait()
                kind = msg[0]
                if kind == "log":
                    self.log(msg[1])
                elif kind == "progress":
                    _, done, total, elapsed = msg
                    self.progress.configure(value=done)
                    left = elapsed / done * (total - done) if done else 0
                    self.progress_label.configure(
                        text=f"{done}/{total} points · {fmt_duration(elapsed)} elapsed · ~{fmt_duration(left)} left")
                elif kind == "data":
                    self.live_df = msg[1]
                elif kind == "idn":
                    _, role, address, idn = msg
                    self.history.data["instrument_ids"][address] = idn
                    self.history.remember("sg_addresses" if role == "SG" else "sa_addresses", address)
                    self.history.save()
                    self.refresh_address_choices()
                    self.log(f"{role} at {address}: {idn}")
                elif kind == "idn_error":
                    _, role, address, err = msg
                    self.log(f"{role} at {address} did not respond: {err}")
                    messagebox.showerror("Instrument test failed", f"{address}\n\n{err}")
                elif kind == "scan":
                    found = msg[1]
                    self.log("Found: " + (", ".join(found) if found else "no instruments"))
                    self.refresh_address_choices(scanned=found)
                elif kind == "done":
                    self.sweep_finished(msg[1], "Sweep complete.")
                elif kind == "aborted":
                    self.sweep_finished(msg[2], msg[1])
                elif kind == "error":
                    self.sweep_finished(msg[2], "Sweep failed.")
                    messagebox.showerror("Sweep failed", msg[1])
        except queue.Empty:
            pass

        if self.live_df is not None and time.time() - self.live_last_draw > LIVE_PLOT_INTERVAL:
            self.draw_live()
        self.root.after(100, self.poll_queue)

    def draw_live(self):
        df, self.live_df = self.live_df, None
        self.live_last_draw = time.time()
        try:
            test = plotting.from_frame(df, label=f"{self.live_cfg.dut} (live)")
            plotting.draw(self.fig, plotting.PLOT_POUT, [test], test.modes,
                          title=f"{self.live_cfg.dut}: live output power")
            self.plot_status.configure(text="Live view — updates as points arrive.")
        except plotting.PlotError:
            return
        self.canvas.draw_idle()

    def log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:
            self.log_box.delete("1.0", f"{lines - MAX_LOG_LINES}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ plot pickers

    def refresh_plot_roots(self):
        current = self.p_root.get()
        self.plot_roots = {display_path(d): d for d in data_folders()}
        extra = getattr(self, "_browsed_roots", {})
        self.plot_roots.update(extra)
        names = list(self.plot_roots)
        self.p_root_cb["values"] = names
        if current in names:
            self.p_root.set(current)
        elif names:
            self.p_root.set("Data" if "Data" in names else names[0])
        self.on_plot_root(keep=True)

    def browse_data_folder(self):
        folder = filedialog.askdirectory(initialdir=REPO_ROOT, title="Pick a data folder")
        if not folder:
            return
        path = Path(folder)
        # Accept the data root itself, a sweep-type folder, or a device folder
        if path.parent.name in (PIN_SWEEP, FREQ_SWEEP):
            path = path.parent.parent
        elif path.name in (PIN_SWEEP, FREQ_SWEEP):
            path = path.parent
        if not hasattr(self, "_browsed_roots"):
            self._browsed_roots = {}
        name = display_path(path)
        self._browsed_roots[name] = path
        self.p_root.set(name)
        self.refresh_plot_roots()

    @staticmethod
    def _set_choices(cb, var, values, keep):
        cb["values"] = values
        if keep and var.get() in values:
            return
        var.set(values[0] if values else "")

    def on_plot_root(self, keep=False):
        root = self.plot_roots.get(self.p_root.get())
        kinds = []
        if root and root.is_dir():
            kinds = [d.name for d in sorted(root.iterdir())
                     if d.is_dir() and any(d.glob("*/*.csv"))]
        self._set_choices(self.p_kind_cb, self.p_kind, kinds, keep)
        self.on_plot_kind(keep)

    def on_plot_kind(self, keep=False):
        root = self.plot_roots.get(self.p_root.get())
        duts = []
        if root and self.p_kind.get():
            folder = root / self.p_kind.get()
            # newest measurement first
            dirs = [d for d in folder.iterdir() if d.is_dir() and any(d.glob("*.csv"))]
            dirs.sort(key=lambda d: max(f.stat().st_mtime for f in d.glob("*.csv")), reverse=True)
            duts = [d.name for d in dirs]
        self._set_choices(self.p_dut_cb, self.p_dut, duts, keep)
        self.on_plot_dut(keep)

    def on_plot_dut(self, keep=False):
        self.test_files = {}
        root = self.plot_roots.get(self.p_root.get())
        if root and self.p_kind.get() and self.p_dut.get():
            folder = root / self.p_kind.get() / self.p_dut.get()
            files = sorted(folder.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
            self.test_files = {f.stem: f for f in files}
        self._set_choices(self.p_test_cb, self.p_test, list(self.test_files), keep)
        self.refresh_plot_options()

    def current_test_path(self):
        return self.test_files.get(self.p_test.get())

    def select_measurement(self, path):
        """Point the drop downs at a specific CSV (used after a sweep finishes)."""
        root = path.parent.parent.parent
        name = display_path(root)
        if name not in self.plot_roots:
            if not hasattr(self, "_browsed_roots"):
                self._browsed_roots = {}
            self._browsed_roots[name] = root
        self.refresh_plot_roots()
        self.p_root.set(name)
        self.on_plot_root()
        self.p_kind.set(path.parent.parent.name)
        self.on_plot_kind(keep=True)
        self.p_dut.set(path.parent.name)
        self.on_plot_dut(keep=True)
        self.p_test.set(path.stem)
        self.refresh_plot_options()

    def add_to_plot_list(self):
        path = self.current_test_path()
        if path is None:
            return
        if path in self.plot_list:
            return
        self.plot_list.append(path)
        self.plot_listbox.insert("end", f"{path.parent.parent.name} / {path.parent.name} / {path.stem}")
        self.refresh_plot_options()

    def remove_from_plot_list(self):
        for i in reversed(self.plot_listbox.curselection()):
            self.plot_listbox.delete(i)
            del self.plot_list[i]
        self.refresh_plot_options()

    def clear_plot_list(self):
        self.plot_listbox.delete(0, "end")
        self.plot_list.clear()
        self.refresh_plot_options()

    def load(self, path):
        key = (path, path.stat().st_mtime)
        if key not in self.test_cache:
            self.test_cache[key] = plotting.load_test(path)
        return self.test_cache[key]

    def tests_for_plot(self, paths=None):
        if paths is None:
            paths = list(self.plot_list) or ([self.current_test_path()] if self.current_test_path() else [])
        tests = []
        for p in paths:
            try:
                tests.append(self.load(p))
            except Exception as e:
                self.plot_status.configure(text=f"Could not read {p.name}: {e}")
        return tests

    def refresh_plot_options(self, tests=None):
        if tests is None:
            tests = self.tests_for_plot()
        modes = sorted({m for t in tests for m in t.modes}) or [1, 2]
        previous = {m: v.get() for m, v in self.mode_vars.items()}
        for w in self.mode_frame.winfo_children():
            w.destroy()
        self.mode_vars = {}
        for m in modes:
            var = tk.BooleanVar(value=previous.get(m, True))
            ttk.Checkbutton(self.mode_frame, text=plotting.harmonic_name(m), variable=var).pack(side="left", padx=(0, 6))
            self.mode_vars[m] = var

        funds = sorted({f for t in tests for f in t.fundamentals})
        values = ["All"] + [f"{f:.4f} GHz" for f in funds]
        self.p_freq_cb["values"] = values
        if self.p_freq.get() not in values:
            self.p_freq.set("All")

    def plot(self, paths=None):
        tests = self.tests_for_plot(paths)
        if paths is not None:
            self.refresh_plot_options(tests)
        modes = [m for m, v in self.mode_vars.items() if v.get()]
        freq = None if self.p_freq.get() in ("", "All") else float(self.p_freq.get().split()[0])
        try:
            status = plotting.draw(self.fig, self.p_type.get(), tests, modes, freq)
            self.plot_status.configure(text=status, fg="gray20")
        except plotting.PlotError as e:
            self.show_placeholder()
            self.plot_status.configure(text=str(e), fg="firebrick")
            return
        self.canvas.draw_idle()

    def save_figure(self):
        path = self.current_test_path()
        default = f"{path.parent.name}_{path.stem}" if path else "plot"
        filename = filedialog.asksaveasfilename(
            initialdir=REPO_ROOT, initialfile=f"{default}.png", defaultextension=".png",
            filetypes=[("PNG", "*.png"), ("PDF", "*.pdf"), ("SVG", "*.svg")])
        if filename:
            self.fig.savefig(filename, dpi=200)
            self.plot_status.configure(text=f"Saved {filename}")

    # ------------------------------------------------------------------ close

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Sweep running", "A sweep is running. Stop it and quit?"):
                return
            self.stop_event.set()
            self.worker.join(timeout=15)   # lets the runner turn the RF output off
        self.save_last()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()