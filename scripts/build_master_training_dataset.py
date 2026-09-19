from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]

PROCESSED_DIR = (
    BASE_DIR
    / "data"
    / "processed"
)

OUTPUT_FILE = (
    PROCESSED_DIR
    / "liva_master_training.csv"
)


# Only files with compatible schedule-delay labels
TRAINING_FILES = [
    PROCESSED_DIR
    / "mospi_march_2026_training_ready.csv",
]


REQUIRED_COLUMNS = [
    "project_name",
    "original_cost_cr",
    "expenditure_cr",
    "schedule_delay_days",
    "expenditure_ratio",
    "is_schedule_delayed",
]


OPTIONAL_COLUMNS = [
    "sector",
    "line_ministry",
    "revised_cost_cr",
    "cost_overrun_pct",
    "original_completion_year",
    "revised_completion_year",
    "source_authority",
    "source_department",
    "source_platform",
    "source_reference_period",
    "is_government_data",
    "is_demo",
]


def load_training_file(
    path: Path,
) -> pd.DataFrame:

    if not path.exists():
        print(
            f"Skipping missing source: "
            f"{path.name}"
        )

        return pd.DataFrame()

    df = pd.read_csv(path)

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"{path.name} is missing "
            f"required columns: {missing}"
        )

    print(
        f"Loaded {len(df)} records "
        f"from {path.name}"
    )

    return df


def standardise(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # ------------------------------------------------
    # Numeric features
    # ------------------------------------------------

    numeric_columns = [
        "original_cost_cr",
        "revised_cost_cr",
        "expenditure_cr",
        "schedule_delay_days",
        "cost_overrun_pct",
        "expenditure_ratio",
        "original_completion_year",
        "revised_completion_year",
        "is_schedule_delayed",
    ]

    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce",
            )

    # ------------------------------------------------
    # Target must be 0 or 1
    # ------------------------------------------------

    df = df[
        df["is_schedule_delayed"].isin(
            [0, 1]
        )
    ].copy()

    df["is_schedule_delayed"] = (
        df["is_schedule_delayed"]
        .astype(int)
    )

    # ------------------------------------------------
    # Core rows must have usable values
    # ------------------------------------------------

    df = df.dropna(
        subset=[
            "project_name",
            "original_cost_cr",
            "expenditure_cr",
            "schedule_delay_days",
            "expenditure_ratio",
            "is_schedule_delayed",
        ]
    )

    # ------------------------------------------------
    # Government-only training
    # ------------------------------------------------

    if "is_government_data" in df.columns:
        df = df[
            df["is_government_data"]
            .astype(str)
            .str.lower()
            .isin(
                [
                    "true",
                    "1",
                ]
            )
        ]

    # Never train using demo rows.
    if "is_demo" in df.columns:
        df = df[
            ~df["is_demo"]
            .astype(str)
            .str.lower()
            .isin(
                [
                    "true",
                    "1",
                ]
            )
        ]

    return df


def remove_duplicates(
    df: pd.DataFrame,
) -> pd.DataFrame:

    before = len(df)

    subset = [
        column
        for column in [
            "project_code",
            "project_name",
            "source_reference_period",
        ]
        if column in df.columns
    ]

    if not subset:
        subset = [
            "project_name"
        ]

    df = df.drop_duplicates(
        subset=subset,
        keep="first",
    )

    removed = before - len(df)

    print(
        "\nDuplicate records removed:",
        removed,
    )

    return df


def quality_report(
    df: pd.DataFrame,
) -> None:

    print("\n================================")
    print("LIVA MASTER TRAINING DATASET")
    print("================================")

    print(
        "\nTotal government records:",
        len(df),
    )

    print(
        "\nClass distribution:"
    )

    print(
        df[
            "is_schedule_delayed"
        ]
        .value_counts()
        .sort_index()
    )

    print(
        "\nGovernment sources:"
    )

    if "source_authority" in df.columns:

        print(
            df[
                "source_authority"
            ]
            .value_counts()
        )

    print(
        "\nSchedule delay summary:"
    )

    print(
        df[
            "schedule_delay_days"
        ].describe()
    )

    if "cost_overrun_pct" in df.columns:

        print(
            "\nCost overrun summary:"
        )

        print(
            df[
                "cost_overrun_pct"
            ].describe()
        )

    print(
        "\nMaster dataset saved:"
    )

    print(
        OUTPUT_FILE
    )


def main():

    datasets = []

    for path in TRAINING_FILES:

        df = load_training_file(
            path
        )

        if not df.empty:

            df = standardise(
                df
            )

            datasets.append(
                df
            )

    if not datasets:
        raise RuntimeError(
            "No compatible government "
            "training datasets were found."
        )

    master = pd.concat(
        datasets,
        ignore_index=True,
        sort=False,
    )

    master = remove_duplicates(
        master
    )

    master = master.reset_index(
        drop=True
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    master.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    quality_report(
        master
    )


if __name__ == "__main__":
    main()