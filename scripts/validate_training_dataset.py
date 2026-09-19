from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "liva_master_training.csv"
)

# Project-level engineering safeguards.
MIN_ROWS = 100
MIN_CLASS_COUNT = 20


def validate_training_data():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Training dataset not found:\n{DATA_FILE}"
        )

    df = pd.read_csv(DATA_FILE)

    print("\n==============================")
    print("LIVA ML DATA QUALITY CHECK")
    print("==============================")

    print("\nTotal rows:")
    print(len(df))

    if "is_schedule_delayed" not in df.columns:
        raise ValueError(
            "Target column is_schedule_delayed missing."
        )

    counts = (
        df["is_schedule_delayed"]
        .value_counts()
        .sort_index()
    )

    print("\nClass distribution:")
    print(counts)

    problems = []

    if len(df) < MIN_ROWS:
        problems.append(
            f"Only {len(df)} rows available. "
            f"LIVA training guard expects at least {MIN_ROWS}."
        )

    if len(counts) < 2:
        problems.append(
            "Both delayed and non-delayed classes are required."
        )

    for label in [0, 1]:
        count = int(counts.get(label, 0))

        if count < MIN_CLASS_COUNT:
            problems.append(
                f"Class {label} contains only {count} rows. "
                f"Minimum guard value is {MIN_CLASS_COUNT}."
            )

    if problems:
        print("\nTRAINING STATUS: BLOCKED")

        for problem in problems:
            print("-", problem)

        print(
            "\nReason: Training on this dataset would "
            "produce an unreliable evaluation."
        )

        return False

    print("\nTRAINING STATUS: READY")
    return True


if __name__ == "__main__":
    validate_training_data()