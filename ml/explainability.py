from ml.schemas import RiskFeatureInput, RiskFactor


def _cap(value: float, maximum: float) -> float:
    return max(0.0, min(float(value), maximum))


def _ratio(part: int, total: int) -> float:
    if total <= 0:
        return 0.0

    return max(0.0, min(part / total, 1.0))


def build_risk_factors(
    features: RiskFeatureInput,
) -> list[RiskFactor]:
    """
    Build human-readable explanations for the current
    LIVA rule-based risk score.

    These explanations correspond to the same factors
    used by the baseline risk engine.

    Later, when the real ML model is trained using
    verified government data, SHAP explanations will
    be added/replaced here.
    """

    factors: list[RiskFactor] = []

    total_parcels = features.total_parcels

    # ========================================================
    # 1. Pending parcels
    # ========================================================

    if features.has_feature("pending_parcels") and features.has_feature("total_parcels") and features.pending_parcels > 0:

        pending_ratio = _ratio(
            features.pending_parcels,
            total_parcels,
        )

        impact = round(
            pending_ratio * 15,
            2,
        )

        factors.append(
            RiskFactor(
                code="PENDING_PARCELS",
                label="Pending land parcels",
                observed_value=features.pending_parcels,
                impact_score=impact,
                direction="INCREASES_RISK",
                reason=(
                    f"{features.pending_parcels} parcels are still "
                    "pending in the acquisition workflow."
                ),
            )
        )

    # ========================================================
    # 2. Ownership disputes
    # ========================================================

    ownership_disputes_available = features.has_feature("ownership_disputes")
    ownership_pending_available = features.has_feature("ownership_pending")
    if (
        (ownership_disputes_available and features.ownership_disputes > 0)
        or (ownership_pending_available and features.ownership_pending > 0)
    ):
        observed_disputes = features.ownership_disputes if ownership_disputes_available else 0
        observed_pending = features.ownership_pending if ownership_pending_available else 0

        impact = _cap(
            (observed_disputes * 2.0)
            + (observed_pending * 0.75),
            15,
        )

        factors.append(
            RiskFactor(
                code="OWNERSHIP_ISSUES",
                label="Ownership issues",
                observed_value=(
                    observed_disputes
                    + observed_pending
                ),
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    (
                        f"{observed_disputes} ownership disputes are unresolved."
                        if ownership_disputes_available and not ownership_pending_available
                        else f"{observed_disputes} ownership disputes and {observed_pending} ownership reviews are unresolved."
                        if ownership_disputes_available
                        else f"{observed_pending} ownership reviews are unresolved."
                    )
                ),
            )
        )

    # ========================================================
    # 3. Survey pending
    # ========================================================

    if features.has_feature("survey_pending") and features.survey_pending > 0:

        if total_parcels > 0 and features.has_feature("total_parcels"):

            survey_ratio = _ratio(
                features.survey_pending,
                total_parcels,
            )

            impact = survey_ratio * 10

        else:

            impact = _cap(
                features.survey_pending,
                10,
            )

        factors.append(
            RiskFactor(
                code="SURVEY_PENDING",
                label="Survey work pending",
                observed_value=features.survey_pending,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"{features.survey_pending} parcel surveys "
                    "are still incomplete."
                ),
            )
        )

    # ========================================================
    # 4. Litigation
    # ========================================================

    active_cases_available = features.has_feature("active_litigation_cases")
    high_risk_cases_available = features.has_feature("high_risk_litigation_cases")
    if (
        (active_cases_available and features.active_litigation_cases > 0)
        or (high_risk_cases_available and features.high_risk_litigation_cases > 0)
    ):
        active_cases = features.active_litigation_cases if active_cases_available else 0
        high_risk_cases = features.high_risk_litigation_cases if high_risk_cases_available else 0

        impact = _cap(
            (active_cases * 2.5)
            + (high_risk_cases * 2.5),
            20,
        )

        factors.append(
            RiskFactor(
                code="LITIGATION",
                label="Active litigation",
                observed_value=active_cases,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"{active_cases} active "
                    "litigation cases may affect acquisition progress."
                ),
            )
        )

    # ========================================================
    # 5. Missing documents
    # ========================================================

    if features.has_feature("missing_documents") and features.missing_documents > 0:

        impact = _cap(
            features.missing_documents * 1.5,
            10,
        )

        factors.append(
            RiskFactor(
                code="MISSING_DOCUMENTS",
                label="Missing mandatory documents",
                observed_value=features.missing_documents,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"{features.missing_documents} required documents "
                    "are currently missing."
                ),
            )
        )

    # ========================================================
    # 6. Compensation pending
    # ========================================================

    if features.has_feature("compensation_pending") and features.compensation_pending > 0:

        impact = _cap(
            features.compensation_pending * 0.75,
            8,
        )

        factors.append(
            RiskFactor(
                code="COMPENSATION_PENDING",
                label="Compensation pending",
                observed_value=features.compensation_pending,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"{features.compensation_pending} compensation "
                    "records are still pending."
                ),
            )
        )

    # ========================================================
    # 7. Approvals pending
    # ========================================================

    if features.has_feature("pending_approvals") and features.pending_approvals > 0:

        impact = _cap(
            features.pending_approvals * 1.5,
            10,
        )

        factors.append(
            RiskFactor(
                code="PENDING_APPROVALS",
                label="Approvals pending",
                observed_value=features.pending_approvals,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"{features.pending_approvals} workflow approvals "
                    "are currently pending."
                ),
            )
        )

    # ========================================================
    # 8. Overdue duration
    # ========================================================

    if features.has_feature("max_overdue_days") and features.max_overdue_days > 0:

        impact = _cap(
            features.max_overdue_days / 6,
            10,
        )

        factors.append(
            RiskFactor(
                code="OVERDUE_DURATION",
                label="Overdue workflow duration",
                observed_value=features.max_overdue_days,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"The longest pending workflow item is "
                    f"{features.max_overdue_days} days overdue."
                ),
            )
        )

    # ========================================================
    # 9. Action centre pressure
    # ========================================================

    overdue_actions_available = features.has_feature("overdue_actions")
    high_priority_actions_available = features.has_feature("high_priority_open_actions")
    if (
        (overdue_actions_available and features.overdue_actions > 0)
        or (high_priority_actions_available and features.high_priority_open_actions > 0)
    ):
        overdue_actions = features.overdue_actions if overdue_actions_available else 0
        high_priority_actions = features.high_priority_open_actions if high_priority_actions_available else 0

        impact = _cap(
            overdue_actions
            + (
                high_priority_actions
                * 0.5
            ),
            7,
        )

        factors.append(
            RiskFactor(
                code="ACTION_PRESSURE",
                label="Unresolved priority actions",
                observed_value=overdue_actions,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    (
                        f"{overdue_actions} actions are overdue and {high_priority_actions} high-priority actions remain open."
                        if overdue_actions_available and high_priority_actions_available
                        else f"{overdue_actions} actions are overdue."
                        if overdue_actions_available
                        else f"{high_priority_actions} high-priority actions remain open."
                    )
                ),
            )
        )

    # ========================================================
    # 10. Low project completion
    # ========================================================

    if features.has_feature("completion_percentage") and features.completion_percentage < 50:

        impact = _cap(
            (
                50
                - features.completion_percentage
            )
            / 10,
            5,
        )

        factors.append(
            RiskFactor(
                code="LOW_COMPLETION",
                label="Low project completion",
                observed_value=features.completion_percentage,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"Overall acquisition workflow completion is "
                    f"{features.completion_percentage:.1f}%."
                ),
            )
        )

    # ========================================================
    # Sort strongest reasons first
    # ========================================================

    factors.sort(
        key=lambda factor: factor.impact_score,
        reverse=True,
    )

    return factors
