"""
Sami Calabretta
descrip"""



import tkinter as tk
from tkinter import simpledialog
#from call_sweep import sweep as sw

DUT = "MMDL301_STUBMATCH_1p578"

params = {
    "General":[
        "Device name",
        ], 
    "Sweep settings":[
        "Sweep range", "Sweep start", "Sweep steps", "Resolution BW", "Span",
        ],
    "Constants":[
        "Fundamental frequency", "Modes (comma separated)",
        ],
    "Device Addresses":[
        "Signal Generator", "Signal Analyzer",
        ],
}
param_vals = {
    "DUT": "none",
    "P_range": 1,
    "P_min": 1,
    "P_step": 1,
    "Modes":[],
    "RBW": 1,
    "SPAN": 1,
    "VISA_ADDRESS_SG": "none",
    "VISA_ADDRESS_SA": "none",
    }

#connects each displayed label to its existing parameter key
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
    for section, par in params.items():
        #create frame for each section, get value for each par per section, re-assign value in param vals, print param vals to verify
        frame = tk.LabelFrame(root, text=section, padx=10, pady=5) #labels frame for each section
        frame.grid(row=section_row, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        for i, parameter in enumerate(par):
            tk.Label(frame, text=f"{parameter}:").grid(row=i, column=0, sticky="w") #creates label and input field for each param
            entry = tk.Entry(frame)
            entry.grid(row=i, column=1, padx=5, pady=2)
    print(param_vals) #verify

    DUT = name_entry.get()
    freq = var.get()
    print(freq)

# Create the window
root = tk.Tk()
root.title("Parameters")
root.geometry("300x200")

# Name input
tk.Label(root, text="Device name:").grid(row=1,column=0)
tk.Label(root, text="Center frequency:").grid(row=2,column=0)

name_entry = tk.Entry(root)
var = tk.Entry(root)
name_entry.grid(row=1,column=1)
var.grid(row=2,column=1)


# Name button
tk.Button(root, text="Submit", command=ask_params).grid(row=3,column=0)

root.mainloop()

sw(param_vals)