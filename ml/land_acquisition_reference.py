from functools import lru_cache
from pathlib import Path

import pandas as pd

from ml.schemas import GovernmentLandReference


BASE_DIR = Path(__file__).resolve().parents[1]

DATA_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "liva_land_acquisition_master.csv"
)


@lru_cache(maxsize=1)
def _load_reference_data() -> pd.DataFrame | None:
    if not DATA_FILE.exists():
        print(
            f"[LIVA] Government dataset not found: {DATA_FILE}"
        )
        return None

    df = pd.read_csv(DATA_FILE)

    required = [
        "state",
        "project_name",
        "total_land_ha",
        "land_acquired_ha",
        "balance_land_ha",
        "acquired_pct",
        "pending_land_pct",
        "source_file",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"Government dataset missing columns: {missing}"
        )

    numeric_columns = [
        "total_land_ha",
        "land_acquired_ha",
        "balance_land_ha",
        "acquired_pct",
        "pending_land_pct",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df["state"] = (
        df["state"]
        .astype(str)
        .str.strip()
    )

    df = df.dropna(
        subset=[
            "total_land_ha",
            "land_acquired_ha",
            "balance_land_ha",
            "pending_land_pct",
        ]
    )

    return df


def get_land_acquisition_reference(
    state: str | None = None,
) -> GovernmentLandReference | None:

    df = _load_reference_data()

    if df is None or df.empty:
        return None

    scoped = df.copy()

    scope = "ALL_STATES"
    matched_state = None

    if state:
        requested_state = (
            str(state)
            .strip()
            .casefold()
        )

        state_rows = df[
            df["state"]
            .str.casefold()
            .eq(requested_state)
        ]

        if not state_rows.empty:
            scoped = state_rows.copy()
            scope = "STATE"
            matched_state = state

    average_pending = round(
        float(
            scoped["pending_land_pct"].mean()
        ),
        2,
    )

    median_pending = round(
        float(
            scoped["pending_land_pct"].median()
        ),
        2,
    )

    high_backlog_projects = int(
        (
            scoped["pending_land_pct"] >= 75
        ).sum()
    )

    zero_acquisition_projects = int(
        (
            scoped["land_acquired_ha"] <= 0
        ).sum()
    )

    source_files = sorted(
        scoped["source_file"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    return GovernmentLandReference(
        scope=scope,
        state=matched_state,
        record_count=int(len(scoped)),
        average_pending_land_pct=average_pending,
        median_pending_land_pct=median_pending,
        high_backlog_projects=high_backlog_projects,
        zero_acquisition_projects=zero_acquisition_projects,
        source_files=source_files,
        note=(
            "Verified government land-acquisition records "
            "used as contextual evidence. These records do "
            "not directly change the current rule-based score."
        ),
    )