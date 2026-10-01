import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

data_folder = Path("Data")

# Select test
test_folders = sorted([x for x in data_folder.iterdir() if x.is_dir()])

print("\nAvailable tests:")
for i, test in enumerate(test_folders, 1):
    print(f"{i}: {test.name}")

test_choice = int(input("\nSelect test: ")) - 1
test_folder = test_folders[test_choice]

# Select DUTs and tests
dut_folders = sorted([x for x in test_folder.iterdir() if x.is_dir()])

print(f"\nAvailable DUTs in {test_folder.name}:")
for i, dut in enumerate(dut_folders, 1):
    print(f"{i}: {dut.name}")

selected_files = []

DUTS = "y"

while DUTS == "y":

    # Select DUT
    dut_number = int(input("\nSelect DUT: "))
    selected_dut = dut_folders[dut_number - 1]

    print(f"\nSelected DUT: {selected_dut.name}")

    # Find CSV files for this DUT
    csv_files = sorted(selected_dut.glob("*.csv"))

    print("\nAvailable tests:")
    for i, file in enumerate(csv_files, 1):
        print(f"{i}: {file.stem}")

    # Add tests for this DUT

    ADD_CSV = "y"
    while ADD_CSV == "y":

        csv_number = int(input("\nWhich test would you like to add? "))
        selected_files.append(csv_files[csv_number - 1])
        ADD_CSV = input("\nWould you like to add another test for this DUT? (y/n) ")

    # Add another DUT
    DUTS = input("\nWould you like to add another DUT to compare? (y/n) ")


# Plotting
plt.figure()

DUT_names = ""
for csv_path in selected_files:

    df = pd.read_csv(csv_path)
    DUT = csv_path.parent.name
    date = csv_path.stem

    DUT_names += f"{DUT}, "

    Pin = df["Pin"]

    f0 = df.iloc[:, 1]
    f02 = df.iloc[:, 2]

    # Plot
    plt.plot(Pin, f0, marker=".", label=f"{DUT} - {date} - Fundamental")

    plt.plot(Pin, f02, marker=".", label=f"{DUT} - {date} - 2nd Harmonic")

DUT_names = DUT_names.rstrip(", ")

plt.xlabel("Input Power (dBm)")
plt.ylabel("Output Power (dBm)")
plt.title(f"{DUT_names}: Input vs Output Power Comparison")

plt.grid(True)
plt.legend()
plt.show()