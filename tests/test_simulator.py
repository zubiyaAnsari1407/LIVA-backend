from ml.schemas import (
    RiskFeatureInput,
)

from ml.simulation_schemas import (
    SimulationChangeSet,
)

from ml.simulator import (
    simulate_intervention,
)


def test_simulation_reduces_risk():
    current = RiskFeatureInput(
        project_id="test-project",
        project_name="Test Project",

        total_parcels=100,
        pending_parcels=80,

        ownership_disputes=5,
        ownership_pending=10,

        survey_pending=40,

        active_litigation_cases=4,
        high_risk_litigation_cases=2,

        missing_documents=5,

        compensation_pending=8,

        pending_approvals=4,

        max_overdue_days=60,

        open_actions=10,
        overdue_actions=6,

        high_priority_open_actions=3,

        completion_percentage=20,
    )

    changes = SimulationChangeSet(
        pending_parcels=30,

        ownership_disputes=1,
        ownership_pending=2,

        survey_pending=10,

        active_litigation_cases=1,
        high_risk_litigation_cases=0,

        missing_documents=1,

        compensation_pending=2,

        pending_approvals=1,

        max_overdue_days=15,

        overdue_actions=1,

        high_priority_open_actions=1,

        completion_percentage=60,
    )

    result = simulate_intervention(
        current_features=current,
        changes=changes,
    )

    assert (
        result
        .simulated_prediction
        .risk_score
        <
        result
        .current_prediction
        .risk_score
    )

    assert result.improved is True

    assert result.direction == "IMPROVED"

    assert (
        result.risk_reduction_points
        > 0
    )