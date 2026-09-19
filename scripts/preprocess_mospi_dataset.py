from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parents[1]

RAW_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "Projects_Report.csv"
)

PROCESSED_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "mospi_march_2026_training_ready.csv"
)


COLUMN_MAP = {
    "Sector Name": "sector",
    "Line Ministry": "line_ministry",
    "Implementing Agency": "implementing_agency",
    "Project Code": "project_code",
    "Project Name": "project_name",
    "Original Cost\n(in cr.)": "original_cost_cr",
    "Revised Cost\n(in cr.)": "revised_cost_cr",
    "Expenditure\n(in cr.)": "expenditure_cr",
    "Physical Progress\n(in %)": "physical_progress_pct",
    "Original\nDate of Commissioning": "original_end_date",
    "Revised\nDate of Commissioning": "revised_date",
    "Sanction Date": "sanction_date",
}


def load_data() -> pd.DataFrame:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"Dataset not found:\n{RAW_FILE}"
        )

    # PAIMANA export contains:
    # row 1 = "Projects Details"
    # row 2 = blank
    # row 3 = actual CSV header
    return pd.read_csv(
        RAW_FILE,
        skiprows=2,
    )


def preprocess(
    df: pd.DataFrame,
) -> pd.DataFrame:
    df = df.copy()

    missing = [
        column
        for column in COLUMN_MAP
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Missing columns: {missing}"
        )

    df = df.rename(
        columns=COLUMN_MAP
    )

    # -----------------------------
    # Text cleanup
    # -----------------------------

    text_columns = [
        "sector",
        "line_ministry",
        "implementing_agency",
        "project_name",
    ]

    for column in text_columns:
        df[column] = (
            df[column]
            .fillna("")
            .astype(str)
            .str.strip()
        )

    # -----------------------------
    # Numeric columns
    # -----------------------------

    numeric_columns = [
        "original_cost_cr",
        "revised_cost_cr",
        "expenditure_cr",
        "physical_progress_pct",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # Revised cost = 0 in export often
    # means no revised value recorded.
    df.loc[
        df["revised_cost_cr"] <= 0,
        "revised_cost_cr",
    ] = pd.NA

    # -----------------------------
    # Dates
    # -----------------------------

    date_columns = [
        "original_end_date",
        "revised_date",
        "sanction_date",
    ]

    for column in date_columns:
        df[column] = pd.to_datetime(
            df[column],
            format="%d/%m/%Y",
            errors="coerce",
        )

    # Schedule target requires both dates.
    df = df.dropna(
        subset=[
            "original_end_date",
            "revised_date",
            "original_cost_cr",
        ]
    ).copy()

    # -----------------------------
    # Delay target
    # -----------------------------

    df["schedule_delay_days"] = (
        df["revised_date"]
        - df["original_end_date"]
    ).dt.days

    df["schedule_delay_days"] = (
        df["schedule_delay_days"]
        .clip(lower=0)
    )

    df["is_schedule_delayed"] = (
        df["schedule_delay_days"] > 0
    ).astype(int)

    # -----------------------------
    # Cost features
    # -----------------------------

    df["cost_overrun_cr"] = (
        df["revised_cost_cr"]
        - df["original_cost_cr"]
    )

    df["cost_overrun_pct"] = (
        (
            df["revised_cost_cr"]
            - df["original_cost_cr"]
        )
        / df["original_cost_cr"]
        * 100
    ).round(2)

    # -----------------------------
    # Expenditure features
    # -----------------------------

    df["expenditure_ratio"] = (
        df["expenditure_cr"]
        / df["original_cost_cr"]
    ).round(4)

    df["expenditure_pct_of_original"] = (
        df["expenditure_ratio"]
        * 100
    ).round(2)

    # -----------------------------
    # Schedule features
    # -----------------------------

    df["original_completion_year"] = (
        df["original_end_date"].dt.year
    )

    df["revised_completion_year"] = (
        df["revised_date"].dt.year
    )

    df["sanction_year"] = (
        df["sanction_date"].dt.year
    )

    # -----------------------------
    # Government provenance
    # -----------------------------

    df["source_authority"] = (
        "Ministry of Statistics and Programme Implementation"
    )

    df["source_department"] = (
        "Infrastructure and Project Monitoring Division"
    )

    df["source_platform"] = "PAIMANA"

    df["source_dataset"] = (
        "Projects Report - Public Dashboard"
    )

    df["source_reference_period"] = (
        "March 2026"
    )

    df["is_government_data"] = True
    df["is_demo"] = False

    return df


def main():
    raw_df = load_data()

    print(
        "Raw PAIMANA projects:",
        len(raw_df),
    )

    processed_df = preprocess(
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

    print(
        "\nTraining-ready rows:",
        len(processed_df),
    )

    print(
        "\nClass distribution:"
    )

    print(
        processed_df[
            "is_schedule_delayed"
        ]
        .value_counts()
        .sort_index()
    )

    print(
        "\nSaved to:",
        PROCESSED_FILE,
    )


if __name__ == "__main__":
    main()