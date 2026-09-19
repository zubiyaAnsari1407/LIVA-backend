from pathlib import Path
import json

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]

RAW_DIR = BASE_DIR / "data" / "raw"
SOURCE_FILE = BASE_DIR / "data" / "sources.json"

DATASET_FILE = (
    RAW_DIR
    / "railway_land_acquisition_delay_2025.csv"
)


def load_source_metadata():
    with open(
        SOURCE_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def inspect_dataset():
    if not DATASET_FILE.exists():
        raise FileNotFoundError(
            f"Official dataset not found:\n"
            f"{DATASET_FILE}"
        )

    df = pd.read_csv(DATASET_FILE)

    metadata = load_source_metadata()

    print("\n==============================")
    print("LIVA GOVERNMENT DATA INSPECTOR")
    print("==============================")

    print("\nDataset:")
    print(DATASET_FILE.name)

    print("\nRows:")
    print(len(df))

    print("\nColumns:")
    for column in df.columns:
        print("-", column)

    print("\nData types:")
    print(df.dtypes)

    print("\nMissing values:")
    print(df.isna().sum())

    print("\nFirst 5 government records:")
    print(df.head())

    print("\nRegistered official sources:")
    for source in metadata["sources"]:
        print(
            "-",
            source["name"],
            "|",
            source["authority"],
        )


if __name__ == "__main__":
    inspect_dataset()