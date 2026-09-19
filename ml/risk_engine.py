from ml.schemas import (
    RiskFeatureInput,
    RiskPredictionResponse,
    RiskLevel,
)

from ml.explainability import (
    build_risk_factors,
)

from ml.recommendations import (
    build_recommendations,
)

from ml.land_acquisition_reference import (
    get_land_acquisition_reference,
)


# ============================================================
# Utility functions
# ============================================================

def _cap(
    value: float,
    maximum: float,
) -> float:
    """
    Keep a risk contribution between 0 and its maximum.
    """

    return max(
        0.0,
        min(
            float(value),
            maximum,
        ),
    )


def _ratio(
    part: int,
    total: int,
) -> float:
    """
    Safely calculate a ratio between 0 and 1.
    """

    if total <= 0:
        return 0.0

    return max(
        0.0,
        min(
            part / total,
            1.0,
        ),
    )


# ============================================================
# Risk level classification
# ============================================================

def get_risk_level(
    score: float,
) -> RiskLevel:
    """
    Convert a 0-100 risk score into a LIVA risk category.

    Current thresholds are transparent engineering baseline
    thresholds and are not ML-derived.
    """

    if score < 25:
        return "LOW"

    if score < 50:
        return "MEDIUM"

    if score < 75:
        return "HIGH"

    return "CRITICAL"


# ============================================================
# Rule-based baseline score
# ============================================================

def calculate_baseline_score(
    features: RiskFeatureInput,
) -> float:
    """
    Calculate LIVA's transparent workflow risk index.

    This is currently the rule-based baseline.

    The government reference dataset is contextual evidence
    and does NOT directly alter this score.

    Maximum score = 100.
    """

    total_parcels = features.total_parcels

    # --------------------------------------------------------
    # 1. Pending parcels
    # Maximum: 15
    # --------------------------------------------------------

    pending_parcel_ratio = _ratio(
        features.pending_parcels,
        total_parcels,
    )

    parcel_score = (
        pending_parcel_ratio * 15
    )

    # --------------------------------------------------------
    # 2. Ownership issues
    # Maximum: 15
    # --------------------------------------------------------

    ownership_score = _cap(
        (
            features.ownership_disputes
            * 2.0
        )
        + (
            features.ownership_pending
            * 0.75
        ),
        15,
    )

    # --------------------------------------------------------
    # 3. Survey delays
    # Maximum: 10
    # --------------------------------------------------------

    if total_parcels > 0:

        survey_ratio = _ratio(
            features.survey_pending,
            total_parcels,
        )

        survey_score = (
            survey_ratio * 10
        )

    else:

        survey_score = _cap(
            features.survey_pending,
            10,
        )

    # --------------------------------------------------------
    # 4. Litigation
    # Maximum: 20
    # --------------------------------------------------------

    litigation_score = _cap(
        (
            features.active_litigation_cases
            * 2.5
        )
        + (
            features.high_risk_litigation_cases
            * 2.5
        ),
        20,
    )

    # --------------------------------------------------------
    # 5. Missing documentation
    # Maximum: 10
    # --------------------------------------------------------

    document_score = _cap(
        features.missing_documents
        * 1.5,
        10,
    )

    # --------------------------------------------------------
    # 6. Compensation delays
    # Maximum: 8
    # --------------------------------------------------------

    compensation_score = _cap(
        features.compensation_pending
        * 0.75,
        8,
    )

    # --------------------------------------------------------
    # 7. Pending approvals
    # Maximum: 10
    # --------------------------------------------------------

    approval_score = _cap(
        features.pending_approvals
        * 1.5,
        10,
    )

    # --------------------------------------------------------
    # 8. Maximum overdue duration
    # Maximum: 10
    #
    # Approximately 60 overdue days reaches maximum.
    # --------------------------------------------------------

    overdue_days_score = _cap(
        features.max_overdue_days
        / 6,
        10,
    )

    # --------------------------------------------------------
    # 9. Action Centre pressure
    # Maximum: 7
    # --------------------------------------------------------

    action_score = _cap(
        features.overdue_actions
        + (
            features.high_priority_open_actions
            * 0.5
        ),
        7,
    )

    # --------------------------------------------------------
    # 10. Low project completion
    # Maximum: 5
    # --------------------------------------------------------

    progress_score = 0.0

    if features.completion_percentage < 50:

        progress_score = _cap(
            (
                50
                - features.completion_percentage
            )
            / 10,
            5,
        )

    # --------------------------------------------------------
    # Final score
    # --------------------------------------------------------

    raw_score = (
        parcel_score
        + ownership_score
        + survey_score
        + litigation_score
        + document_score
        + compensation_score
        + approval_score
        + overdue_days_score
        + action_score
        + progress_score
    )

    return min(
        round(
            raw_score,
            2,
        ),
        100.0,
    )


# ============================================================
# Main Risk Engine
# ============================================================

def predict_delay_risk(
    features: RiskFeatureInput,
) -> RiskPredictionResponse:
    """
    Generate the current LIVA delay-risk result.

    Current prediction mode:
        RULE_BASED

    Government land-acquisition records are returned as
    contextual evidence.

    Future:
        ML
        HYBRID
    """

    # --------------------------------------------------------
    # Baseline score
    # --------------------------------------------------------

    risk_score = calculate_baseline_score(
        features
    )

    risk_level = get_risk_level(
        risk_score
    )

    # --------------------------------------------------------
    # Explainability
    # --------------------------------------------------------

    factors = build_risk_factors(
        features
    )

    # --------------------------------------------------------
    # Recommended actions
    # --------------------------------------------------------

    recommendations = (
        build_recommendations(
            features
        )
    )

    # --------------------------------------------------------
    # Government land-acquisition context
    #
    # If project state exists in reference dataset:
    #     STATE benchmark
    #
    # Otherwise:
    #     ALL_STATES benchmark
    # --------------------------------------------------------

    government_context = (
        get_land_acquisition_reference(
            features.state
        )
    )

    # --------------------------------------------------------
    # Final API response
    # --------------------------------------------------------

    return RiskPredictionResponse(
        project_id=features.project_id,
        project_name=features.project_name,

        risk_score=risk_score,
        risk_level=risk_level,

        prediction_source="RULE_BASED",

        # Rule-based score does not currently provide
        # statistical probability/confidence.
        confidence=None,

        factors=factors,

        recommendations=recommendations,

        # THIS was missing in your old file.
        government_context=government_context,

        model_version="liva-rule-baseline-v1",
    )