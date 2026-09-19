from io import StringIO
from pathlib import Path
import re

import pandas as pd
import requests


BASE_DIR = Path(__file__).resolve().parents[1]

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "mospi_public_dashboard_march_2026.csv"
)

OFFICIAL_URL = (
    "https://uatipm.mospi.gov.in/Home/PublicDashboard"
)


def clean_column_name(value: object) -> str:
    text = str(value)

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if isinstance(
        df.columns,
        pd.MultiIndex,
    ):
        flattened = []

        for column in df.columns:
            parts = [
                clean_column_name(part)
                for part in column
                if (
                    str(part) != "nan"
                    and not str(part).startswith(
                        "Unnamed"
                    )
                )
            ]

            flattened.append(
                " ".join(parts)
            )

        df.columns = flattened

    else:
        df.columns = [
            clean_column_name(column)
            for column in df.columns
        ]

    return df


def normalise_name(value: str) -> str:
    value = value.lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def find_project_table(
    tables: list[pd.DataFrame],
) -> pd.DataFrame:

    for index, raw_table in enumerate(
        tables
    ):
        table = flatten_columns(
            raw_table
        )

        normalised_columns = [
            normalise_name(column)
            for column in table.columns
        ]

        joined = " | ".join(
            normalised_columns
        )

        required_signals = [
            "project code",
            "project name",
            "original cost",
            "original end date",
        ]

        if all(
            signal in joined
            for signal in required_signals
        ):
            print(
                f"Project table detected: "
                f"HTML table #{index + 1}"
            )

            return table

    raise ValueError(
        "Could not identify the MoSPI "
        "project-level table."
    )


def find_column(
    columns: list[str],
    required_words: list[str],
) -> str | None:

    for column in columns:
        normalised = normalise_name(
            column
        )

        if all(
            word in normalised
            for word in required_words
        ):
            return column

    return None


def standardise_project_table(
    df: pd.DataFrame,
) -> pd.DataFrame:

    columns = list(df.columns)

    mapping = {}

    searches = {
        "sector": [
            "sector"
        ],
        "line_ministry": [
            "line",
            "ministry",
        ],
        "project_code": [
            "project",
            "code",
        ],
        "project_name": [
            "project",
            "name",
        ],
        "original_cost_cr": [
            "original",
            "cost",
        ],
        "revised_cost_cr": [
            "revised",
            "cost",
        ],
        "expenditure_cr": [
            "expenditure",
        ],
        "original_end_date": [
            "original",
            "end",
            "date",
        ],
        "revised_date": [
            "revised",
            "date",
        ],
    }

    for target, words in searches.items():
        source = find_column(
            columns,
            words,
        )

        if source:
            mapping[source] = target

    df = df.rename(
        columns=mapping
    )

    required = [
        "project_code",
        "project_name",
        "original_cost_cr",
        "expenditure_cr",
        "original_end_date",
        "revised_date",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        print(
            "\nDetected columns:"
        )

        for column in df.columns:
            print("-", column)

        raise ValueError(
            f"Required project columns "
            f"not detected: {missing}"
        )

    wanted_columns = [
        "sector",
        "line_ministry",
        "project_code",
        "project_name",
        "original_cost_cr",
        "revised_cost_cr",
        "expenditure_cr",
        "original_end_date",
        "revised_date",
    ]

    existing = [
        column
        for column in wanted_columns
        if column in df.columns
    ]

    df = df[
        existing
    ].copy()

    # Remove blank / repeated header rows
    df["project_name"] = (
        df["project_name"]
        .astype(str)
        .str.strip()
    )

    df = df[
        ~df["project_name"]
        .str.lower()
        .isin(
            [
                "",
                "nan",
                "project name",
            ]
        )
    ]

    # Provenance
    df["source_authority"] = (
        "Ministry of Statistics and "
        "Programme Implementation"
    )

    df["source_department"] = (
        "Infrastructure and Project "
        "Monitoring Division"
    )

    df["source_platform"] = "PAIMANA"

    df["source_reference_period"] = (
        "March 2026"
    )

    df["source_url"] = OFFICIAL_URL

    df["is_government_data"] = True
    df["is_demo"] = False

    return df


def fetch_dashboard():
    print("\n==============================")
    print("LIVA FULL MOSPI DATA INGESTION")
    print("==============================")

    print("\nOfficial source:")
    print(OFFICIAL_URL)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "LIVA Government Data Research"
        )
    }

    response = requests.get(
        OFFICIAL_URL,
        headers=headers,
        timeout=60,
    )

    response.raise_for_status()

    print(
        "\nHTTP status:",
        response.status_code,
    )

    tables = pd.read_html(
        StringIO(
            response.text
        )
    )

    print(
        "HTML tables detected:",
        len(tables),
    )

    project_table = find_project_table(
        tables
    )

    project_table = (
        standardise_project_table(
            project_table
        )
    )

    project_table = (
        project_table
        .drop_duplicates(
            subset=[
                "project_code"
            ]
        )
        .reset_index(
            drop=True
        )
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    project_table.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print("\n==============================")
    print("INGESTION RESULT")
    print("==============================")

    print(
        "\nGovernment project rows:",
        len(project_table),
    )

    print(
        "\nColumns:"
    )

    for column in project_table.columns:
        print(
            "-",
            column,
        )

    print(
        "\nFirst 5 projects:\n"
    )

    print(
        project_table
        .head()
        .to_string(
            index=False
        )
    )

    print(
        "\nSaved:"
    )

    print(
        OUTPUT_FILE
    )


if __name__ == "__main__":
    fetch_dashboard()