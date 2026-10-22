# Remote Signal Generator and Analyzer Automation

Python scripts for automating RF power sweeps on a Keysight signal generator and signal analyzer over VISA, and for plotting the results. The scripts were written to characterize Schottky-diode frequency doublers (MMDL301, SMS7621) and their matching networks: the generator drives the device under test (DUT) at a fundamental frequency *f0*, and the analyzer measures the output power at *f0* and its second harmonic *2f0* as the input power (and optionally the frequency) is swept.

Developed at the University of Vermont.

## Hardware

| Role | Instrument |
| --- | --- |
| Signal generator (SG) | Keysight N5183B EXG Vector Signal Generator |
| Signal analyzer (SA) | Keysight N9020A EXA Signal Analyzer |

Both instruments are connected to the PC over USB. The SG output feeds the DUT input, and the DUT output feeds the SA input.

```
┌────────────┐      ┌───────┐      ┌────────────┐
│  N5183B SG │ ───► │  DUT  │ ───► │  N9020A SA │
└─────┬──────┘      └───────┘      └─────┬──────┘
      │ USB                              │ USB
      └──────────────► PC ◄──────────────┘
```

## Requirements

- Windows, with the [Keysight IO Libraries Suite](https://www.keysight.com/find/iosuite) installed. The scripts load the VISA library from `C:\Windows\System32\visa32.dll`.
- Python 3 with:

```bash
pip install pyvisa numpy pandas matplotlib
```

## Setup

1. Connect both instruments over USB and open **Keysight Connection Expert** to find their VISA addresses.
2. Update the addresses at the top of each acquisition script if yours differ:

   ```python
   VISA_ADDRESS_SG = 'USB0::0x0957::0x1F01::MY59100943::0::INSTR'
   VISA_ADDRESS_SA = 'USB0::0x2A8D::0x0B0B::MY53400410::0::INSTR'
   ```
3. Run the connection tests in `Test Setup/` to confirm both instruments respond.
4. Run every script **from the repository root**. Data paths such as `Data/pin_sweep/...` are relative to the current working directory.

## Repository layout

```
├── Test Setup/          Connection checks and the measurement-uncertainty study
├── Sweep Tests/         Acquisition scripts that drive the instruments and write CSVs
├── Sweep Plotting/
│   ├── Single Test/     Plots for one CSV
│   └── Compare Tests/   Plots that overlay or difference several CSVs
├── Data/                Current measurement data (written by Sweep Tests)
├── Data_dev-oct_14_2026/  Archived measurements taken before Oct 14, 2026
└── Uncertainty/         Output of sweep_uncertainty.py, one folder per run
```

## Test Setup

| Script | What it does |
| --- | --- |
| `Test_SG.py` | Connects to the SG, prints its `*IDN?`, and steps the output from 1 to 5 GHz at 0 dBm. |
| `Test_SA.py` | Connects to the SA, prints its `*IDN?`, and reads the frequency and amplitude of the largest peak with Marker 1. |
| `TEST_SA_SG.py` | Runs both together: steps the SG from 1 to 5 GHz and reads the peak on the SA at each step. |
| `sweep_uncertainty.py` | Measures the precision-versus-speed trade-off of the analyzer settings (see below). |

### Measurement uncertainty study

`sweep_uncertainty.py` sweeps a grid of analyzer span and resolution bandwidth (RBW) settings, logarithmically spaced. For each pair it repeats an input-power sweep *N* times at *f0* and *2f0*, timing every point. Narrower RBW lowers the noise floor but lengthens each sweep, so the goal is to find the knee where more measurement time stops buying meaningful precision.

Each run writes a timestamped folder under `Uncertainty/` containing:

| File | Contents |
| --- | --- |
| `raw.csv` | Every individual measurement: span, RBW, harmonic, input power, measured peak, frequency error, and time per point |
| `configuration.csv` | Total and per-repeat elapsed time for each span/RBW pair |
| `uncertainty.csv` | Per-point mean, standard deviation, standard error, and 95% confidence interval (uses *t* = 4.303, the Student's *t* value for *N* = 3) |
| `pareto_precision_vs_time.png` | Output-power standard deviation vs. time per repeat |
| `mean_Pout_vs_Pin_mode_{1,2}.png` | Mean output power vs. input power, one curve per span/RBW pair |
| `std_Pout_vs_Pin_mode_{1,2}.png` | Standard deviation vs. input power, showing where repeatability degrades |

Raw data is flushed to disk every few points, and the RF output is turned off in a `finally` block, so an interrupted run keeps its data and leaves the generator safe.

## Sweep Tests

All acquisition scripts are configured by editing the variables at the top of the file:

```python
DUT   = "MMDL301_STUBMATCH"         # Folder name the CSV is saved under
f0    = 1.575                       # Fundamental frequency (GHz)
Pin   = np.linspace(-60, 20, 201)   # Input power sweep (dBm)
modes = [1, 2]                      # Harmonics to measure (1 = f0, 2 = 2f0)
SPAN  = 5e4                         # Analyzer span (Hz)
RBW   = 1e2                         # Analyzer resolution bandwidth (Hz)
```

For each harmonic, the SA is centered on *M · f0*, the SG steps through `Pin`, and the SA's Marker 1 peak is recorded as the output power.

| Script | Sweep | Output |
| --- | --- | --- |
| `input_power_v2.py` | Input power at a single frequency. Triggers one analyzer sweep per point and waits for completion (`*OPC?`). Estimates the run time and asks for confirmation before starting. | `Data/pin_sweep/<DUT>/<timestamp>.csv` |
| `input_power_frequency.py` | Input power **and** frequency: steps `f0` across a band of width `BW` centered on `f0`, and runs the power sweep at each step. Asks for confirmation before starting. | `Data/p_freq_in_sweep/<DUT>/<timestamp>.csv` |
| `SLOW_manual_delay_input_power.py` | The original single-frequency power sweep. Leaves the analyzer in continuous mode and waits a fixed 1.5 × sweep time before and after each reading. Slower; kept for reference. | `Data/pin_sweep/<DUT>/<timestamp>.csv` |

`input_power_v2.py` and `SLOW_manual_delay_input_power.py` save the CSV after every point, so a partial sweep is not lost. `input_power_frequency.py` writes its CSV once, at the end of the run.

### Data format

Every sweep CSV has a `Pin` column (input power, dBm) followed by one column per measured frequency, named by that frequency in GHz. Values are measured output power in dBm.

A single-frequency sweep (`pin_sweep`) has three columns:

```
Pin,1.575GHz,3.15GHz
-60.0,-103.988,-111.349
-59.9,-107.079,-109.809
```

A frequency sweep (`p_freq_in_sweep`) has an *f0*/*2f0* column pair for every frequency step:

```
Pin,1.515GHz,3.03GHz,1.5174GHz,3.0348GHz,1.5198GHz,3.0396GHz,...
```

DUT folders are named after the device and its matching network, for example `MMDL301_NOMATCH`, `MMDL301_STUBMATCH`, or `SAW_MMDL301_STUBMATCH`.

## Sweep Plotting

Conversion loss is calculated throughout as

```
CL (dB) = Pin (dBm) − Pout (dBm)
```

### Single Test

These scripts plot one CSV. Set the `file` / `csv_path` variable at the top of the script to the CSV you want.

| Script | Input | Plots |
| --- | --- | --- |
| `ouput_power.py` | `pin_sweep` | Output power vs. input power for every frequency column |
| `conversion_loss.py` | `pin_sweep` | Conversion loss vs. input power at *f0* and *2f0* |
| `BW_output_power.py` | `p_freq_in_sweep` | Output power vs. input power at every frequency, as 2D overlays and 3D line plots (input power × frequency × output power), for *f0* and *2f0* |
| `BW_conversion_loss.py` | `p_freq_in_sweep` | Vertically offset "waterfall" of conversion-loss curves, one per frequency, for *f0* and *2f0*. Prints the frequency and input power with the lowest conversion loss at each harmonic. |
| `waterfall.py` | `p_freq_in_sweep` | Color maps of output power and conversion loss across input power (x) and frequency (y), for *f0* and *2f0*, on shared color scales so the harmonics can be compared directly |

### Compare Tests

These scripts are interactive: they list the folders under `Data/` and prompt you to pick the tests to compare.

| Script | Plots |
| --- | --- |
| `output_power.py` | Overlays output power vs. input power at *f0* and *2f0* for any number of DUTs and tests |
| `conversion_loss.py` | Overlays conversion loss vs. input power at *f0* and *2f0* for any number of DUTs and tests |
| `relative_conversion_loss.py` | Difference in *2f0* conversion loss between exactly two tests, ΔCL = CL(Test 2) − CL(Test 1). Both tests are interpolated onto a common input-power grid over their overlapping range (no extrapolation). Negative ΔCL means Test 2 has lower conversion loss. |

The comparison plots expect `pin_sweep`-style CSVs, where column 1 is *f0* and column 2 is *2f0*.

## Typical workflow

```bash
# 1. Confirm the instruments are reachable
python "Test Setup/TEST_SA_SG.py"

# 2. (Optional) Choose span and RBW using the uncertainty study
python "Test Setup/sweep_uncertainty.py"

# 3. Edit DUT, f0, Pin, SPAN and RBW, then run a sweep
python "Sweep Tests/input_power_v2.py"

# 4. Plot the result, or compare it against earlier tests
python "Sweep Plotting/Single Test/conversion_loss.py"
python "Sweep Plotting/Compare Tests/conversion_loss.py"
```

## Author

Ian Cassidy
