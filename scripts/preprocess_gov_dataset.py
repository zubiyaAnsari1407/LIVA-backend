from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]

RAW_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "railway_land_acquisition_delay_2025.csv"
)

PROCESSED_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "railway_land_acquisition_delay_2025_processed.csv"
)


SOURCE_NAME = (
    "Project-wise Details of Some Major Projects "
    "Delayed Due to Land Acquisition"
)

SOURCE_AUTHORITY = "Rajya Sabha"

SOURCE_PLATFORM = (
    "Open Government Data Platform India"
)

SOURCE_REFERENCE_DATE = "2025-03-28"

SOURCE_URL = (
    "https://tn.data.gov.in/resource/"
    "project-wise-details-some-major-projects-"
    "delayed-due-land-acquisition-across-indian"
)


REQUIRED_COLUMNS = [
    "serial_no",
    "project_name",
    "total_land_required_ha",
    "land_acquired_ha",
    "balance_land_to_be_acquired_ha",
]


def load_dataset() -> pd.DataFrame:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Raw government dataset not found: "
            f"{RAW_FILE}"
        )

    return pd.read_csv(RAW_FILE)


def validate_columns(
    df: pd.DataFrame,
) -> None:
    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            "Required government columns "
            f"missing: {missing}"
        )


def clean_dataset(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()

    # ---------------------------------------------
    # Project name cleanup
    # ---------------------------------------------

    df["project_name"] = (
        df["project_name"]
        .astype(str)
        .str.strip()
    )

    # ---------------------------------------------
    # Numeric conversion
    # ---------------------------------------------

    numeric_columns = [
        "total_land_required_ha",
        "land_acquired_ha",
        "balance_land_to_be_acquired_ha",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # Remove unusable rows only if essential
    # government numeric values are missing.
    df = df.dropna(
        subset=numeric_columns
    )

    # ---------------------------------------------
    # Logical validation
    # ---------------------------------------------

    df = df[
        df["total_land_required_ha"] > 0
    ].copy()

    invalid_acquired = (
        df["land_acquired_ha"]
        >
        df["total_land_required_ha"]
    )

    if invalid_acquired.any():
        raise ValueError(
            "Government dataset contains "
            "land_acquired > total_land_required."
        )

    # ---------------------------------------------
    # Derived LIVA features
    # ---------------------------------------------

    df["acquisition_completion_pct"] = (
        (
            df["land_acquired_ha"]
            /
            df["total_land_required_ha"]
        )
        * 100
    ).round(2)

    df["pending_land_pct"] = (
        (
            df[
                "balance_land_to_be_acquired_ha"
            ]
            /
            df["total_land_required_ha"]
        )
        * 100
    ).round(2)

    # This dataset itself consists of projects
    # officially identified as delayed due to
    # land acquisition.
    df["delay_due_to_land_acquisition"] = 1

    # ---------------------------------------------
    # Provenance fields
    # ---------------------------------------------

    df["source_name"] = SOURCE_NAME

    df["source_authority"] = (
        SOURCE_AUTHORITY
    )

    df["source_platform"] = (
        SOURCE_PLATFORM
    )

    df["source_reference_date"] = (
        SOURCE_REFERENCE_DATE
    )

    df["source_url"] = SOURCE_URL

    df["is_government_data"] = True

    df["is_demo"] = False

    return df


def print_quality_report(
    raw_df: pd.DataFrame,
    processed_df: pd.DataFrame,
) -> None:

    print("\n================================")
    print("LIVA GOVERNMENT DATA PROCESSING")
    print("================================")

    print(
        "\nRaw records:",
        len(raw_df),
    )

    print(
        "Processed records:",
        len(processed_df),
    )

    print(
        "Duplicate project names:",
        processed_df[
            "project_name"
        ].duplicated().sum(),
    )

    print(
        "Missing values:",
        int(
            processed_df
            .isna()
            .sum()
            .sum()
        ),
    )

    print(
        "\nAcquisition completion:"
    )

    print(
        processed_df[
            [
                "project_name",
                "acquisition_completion_pct",
                "pending_land_pct",
            ]
        ].to_string(
            index=False
        )
    )

    print(
        "\nOfficial source:",
        SOURCE_AUTHORITY,
    )

    print(
        "Reference date:",
        SOURCE_REFERENCE_DATE,
    )

    print(
        "\nSaved:",
        PROCESSED_FILE,
    )


def main():
    raw_df = load_dataset()

    validate_columns(raw_df)

    processed_df = clean_dataset(
        raw_df
    )

    PROCESSED_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    processed_df.to_csv(
        PROCESSED_FILE,
        index=False,
    )

    print_quality_report(
        raw_df,
        processed_df,
    )


if __name__ == "__main__":
    main()