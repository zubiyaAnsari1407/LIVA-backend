from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from bson import ObjectId


BACKEND_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(BACKEND_DIR),
)

from database import db  # noqa: E402


RAW_FILE = (
    BACKEND_DIR
    / "data"
    / "raw"
    / "Projects_Report.csv"
)

BACKUP_DIR = (
    BACKEND_DIR
    / "data"
    / "backups"
)

PAIMANA_URL = (
    "https://paimana-proj.mospi.gov.in/"
    "Home/PublicDashboardNew"
)

TARGET_PROJECT_COUNT = 6


def normalize_columns(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    frame = frame.copy()

    frame.columns = [
        " ".join(
            str(column).split()
        )
        for column
        in frame.columns
    ]

    return frame


def numeric_series(
    series: pd.Series,
) -> pd.Series:
    cleaned = (
        series
        .astype(str)
        .str.replace(
            ",",
            "",
            regex=False,
        )
        .str.strip()
    )

    return pd.to_numeric(
        cleaned,
        errors="coerce",
    )


def date_series(
    series: pd.Series,
) -> pd.Series:
    return pd.to_datetime(
        series,
        errors="coerce",
        dayfirst=True,
    )


def json_safe(
    value,
):
    if isinstance(
        value,
        ObjectId,
    ):
        return str(value)

    if isinstance(
        value,
        datetime,
    ):
        return value.isoformat()

    if isinstance(
        value,
        dict,
    ):
        return {
            key: json_safe(item)
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        list,
    ):
        return [
            json_safe(item)
            for item
            in value
        ]

    return value


def backup_demo_projects(
    projects: list[dict],
):
    if not projects:
        return

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    path = (
        BACKUP_DIR
        / f"demo_projects_{stamp}.json"
    )

    payload = [
        json_safe(project)
        for project
        in projects
    ]

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"Backup created: {path}"
    )


def delete_demo_data():
    demos = list(
        db.projects.find(
            {
                "isDemo": True,
            }
        )
    )

    if not demos:
        print(
            "No demo projects found."
        )
        return 0


    backup_demo_projects(
        demos
    )


    object_ids = [
        project["_id"]
        for project
        in demos
    ]

    string_ids = [
        str(project["_id"])
        for project
        in demos
    ]


    print(
        "\nDemo projects to delete:"
    )

    for project in demos:
        print(
            " -",
            project.get(
                "name",
                str(
                    project["_id"]
                ),
            ),
        )


    # Remove linked records safely.
    #
    # This automatically checks every collection
    # for projectId / project_id references.
    #
    # Non-demo project records are NOT touched.

    collection_names = (
        db.list_collection_names()
    )


    for collection_name in collection_names:
        if collection_name == "projects":
            continue

        collection = db[
            collection_name
        ]

        query = {
            "$or": [
                {
                    "projectId": {
                        "$in":
                            string_ids
                    }
                },
                {
                    "projectId": {
                        "$in":
                            object_ids
                    }
                },
                {
                    "project_id": {
                        "$in":
                            string_ids
                    }
                },
                {
                    "project_id": {
                        "$in":
                            object_ids
                    }
                },
            ]
        }

        result = (
            collection.delete_many(
                query
            )
        )

        if result.deleted_count:
            print(
                f"Removed "
                f"{result.deleted_count} "
                f"linked records from "
                f"{collection_name}"
            )


    result = (
        db.projects.delete_many(
            {
                "_id": {
                    "$in":
                        object_ids
                }
            }
        )
    )


    print(
        f"\nDeleted "
        f"{result.deleted_count} "
        f"demo projects."
    )


    return result.deleted_count


def load_paimana() -> pd.DataFrame:
    if not RAW_FILE.exists():
        raise FileNotFoundError(
            f"PAIMANA export not found:\n"
            f"{RAW_FILE}"
        )


    frame = pd.read_csv(
        RAW_FILE,
        skiprows=2,
    )


    frame = normalize_columns(
        frame
    )


    required = [
        "Sector Name",
        "Line Ministry",
        "Project Code",
        "Project Name",
        "Original Cost (in cr.)",
        "Expenditure (in cr.)",
        "Physical Progress (in %)",
        "Original Date of Commissioning",
        "Sanction Date",
    ]


    missing = [
        column
        for column
        in required
        if column not in frame.columns
    ]


    if missing:
        raise RuntimeError(
            "Missing PAIMANA columns: "
            + ", ".join(
                missing
            )
        )


    frame[
        "original_cost_cr"
    ] = numeric_series(
        frame[
            "Original Cost (in cr.)"
        ]
    )


    frame[
        "expenditure_cr"
    ] = numeric_series(
        frame[
            "Expenditure (in cr.)"
        ]
    )


    frame[
        "physical_progress_pct"
    ] = numeric_series(
        frame[
            "Physical Progress (in %)"
        ]
    )


    original_dates = date_series(
        frame[
            "Original Date of Commissioning"
        ]
    )


    sanction_dates = date_series(
        frame[
            "Sanction Date"
        ]
    )


    frame[
        "original_completion_year"
    ] = original_dates.dt.year


    frame[
        "sanction_year"
    ] = sanction_dates.dt.year


    return frame


def eligible_projects(
    frame: pd.DataFrame,
) -> pd.DataFrame:
    result = frame.copy()


    result = result.dropna(
        subset=[
            "Project Code",
            "Project Name",
            "Sector Name",
            "Line Ministry",
            "original_cost_cr",
            "expenditure_cr",
            "physical_progress_pct",
            "original_completion_year",
            "sanction_year",
        ]
    )


    result = result[
        (
            result[
                "original_cost_cr"
            ] > 0
        )
        &
        (
            result[
                "expenditure_cr"
            ] >= 0
        )
        &
        (
            result[
                "physical_progress_pct"
            ].between(
                0,
                100,
            )
        )
    ]


    result[
        "Project Code"
    ] = (
        result[
            "Project Code"
        ]
        .astype(str)
        .str.strip()
    )


    result[
        "Project Name"
    ] = (
        result[
            "Project Name"
        ]
        .astype(str)
        .str.strip()
    )


    return result


def existing_paimana_codes():
    documents = db.projects.find(
        {
            "isDemo": False,
            "sourceName": {
                "$regex":
                    "PAIMANA",
                "$options":
                    "i",
            },
        },
        {
            "sourceRecordId": 1,
        },
    )


    return {
        str(
            document.get(
                "sourceRecordId",
                "",
            )
        )
        for document
        in documents
        if document.get(
            "sourceRecordId"
        )
    }


def current_paimana_count():
    return db.projects.count_documents(
        {
            "isDemo": False,
            "sourceName": {
                "$regex":
                    "PAIMANA",
                "$options":
                    "i",
            },
        }
    )


def select_projects(
    frame: pd.DataFrame,
    count: int,
) -> pd.DataFrame:
    existing_codes = (
        existing_paimana_codes()
    )


    frame = frame[
        ~frame[
            "Project Code"
        ].isin(
            existing_codes
        )
    ]


    # Pick projects from different sectors first,
    # so GIS/filter testing is more useful.

    frame = frame.sort_values(
        by=[
            "Sector Name",
            "Project Code",
        ],
        kind="stable",
    )


    chosen_indexes = []

    used_sectors = set()


    for index, row in (
        frame.iterrows()
    ):
        sector = str(
            row[
                "Sector Name"
            ]
        ).strip()


        if sector in used_sectors:
            continue


        chosen_indexes.append(
            index
        )

        used_sectors.add(
            sector
        )


        if (
            len(
                chosen_indexes
            )
            >= count
        ):
            break


    # If fewer than requested sectors exist,
    # fill remaining slots with other valid rows.

    if (
        len(
            chosen_indexes
        )
        < count
    ):
        for index in frame.index:
            if (
                index in
                chosen_indexes
            ):
                continue


            chosen_indexes.append(
                index
            )


            if (
                len(
                    chosen_indexes
                )
                >= count
            ):
                break


    return frame.loc[
        chosen_indexes
    ]


def build_document(
    row: pd.Series,
):
    now = datetime.now(
        timezone.utc
    )


    original_cost = float(
        row[
            "original_cost_cr"
        ]
    )


    expenditure = float(
        row[
            "expenditure_cr"
        ]
    )


    progress = float(
        row[
            "physical_progress_pct"
        ]
    )


    document = {
        "name":
            str(
                row[
                    "Project Name"
                ]
            ).strip(),

        # The downloaded PAIMANA Projects Report
        # used here does not provide reliable
        # state/district fields for every record.
        #
        # Do not invent them.
        "state":
            "Not specified in PAIMANA export",

        "district":
            "Not specified in PAIMANA export",

        # Acquisition stage is also not present
        # in this PAIMANA infrastructure export.
        "stage":
            "Not specified",

        "progress":
            progress,

        "description":
            (
                "Official MoSPI/PAIMANA "
                "public-dashboard project record. "
                "Acquisition-specific fields are "
                "not inferred where the source "
                "does not provide them."
            ),

        "sector":
            str(
                row[
                    "Sector Name"
                ]
            ).strip(),

        "line_ministry":
            str(
                row[
                    "Line Ministry"
                ]
            ).strip(),

        "original_cost_cr":
            original_cost,

        "expenditure_cr":
            expenditure,

        "physical_progress_pct":
            progress,

        "original_completion_year":
            int(
                row[
                    "original_completion_year"
                ]
            ),

        "sanction_year":
            int(
                row[
                    "sanction_year"
                ]
            ),

        "isDemo":
            False,

        "sourceName":
            "MoSPI PAIMANA Public Dashboard",

        "sourceUrl":
            PAIMANA_URL,

        "sourceRecordId":
            str(
                row[
                    "Project Code"
                ]
            ).strip(),

        "createdAt":
            now,

        "updatedAt":
            now,
    }


    if (
        "Implementing Agency"
        in row.index
        and pd.notna(
            row[
                "Implementing Agency"
            ]
        )
    ):
        document[
            "implementing_agency"
        ] = str(
            row[
                "Implementing Agency"
            ]
        ).strip()


    return document


def seed_projects():
    current_count = (
        current_paimana_count()
    )


    required = max(
        TARGET_PROJECT_COUNT
        - current_count,
        0,
    )


    print(
        f"\nExisting real PAIMANA "
        f"projects: {current_count}"
    )


    if required == 0:
        print(
            "Already have 6 or more "
            "real PAIMANA projects."
        )

        return


    frame = load_paimana()


    eligible = (
        eligible_projects(
            frame
        )
    )


    selected = (
        select_projects(
            eligible,
            required,
        )
    )


    if selected.empty:
        raise RuntimeError(
            "No eligible PAIMANA "
            "projects available."
        )


    print(
        f"\nAdding "
        f"{len(selected)} "
        f"real PAIMANA projects:"
    )


    for _, row in selected.iterrows():
        document = (
            build_document(
                row
            )
        )


        duplicate = (
            db.projects.find_one(
                {
                    "isDemo": False,
                    "sourceRecordId":
                        document[
                            "sourceRecordId"
                        ],
                }
            )
        )


        if duplicate:
            continue


        result = (
            db.projects.insert_one(
                document
            )
        )


        print(
            " +",
            document["name"],
            "|",
            document["sector"],
            "| ID:",
            result.inserted_id,
        )


def show_final_state():
    print(
        "\n==========================="
    )

    print(
        "FINAL PROJECT STATE"
    )

    print(
        "==========================="
    )


    all_projects = list(
        db.projects.find(
            {},
            {
                "name": 1,
                "isDemo": 1,
                "sourceName": 1,
                "sourceRecordId": 1,
            },
        )
    )


    for project in all_projects:
        print(
            "REAL"
            if not project.get(
                "isDemo",
                True,
            )
            else "DEMO",
            "|",
            project.get(
                "name"
            ),
            "|",
            project.get(
                "sourceRecordId",
                "-",
            ),
        )


    print(
        "\nTotal projects:",
        len(
            all_projects
        ),
    )


    print(
        "Demo projects:",
        db.projects.count_documents(
            {
                "isDemo": True
            }
        ),
    )


    print(
        "PAIMANA projects:",
        current_paimana_count(),
    )


if __name__ == "__main__":
    print(
        "\nLIVA DATA RESET"
    )

    print(
        "Official PAIMANA projects "
        "will be preserved."
    )


    delete_demo_data()

    seed_projects()

    show_final_state()