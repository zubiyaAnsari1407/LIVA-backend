from ml.risk_engine import (
    predict_delay_risk,
)

from ml.schemas import (
    RiskFeatureInput,
)

from ml.simulation_schemas import (
    SimulationChangeSet,
    SimulationResponse,
)


def _normalise_simulated_features(
    current: RiskFeatureInput,
    changes: SimulationChangeSet,
) -> tuple[
    RiskFeatureInput,
    dict[str, int | float],
]:
    """
    Create a new feature state without modifying
    the original project features.
    """

    current_data = current.model_dump()

    requested_changes = (
        changes.model_dump(
            exclude_none=True
        )
    )

    applied_changes: dict[
        str,
        int | float,
    ] = {}

    for key, value in requested_changes.items():

        current_value = getattr(
            current,
            key,
        )

        if current_value != value:
            applied_changes[key] = value

        current_data[key] = value

    # --------------------------------------------------------
    # Logical constraints
    # --------------------------------------------------------

    total_parcels = int(
        current_data.get(
            "total_parcels",
            0,
        )
        or 0
    )

    if total_parcels > 0:
        current_data["pending_parcels"] = min(
            int(
                current_data.get(
                    "pending_parcels",
                    0,
                )
            ),
            total_parcels,
        )

    active_cases = int(
        current_data.get(
            "active_litigation_cases",
            0,
        )
        or 0
    )

    current_data[
        "high_risk_litigation_cases"
    ] = min(
        int(
            current_data.get(
                "high_risk_litigation_cases",
                0,
            )
            or 0
        ),
        active_cases,
    )

    open_actions = int(
        current_data.get(
            "open_actions",
            0,
        )
        or 0
    )

    if open_actions > 0:
        current_data["overdue_actions"] = min(
            int(
                current_data.get(
                    "overdue_actions",
                    0,
                )
                or 0
            ),
            open_actions,
        )

        current_data[
            "high_priority_open_actions"
        ] = min(
            int(
                current_data.get(
                    "high_priority_open_actions",
                    0,
                )
                or 0
            ),
            open_actions,
        )

    simulated_features = (
        RiskFeatureInput.model_validate(
            current_data
        )
    )

    return (
        simulated_features,
        applied_changes,
    )


def _build_summary(
    current_score: float,
    simulated_score: float,
    current_level: str,
    simulated_level: str,
) -> tuple[
    str,
    str,
    bool,
    float,
    float,
]:
    """
    Produce an understandable simulation result.
    """

    score_change = round(
        simulated_score
        - current_score,
        2,
    )

    risk_reduction = round(
        max(
            current_score
            - simulated_score,
            0,
        ),
        2,
    )

    if simulated_score < current_score:

        direction = "IMPROVED"
        improved = True

        if current_level != simulated_level:
            summary = (
                f"Simulated interventions reduce risk "
                f"from {current_score:.1f} "
                f"({current_level}) to "
                f"{simulated_score:.1f} "
                f"({simulated_level})."
            )
        else:
            summary = (
                f"Simulated interventions reduce the "
                f"risk score by {risk_reduction:.1f} "
                f"points while remaining in the "
                f"{simulated_level} category."
            )

    elif simulated_score > current_score:

        direction = "WORSENED"
        improved = False

        increase = round(
            simulated_score
            - current_score,
            2,
        )

        summary = (
            f"The simulated scenario increases risk "
            f"by {increase:.1f} points, from "
            f"{current_score:.1f} to "
            f"{simulated_score:.1f}."
        )

    else:

        direction = "UNCHANGED"
        improved = False

        summary = (
            "The selected interventions do not change "
            "the current risk score."
        )

    return (
        summary,
        direction,
        improved,
        score_change,
        risk_reduction,
    )


def simulate_intervention(
    current_features: RiskFeatureInput,
    changes: SimulationChangeSet,
) -> SimulationResponse:
    """
    Run LIVA Digital Twin / What-if analysis.

    The current project remains unchanged.
    A temporary simulated workflow state is created,
    scored and compared against the current state.
    """

    current_prediction = (
        predict_delay_risk(
            current_features
        )
    )

    (
        simulated_features,
        applied_changes,
    ) = _normalise_simulated_features(
        current=current_features,
        changes=changes,
    )

    simulated_prediction = (
        predict_delay_risk(
            simulated_features
        )
    )

    (
        summary,
        direction,
        improved,
        score_change,
        risk_reduction,
    ) = _build_summary(
        current_score=(
            current_prediction.risk_score
        ),
        simulated_score=(
            simulated_prediction.risk_score
        ),
        current_level=(
            current_prediction.risk_level
        ),
        simulated_level=(
            simulated_prediction.risk_level
        ),
    )

    return SimulationResponse(
        project_id=(
            current_features.project_id
        ),
        project_name=(
            current_features.project_name
        ),

        current_prediction=(
            current_prediction
        ),

        simulated_prediction=(
            simulated_prediction
        ),

        score_change=score_change,

        risk_reduction_points=(
            risk_reduction
        ),

        direction=direction,

        improved=improved,

        applied_changes=applied_changes,

        summary=summary,
    )