import subprocess
import sys
import os
from pathlib import Path

from config import RUN_MODE


BASE_DIR = Path(__file__).resolve().parent
FILES_FOLDER = BASE_DIR / "files"


ALL_SCRIPTS = [
    "atc-losses.py",
    "cash-adjusted-gap.py",
    "consumer-rev-breakup.py",
    "consumer-revenue.py",
    "consumer-sales.py",
    "cost-str-energy.py",
    "cost-str.py",
    "debt.py",
    "equities.py",
    "expense.py",
    "gap-on-energy.py",
    "net-worth.py",
    "profit.py",
    "rev_energy_sold.py",
    "rev-details.py",
    "rev-str.py",
    "total-assets.py",
]


STANDARD_EXCLUDE = {
    "consumer-rev-breakup.py",
    "consumer-revenue.py",
    "consumer-sales.py",
}


if RUN_MODE.upper() == "STANDARD":
    scripts = [
        script for script in ALL_SCRIPTS
        if script not in STANDARD_EXCLUDE
    ]

elif RUN_MODE.upper() == "FULL":
    scripts = ALL_SCRIPTS

else:
    raise ValueError("RUN_MODE must be either 'STANDARD' or 'FULL'")


# Allow scripts inside /files to import config.py from the parent folder
env = os.environ.copy()
env["PYTHONPATH"] = str(BASE_DIR) + os.pathsep + env.get("PYTHONPATH", "")


for script in scripts:
    print(f"\nRunning: {script}")

    subprocess.run(
        [sys.executable, str(FILES_FOLDER / script)],
        env=env
    )


print(f"\nFinished running {len(scripts)} scripts.")