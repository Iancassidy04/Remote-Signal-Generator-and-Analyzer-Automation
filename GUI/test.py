
import tkinter as tk

DUT = "MMDL301_STUBMATCH_1p578"

params = {
    "General": ["Device name"],
    "Sweep settings": [
        "Sweep range", "Sweep start", "Sweep steps",
        "Resolution BW", "Span",
    ],
    "Constants": [
        "Fundamental frequency", "Modes (comma separated)",
    ],
    "Device Addresses": [
        "Signal Generator", "Signal Analyzer",
    ],
}

param_vals = {
    "DUT": "none",
    "P_range": 1,
    "P_min": 1,
    "P_step": 1,
    "Modes": [],
    "RBW": 1,
    "SPAN": 1,
    "FREQ": 1,
    "VISA_ADDRESS_SG": "none",
    "VISA_ADDRESS_SA": "none",
}

#connect each displayed label to its existing parameter key
param_keys = {
    "Device name": "DUT",
    "Sweep range": "P_range",
    "Sweep start": "P_min",
    "Sweep steps": "P_step",
    "Resolution BW": "RBW",
    "Span": "SPAN",
    "Fundamental frequency": "FREQ",
    "Modes (comma separated)": "Modes",
    "Signal Generator": "VISA_ADDRESS_SG",
    "Signal Analyzer": "VISA_ADDRESS_SA",
}


def ask_params():
    for key in param_keys.values():
        value = param_vals[key].get().strip()

        if key == "Modes":
            param_vals[key] = [
                mode.strip()
                for mode in value.split(",")
                if mode.strip()
            ]
        else:
            param_vals[key] = value

    print(param_vals)


root = tk.Tk()
root.title("Parameters")
root.geometry("450x600")

for section_row, (section, parameters) in enumerate(params.items()):
    frame = tk.LabelFrame(root, text=section, padx=10, pady=5)
    frame.grid(row=section_row, column=0,sticky="ew", padx=10, pady=5)

    for i, parameter in enumerate(parameters):
        tk.Label(frame, text=f"{parameter}:").grid(row=i, column=0, sticky="w")

        entry = tk.Entry(frame, width=25)
        entry.grid(row=i, column=1, padx=5, pady=3)

        #stores the widget in param_vals
        param_vals[param_keys[parameter]] = entry

tk.Button(root,text="Submit",command=ask_params,).grid(row=len(params), column=0, pady=10)

root.mainloop()
