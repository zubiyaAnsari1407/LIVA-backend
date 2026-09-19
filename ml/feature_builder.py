from typing import Any

from ml.schemas import RiskFeatureInput


# ============================================================
# Utility functions
# ============================================================

def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """
    Convert incoming values safely to non-negative integers.
    """

    try:
        result = int(value)

        return max(
            result,
            0,
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """
    Convert incoming values safely to a non-negative float.
    """

    try:
        result = float(value)

        return max(
            result,
            0.0,
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def _percentage(
    part: int,
    total: int,
) -> float:
    """
    Calculate percentage safely.
    """

    if total <= 0:
        return 0.0

    return round(
        (
            part
            / total
        )
        * 100,
        2,
    )


def _clean_optional_string(
    value: Any,
) -> str | None:
    """
    Convert optional project fields into clean strings.
    """

    if value is None:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    return value


# ============================================================
# Build workflow risk features
# ============================================================

def build_risk_features(
    project: dict[str, Any],
    workflow_metrics: dict[str, Any],
) -> RiskFeatureInput:
    """
    Build normalized delay-risk features for one LIVA project.

    Project information comes from the projects collection.

    Workflow metrics can come from:
    - parcels
    - ownership
    - surveys
    - litigation
    - documents
    - compensation
    - approvals
    - actions
    """

    # --------------------------------------------------------
    # Project identification
    # --------------------------------------------------------

    project_id = str(
        project.get("project_id")
        or project.get("id")
        or project.get("_id")
        or ""
    ).strip()

    if not project_id:
        raise ValueError(
            "project_id is required "
            "to build risk features."
        )

    project_name = (
        project.get("project_name")
        or project.get("name")
        or project.get("title")
    )

    project_name = (
        _clean_optional_string(
            project_name
        )
    )

    # --------------------------------------------------------
    # Geographic information
    #
    # Support a few possible MongoDB field names so older
    # project records do not break.
    # --------------------------------------------------------

    state = (
        project.get("state")
        or project.get("project_state")
    )

    district = (
        project.get("district")
        or project.get("project_district")
        or project.get("city")
    )

    state = _clean_optional_string(
        state
    )

    district = _clean_optional_string(
        district
    )

    # --------------------------------------------------------
    # Parcel metrics
    # --------------------------------------------------------

    total_parcels = _safe_int(
        workflow_metrics.get(
            "total_parcels"
        )
    )

    pending_parcels = _safe_int(
        workflow_metrics.get(
            "pending_parcels"
        )
    )

    # Never allow pending count above known total.
    if (
        total_parcels > 0
        and pending_parcels > total_parcels
    ):
        pending_parcels = total_parcels

    # --------------------------------------------------------
    # Ownership metrics
    # --------------------------------------------------------

    ownership_disputes = _safe_int(
        workflow_metrics.get(
            "ownership_disputes"
        )
    )

    ownership_pending = _safe_int(
        workflow_metrics.get(
            "ownership_pending"
        )
    )

    # --------------------------------------------------------
    # Survey metrics
    # --------------------------------------------------------

    survey_pending = _safe_int(
        workflow_metrics.get(
            "survey_pending"
        )
    )

    # --------------------------------------------------------
    # Litigation metrics
    # --------------------------------------------------------

    active_litigation_cases = _safe_int(
        workflow_metrics.get(
            "active_litigation_cases"
        )
    )

    high_risk_litigation_cases = _safe_int(
        workflow_metrics.get(
            "high_risk_litigation_cases"
        )
    )

    # High-risk cases should not exceed all active cases
    # when an active-case count exists.
    if (
        active_litigation_cases > 0
        and high_risk_litigation_cases
        > active_litigation_cases
    ):
        high_risk_litigation_cases = (
            active_litigation_cases
        )

    # --------------------------------------------------------
    # Documents
    # --------------------------------------------------------

    missing_documents = _safe_int(
        workflow_metrics.get(
            "missing_documents"
        )
    )

    # --------------------------------------------------------
    # Compensation
    # --------------------------------------------------------

    compensation_pending = _safe_int(
        workflow_metrics.get(
            "compensation_pending"
        )
    )

    # --------------------------------------------------------
    # Approvals
    # --------------------------------------------------------

    pending_approvals = _safe_int(
        workflow_metrics.get(
            "pending_approvals"
        )
    )

    max_overdue_days = _safe_int(
        workflow_metrics.get(
            "max_overdue_days"
        )
    )

    # --------------------------------------------------------
    # Action Centre
    # --------------------------------------------------------

    open_actions = _safe_int(
        workflow_metrics.get(
            "open_actions"
        )
    )

    overdue_actions = _safe_int(
        workflow_metrics.get(
            "overdue_actions"
        )
    )

    high_priority_open_actions = _safe_int(
        workflow_metrics.get(
            "high_priority_open_actions"
        )
    )

    # Keep action sub-counts logically bounded.
    if (
        open_actions > 0
        and overdue_actions > open_actions
    ):
        overdue_actions = open_actions

    if (
        open_actions > 0
        and high_priority_open_actions
        > open_actions
    ):
        high_priority_open_actions = (
            open_actions
        )

    # --------------------------------------------------------
    # Completion
    # --------------------------------------------------------

    completion_percentage = _safe_float(
        workflow_metrics.get(
            "completion_percentage"
        )
    )

    completion_percentage = min(
        completion_percentage,
        100.0,
    )

    # --------------------------------------------------------
    # Final validated feature object
    # --------------------------------------------------------

    return RiskFeatureInput(
        project_id=project_id,
        project_name=project_name,

        state=state,
        district=district,

        total_parcels=total_parcels,
        pending_parcels=pending_parcels,

        ownership_disputes=ownership_disputes,
        ownership_pending=ownership_pending,

        survey_pending=survey_pending,

        active_litigation_cases=(
            active_litigation_cases
        ),

        high_risk_litigation_cases=(
            high_risk_litigation_cases
        ),

        missing_documents=(
            missing_documents
        ),

        compensation_pending=(
            compensation_pending
        ),

        pending_approvals=(
            pending_approvals
        ),

        max_overdue_days=(
            max_overdue_days
        ),

        open_actions=open_actions,

        overdue_actions=(
            overdue_actions
        ),

        high_priority_open_actions=(
            high_priority_open_actions
        ),

        completion_percentage=(
            completion_percentage
        ),
    )


# ============================================================
# ML feature vector
# ============================================================

def build_ml_feature_vector(
    features: RiskFeatureInput,
) -> dict[str, float]:
    """
    Convert validated LIVA workflow features into numerical
    values suitable for a future ML model.

    Geographic/project identifiers are intentionally excluded
    from this numerical vector for now.
    """

    total_parcels = max(
        features.total_parcels,
        1,
    )

    return {
        # ----------------------------------------------------
        # Parcel acquisition
        # ----------------------------------------------------

        "pending_parcel_ratio": round(
            features.pending_parcels
            / total_parcels,
            4,
        ),

        # ----------------------------------------------------
        # Ownership
        # ----------------------------------------------------

        "ownership_disputes": float(
            features.ownership_disputes
        ),

        "ownership_pending": float(
            features.ownership_pending
        ),

        # ----------------------------------------------------
        # Survey
        # ----------------------------------------------------

        "survey_pending": float(
            features.survey_pending
        ),

        # ----------------------------------------------------
        # Court / litigation
        # ----------------------------------------------------

        "active_litigation_cases": float(
            features.active_litigation_cases
        ),

        "high_risk_litigation_cases": float(
            features.high_risk_litigation_cases
        ),

        # ----------------------------------------------------
        # Documentation
        # ----------------------------------------------------

        "missing_documents": float(
            features.missing_documents
        ),

        # ----------------------------------------------------
        # Compensation
        # ----------------------------------------------------

        "compensation_pending": float(
            features.compensation_pending
        ),

        # ----------------------------------------------------
        # Approvals
        # ----------------------------------------------------

        "pending_approvals": float(
            features.pending_approvals
        ),

        "max_overdue_days": float(
            features.max_overdue_days
        ),

        # ----------------------------------------------------
        # Action Centre
        # ----------------------------------------------------

        "open_actions": float(
            features.open_actions
        ),

        "overdue_actions": float(
            features.overdue_actions
        ),

        "high_priority_open_actions": float(
            features.high_priority_open_actions
        ),

        # ----------------------------------------------------
        # Overall progress
        # ----------------------------------------------------

        "completion_percentage": float(
            features.completion_percentage
        ),
    }