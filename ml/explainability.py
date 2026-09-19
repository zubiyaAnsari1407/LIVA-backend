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

    if features.pending_parcels > 0:

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

    if (
        features.ownership_disputes > 0
        or features.ownership_pending > 0
    ):

        impact = _cap(
            (features.ownership_disputes * 2.0)
            + (features.ownership_pending * 0.75),
            15,
        )

        factors.append(
            RiskFactor(
                code="OWNERSHIP_ISSUES",
                label="Ownership issues",
                observed_value=(
                    features.ownership_disputes
                    + features.ownership_pending
                ),
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"{features.ownership_disputes} ownership disputes "
                    f"and {features.ownership_pending} ownership reviews "
                    "are unresolved."
                ),
            )
        )

    # ========================================================
    # 3. Survey pending
    # ========================================================

    if features.survey_pending > 0:

        if total_parcels > 0:

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

    if (
        features.active_litigation_cases > 0
        or features.high_risk_litigation_cases > 0
    ):

        impact = _cap(
            (features.active_litigation_cases * 2.5)
            + (features.high_risk_litigation_cases * 2.5),
            20,
        )

        factors.append(
            RiskFactor(
                code="LITIGATION",
                label="Active litigation",
                observed_value=features.active_litigation_cases,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"{features.active_litigation_cases} active "
                    "litigation cases may affect acquisition progress."
                ),
            )
        )

    # ========================================================
    # 5. Missing documents
    # ========================================================

    if features.missing_documents > 0:

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

    if features.compensation_pending > 0:

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

    if features.pending_approvals > 0:

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

    if features.max_overdue_days > 0:

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

    if (
        features.overdue_actions > 0
        or features.high_priority_open_actions > 0
    ):

        impact = _cap(
            features.overdue_actions
            + (
                features.high_priority_open_actions
                * 0.5
            ),
            7,
        )

        factors.append(
            RiskFactor(
                code="ACTION_PRESSURE",
                label="Unresolved priority actions",
                observed_value=features.overdue_actions,
                impact_score=round(impact, 2),
                direction="INCREASES_RISK",
                reason=(
                    f"{features.overdue_actions} actions are overdue "
                    f"and {features.high_priority_open_actions} "
                    "high-priority actions remain open."
                ),
            )
        )

    # ========================================================
    # 10. Low project completion
    # ========================================================

    if features.completion_percentage < 50:

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