from datetime import date, datetime, timezone
from typing import Any

from bson import ObjectId

from database import db
from ml.feature_builder import build_risk_features
from ml.schemas import RiskFeatureInput


# ============================================================
# Collection aliases
# Supports current/future naming differences in LIVA
# ============================================================

COLLECTIONS = {
    "projects": ["projects"],
    "parcels": ["parcels", "land_parcels"],
    "ownership": [
        "ownership",
        "ownership_reviews",
        "ownership_review",
    ],
    "surveys": [
        "surveys",
        "survey",
        "survey_reviews",
        "survey_review",
    ],
    "litigation": [
        "litigation",
        "litigations",
        "court_cases",
    ],
    "documents": [
        "documents",
        "project_documents",
    ],
    "compensation": [
        "compensation",
        "compensations",
    ],
    "approvals": [
        "approvals",
        "approval",
    ],
    "actions": [
        "actions",
        "tasks",
    ],
}


PROJECT_REFERENCE_FIELDS = [
    "project_id",
    "projectId",
    "project",
    "parent_project_id",
    "project_ref",
]


TERMINAL_STATUSES = {
    "completed",
    "complete",
    "done",
    "closed",
    "resolved",
    "verified",
    "approved",
    "paid",
    "settled",
    "disbursed",
    "acquired",
    "cancelled",
    "canceled",
}


# ============================================================
# Collection helpers
# ============================================================

def _get_collection(alias_group: str):
    """
    Find the first existing MongoDB collection for a logical
    LIVA workflow module.
    """

    available = set(db.list_collection_names())

    for name in COLLECTIONS[alias_group]:
        if name in available:
            return db[name]

    return None


def _project_query(project_id: str) -> dict:
    options: list[dict[str, Any]] = [
        {"project_id": project_id},
        {"id": project_id},
    ]

    if ObjectId.is_valid(project_id):
        options.append(
            {"_id": ObjectId(project_id)}
        )

    return {
        "$or": options
    }


def _find_project(project_id: str) -> dict:
    collection = _get_collection("projects")

    if collection is None:
        raise LookupError(
            "Projects collection was not found."
        )

    project = collection.find_one(
        _project_query(project_id)
    )

    if project is None:
        raise LookupError(
            f"Project '{project_id}' was not found."
        )

    return project


def _project_reference_values(
    project: dict,
) -> list[Any]:
    """
    Different workflow collections may store either:
    - MongoDB ObjectId
    - string ObjectId
    - custom project_id
    """

    values: list[Any] = []

    for key in (
        "_id",
        "project_id",
        "id",
    ):
        value = project.get(key)

        if value is not None:
            values.append(value)

            string_value = str(value)

            if string_value not in values:
                values.append(string_value)

    return values


def _linked_query(project: dict) -> dict:
    refs = _project_reference_values(project)

    return {
        "$or": [
            {
                field: {
                    "$in": refs
                }
            }
            for field in PROJECT_REFERENCE_FIELDS
        ]
    }


def _load_project_documents(
    alias_group: str,
    project: dict,
) -> list[dict]:
    collection = _get_collection(alias_group)

    if collection is None:
        return []

    return list(
        collection.find(
            _linked_query(project)
        )
    )


# ============================================================
# Generic value helpers
# ============================================================

def _first_value(
    document: dict,
    fields: list[str],
    default=None,
):
    for field in fields:
        value = document.get(field)

        if value is not None:
            return value

    return default


def _normalise_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value).strip().lower()


def _status(document: dict) -> str:
    return _normalise_text(
        _first_value(
            document,
            [
                "status",
                "review_status",
                "workflow_status",
                "case_status",
                "payment_status",
                "approval_status",
                "task_status",
            ],
            "",
        )
    )


def _is_open(document: dict) -> bool:
    completed_flag = _first_value(
        document,
        [
            "completed",
            "is_completed",
            "isComplete",
        ],
    )

    if completed_flag is True:
        return False

    status = _status(document)

    if not status:
        return True

    return status not in TERMINAL_STATUSES


# ============================================================
# Date helpers
# ============================================================

def _parse_datetime(
    value: Any,
) -> datetime | None:

    if value is None:
        return None

    if isinstance(value, datetime):
        parsed = value

    elif isinstance(value, date):
        parsed = datetime(
            value.year,
            value.month,
            value.day,
        )

    elif isinstance(value, str):
        cleaned = value.strip()

        if not cleaned:
            return None

        try:
            parsed = datetime.fromisoformat(
                cleaned.replace(
                    "Z",
                    "+00:00",
                )
            )
        except ValueError:
            return None

    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed


def _overdue_days(document: dict) -> int:
    due_value = _first_value(
        document,
        [
            "due_date",
            "dueDate",
            "deadline",
            "target_date",
            "targetDate",
        ],
    )

    due_date = _parse_datetime(due_value)

    if due_date is None:
        return 0

    if not _is_open(document):
        return 0

    now = datetime.now(timezone.utc)

    if due_date >= now:
        return 0

    return max(
        (now - due_date).days,
        0,
    )


# ============================================================
# Workflow specific helpers
# ============================================================

def _has_ownership_dispute(
    document: dict,
) -> bool:

    explicit = _first_value(
        document,
        [
            "has_dispute",
            "disputed",
            "ownership_dispute",
            "has_ownership_dispute",
        ],
    )

    if explicit is True:
        return True

    dispute_status = _normalise_text(
        _first_value(
            document,
            [
                "dispute_status",
                "ownership_status",
            ],
        )
    )

    if dispute_status in {
        "disputed",
        "pending dispute",
        "unresolved",
        "open",
    }:
        return True

    return "dispute" in _status(document)


def _is_high_risk_case(
    document: dict,
) -> bool:

    value = _normalise_text(
        _first_value(
            document,
            [
                "risk_level",
                "risk",
                "severity",
                "priority",
            ],
        )
    )

    return value in {
        "high",
        "critical",
        "very high",
    }


def _is_missing_document(
    document: dict,
) -> bool:

    status = _status(document)

    if status in {
        "missing",
        "not submitted",
        "not_submitted",
        "rejected",
        "pending",
    }:
        return True

    required = _first_value(
        document,
        [
            "required",
            "is_required",
            "mandatory",
        ],
    )

    uploaded = _first_value(
        document,
        [
            "uploaded",
            "is_uploaded",
            "verified",
        ],
    )

    return (
        required is True
        and uploaded is False
    )


# ============================================================
# Completion calculation
# ============================================================

def _completion_percentage(
    project: dict,
    total_parcels: int,
    pending_parcels: int,
) -> float:

    raw = _first_value(
        project,
        [
            "completion_percentage",
            "completionPercentage",
            "progress_percentage",
            "progress",
        ],
    )

    if raw is not None:
        try:
            value = float(raw)

            # Supports values such as 0.65
            if 0 < value <= 1:
                value *= 100

            return max(
                0.0,
                min(value, 100.0),
            )

        except (TypeError, ValueError):
            pass

    if total_parcels > 0:
        completed = max(
            total_parcels - pending_parcels,
            0,
        )

        return round(
            completed / total_parcels * 100,
            2,
        )

    return 0.0


# ============================================================
# Main MongoDB feature builder
# ============================================================

def build_project_risk_features(
    project_id: str,
) -> RiskFeatureInput:
    """
    Build risk features directly from REAL LIVA MongoDB data.

    This does not create synthetic project data.
    It aggregates records already saved through the
    LIVA operational workflow.
    """

    project = _find_project(project_id)

    parcels = _load_project_documents(
        "parcels",
        project,
    )

    ownership = _load_project_documents(
        "ownership",
        project,
    )

    surveys = _load_project_documents(
        "surveys",
        project,
    )

    litigation = _load_project_documents(
        "litigation",
        project,
    )

    documents = _load_project_documents(
        "documents",
        project,
    )

    compensation = _load_project_documents(
        "compensation",
        project,
    )

    approvals = _load_project_documents(
        "approvals",
        project,
    )

    actions = _load_project_documents(
        "actions",
        project,
    )

    # --------------------------------------------------------
    # Parcels
    # --------------------------------------------------------

    total_parcels = len(parcels)

    pending_parcels = sum(
        1
        for record in parcels
        if _is_open(record)
    )

    # --------------------------------------------------------
    # Ownership
    # --------------------------------------------------------

    ownership_disputes = sum(
        1
        for record in ownership
        if _has_ownership_dispute(record)
    )

    ownership_pending = sum(
        1
        for record in ownership
        if _is_open(record)
    )

    # --------------------------------------------------------
    # Survey
    # --------------------------------------------------------

    survey_pending = sum(
        1
        for record in surveys
        if _is_open(record)
    )

    # --------------------------------------------------------
    # Litigation
    # --------------------------------------------------------

    active_litigation_cases = sum(
        1
        for record in litigation
        if _is_open(record)
    )

    high_risk_litigation_cases = sum(
        1
        for record in litigation
        if _is_open(record)
        and _is_high_risk_case(record)
    )

    # --------------------------------------------------------
    # Documents
    # --------------------------------------------------------

    missing_documents = sum(
        1
        for record in documents
        if _is_missing_document(record)
    )

    # --------------------------------------------------------
    # Compensation
    # --------------------------------------------------------

    compensation_pending = sum(
        1
        for record in compensation
        if _is_open(record)
    )

    # --------------------------------------------------------
    # Approvals
    # --------------------------------------------------------

    pending_approvals = sum(
        1
        for record in approvals
        if _is_open(record)
    )

    # --------------------------------------------------------
    # Action Center
    # --------------------------------------------------------

    open_actions = sum(
        1
        for record in actions
        if _is_open(record)
    )

    overdue_actions = sum(
        1
        for record in actions
        if _overdue_days(record) > 0
    )

    high_priority_open_actions = sum(
        1
        for record in actions
        if (
            _is_open(record)
            and _normalise_text(
                record.get("priority")
            )
            in {
                "high",
                "critical",
                "urgent",
            }
        )
    )

    # --------------------------------------------------------
    # Maximum overdue duration
    # --------------------------------------------------------

    overdue_candidates = (
        ownership
        + surveys
        + litigation
        + compensation
        + approvals
        + actions
    )

    max_overdue_days = max(
        (
            _overdue_days(record)
            for record
            in overdue_candidates
        ),
        default=0,
    )

    # --------------------------------------------------------
    # Completion %
    # --------------------------------------------------------

    completion_percentage = (
        _completion_percentage(
            project,
            total_parcels,
            pending_parcels,
        )
    )

    # --------------------------------------------------------
    # Standard LIVA feature object
    # --------------------------------------------------------

    metrics = {
        "total_parcels": total_parcels,
        "pending_parcels": pending_parcels,

        "ownership_disputes":
            ownership_disputes,

        "ownership_pending":
            ownership_pending,

        "survey_pending":
            survey_pending,

        "active_litigation_cases":
            active_litigation_cases,

        "high_risk_litigation_cases":
            high_risk_litigation_cases,

        "missing_documents":
            missing_documents,

        "compensation_pending":
            compensation_pending,

        "pending_approvals":
            pending_approvals,

        "max_overdue_days":
            max_overdue_days,

        "open_actions":
            open_actions,

        "overdue_actions":
            overdue_actions,

        "high_priority_open_actions":
            high_priority_open_actions,

        "completion_percentage":
            completion_percentage,
    }

    return build_risk_features(
        project,
        metrics,
    )