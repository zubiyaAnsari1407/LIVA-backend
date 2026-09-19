from ml.schemas import RiskFeatureInput, RecommendedAction


def build_recommendations(
    features: RiskFeatureInput,
) -> list[RecommendedAction]:
    """
    Generate actionable interventions from current workflow conditions.

    These are deterministic workflow recommendations.
    They are NOT predictions learned from training data.

    Later these recommendations can be enriched using:
    - government-data-trained ML predictions
    - SHAP explanations
    - Digital Twin / what-if simulation
    """

    recommendations: list[RecommendedAction] = []

    # ========================================================
    # Ownership
    # ========================================================

    if features.ownership_disputes > 0:
        recommendations.append(
            RecommendedAction(
                code="RESOLVE_OWNERSHIP_DISPUTES",
                title="Prioritize ownership dispute resolution",
                description=(
                    f"{features.ownership_disputes} ownership disputes "
                    "are unresolved. Schedule title verification and "
                    "stakeholder coordination for affected parcels."
                ),
                priority=(
                    "CRITICAL"
                    if features.ownership_disputes >= 5
                    else "HIGH"
                ),
                target_days=7,
                related_factor="OWNERSHIP_ISSUES",
            )
        )

    elif features.ownership_pending > 0:
        recommendations.append(
            RecommendedAction(
                code="COMPLETE_OWNERSHIP_REVIEW",
                title="Complete pending ownership verification",
                description=(
                    f"{features.ownership_pending} ownership reviews "
                    "are pending. Complete document and title verification."
                ),
                priority="HIGH",
                target_days=7,
                related_factor="OWNERSHIP_ISSUES",
            )
        )

    # ========================================================
    # Survey
    # ========================================================

    if features.survey_pending > 0:
        recommendations.append(
            RecommendedAction(
                code="SCHEDULE_PENDING_SURVEYS",
                title="Schedule pending land surveys",
                description=(
                    f"{features.survey_pending} parcel surveys remain "
                    "incomplete. Prioritize joint survey scheduling."
                ),
                priority=(
                    "HIGH"
                    if features.survey_pending >= 5
                    else "MEDIUM"
                ),
                target_days=7,
                related_factor="SURVEY_PENDING",
            )
        )

    # ========================================================
    # Litigation
    # ========================================================

    if features.active_litigation_cases > 0:
        recommendations.append(
            RecommendedAction(
                code="LEGAL_CASE_REVIEW",
                title="Prioritize litigation review",
                description=(
                    f"{features.active_litigation_cases} active legal "
                    "cases may affect acquisition progress. Review case "
                    "status, next hearing and required legal intervention."
                ),
                priority=(
                    "CRITICAL"
                    if features.high_risk_litigation_cases > 0
                    else "HIGH"
                ),
                target_days=5,
                related_factor="LITIGATION",
            )
        )

    # ========================================================
    # Missing documents
    # ========================================================

    if features.missing_documents > 0:
        recommendations.append(
            RecommendedAction(
                code="COLLECT_MISSING_DOCUMENTS",
                title="Resolve missing document requirements",
                description=(
                    f"{features.missing_documents} mandatory documents "
                    "are missing. Assign document collection and "
                    "verification immediately."
                ),
                priority=(
                    "HIGH"
                    if features.missing_documents >= 3
                    else "MEDIUM"
                ),
                target_days=5,
                related_factor="MISSING_DOCUMENTS",
            )
        )

    # ========================================================
    # Compensation
    # ========================================================

    if features.compensation_pending > 0:
        recommendations.append(
            RecommendedAction(
                code="PROCESS_COMPENSATION",
                title="Accelerate pending compensation",
                description=(
                    f"{features.compensation_pending} compensation "
                    "records remain pending. Review award/payment status "
                    "and resolve blocking requirements."
                ),
                priority=(
                    "HIGH"
                    if features.compensation_pending >= 5
                    else "MEDIUM"
                ),
                target_days=10,
                related_factor="COMPENSATION_PENDING",
            )
        )

    # ========================================================
    # Approvals
    # ========================================================

    if features.pending_approvals > 0:
        recommendations.append(
            RecommendedAction(
                code="ESCALATE_APPROVALS",
                title="Escalate pending approvals",
                description=(
                    f"{features.pending_approvals} approvals are pending. "
                    "Escalate overdue approvals to the responsible authority."
                ),
                priority=(
                    "HIGH"
                    if features.max_overdue_days >= 15
                    else "MEDIUM"
                ),
                target_days=5,
                related_factor="PENDING_APPROVALS",
            )
        )

    # ========================================================
    # Overdue workflow
    # ========================================================

    if features.max_overdue_days >= 15:
        recommendations.append(
            RecommendedAction(
                code="OVERDUE_WORKFLOW_ESCALATION",
                title="Escalate overdue workflow items",
                description=(
                    f"The longest workflow delay is "
                    f"{features.max_overdue_days} days. "
                    "Identify the responsible stage and initiate escalation."
                ),
                priority=(
                    "CRITICAL"
                    if features.max_overdue_days >= 60
                    else "HIGH"
                ),
                target_days=3,
                related_factor="OVERDUE_DURATION",
            )
        )

    # ========================================================
    # Action Center
    # ========================================================

    if (
        features.overdue_actions > 0
        or features.high_priority_open_actions > 0
    ):
        recommendations.append(
            RecommendedAction(
                code="CLEAR_ACTION_BACKLOG",
                title="Clear critical Action Center backlog",
                description=(
                    f"{features.overdue_actions} actions are overdue and "
                    f"{features.high_priority_open_actions} high-priority "
                    "actions remain open."
                ),
                priority=(
                    "CRITICAL"
                    if features.overdue_actions >= 5
                    else "HIGH"
                ),
                target_days=3,
                related_factor="ACTION_PRESSURE",
            )
        )

    # ========================================================
    # Pending parcels
    # ========================================================

    if (
        features.total_parcels > 0
        and features.pending_parcels > 0
    ):
        pending_ratio = (
            features.pending_parcels
            / features.total_parcels
        )

        if pending_ratio >= 0.25:
            recommendations.append(
                RecommendedAction(
                    code="PARCEL_BACKLOG_REVIEW",
                    title="Review high parcel acquisition backlog",
                    description=(
                        f"{features.pending_parcels} of "
                        f"{features.total_parcels} parcels are pending. "
                        "Identify the dominant blocking stages."
                    ),
                    priority=(
                        "HIGH"
                        if pending_ratio >= 0.5
                        else "MEDIUM"
                    ),
                    target_days=7,
                    related_factor="PENDING_PARCELS",
                )
            )

    # ========================================================
    # Priority sorting
    # ========================================================

    priority_order = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }

    recommendations.sort(
        key=lambda action: priority_order[action.priority],
        reverse=True,
    )

    return recommendations