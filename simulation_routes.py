from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from database import db

from ml.simulator import (
    simulate_intervention,
)

from ml.simulation_schemas import (
    SimulationHistoryItem,
    SimulationRequest,
    SimulationResponse,
)


router = APIRouter(
    prefix="/api/simulation",
    tags=["Digital Twin"],
)


# ============================================================
# Health
# ============================================================

@router.get("/health")
def simulation_health():
    return {
        "status": "ok",
        "module": "LIVA Digital Twin",
    }


# ============================================================
# Run simulation
# ============================================================

@router.post(
    "/run",
    response_model=SimulationResponse,
)
def run_simulation(
    payload: SimulationRequest,
):
    """
    Simulate acquisition workflow interventions.

    The real project data is NOT modified.
    """

    result = simulate_intervention(
        current_features=(
            payload.current_features
        ),
        changes=payload.changes,
    )

    # --------------------------------------------------------
    # Save audit record
    # --------------------------------------------------------

    try:
        collection = db[
            "simulation_runs"
        ]

        created_at = datetime.now(
            timezone.utc
        )

        document = {
            "project_id":
                result.project_id,

            "project_name":
                result.project_name,

            "current_risk_score":
                result
                .current_prediction
                .risk_score,

            "simulated_risk_score":
                result
                .simulated_prediction
                .risk_score,

            "current_risk_level":
                result
                .current_prediction
                .risk_level,

            "simulated_risk_level":
                result
                .simulated_prediction
                .risk_level,

            "score_change":
                result.score_change,

            "risk_reduction_points":
                result
                .risk_reduction_points,

            "direction":
                result.direction,

            "applied_changes":
                result.applied_changes,

            "summary":
                result.summary,

            "current_prediction":
                result
                .current_prediction
                .model_dump(
                    mode="json"
                ),

            "simulated_prediction":
                result
                .simulated_prediction
                .model_dump(
                    mode="json"
                ),

            "created_at":
                created_at,
        }

        insert_result = (
            collection.insert_one(
                document
            )
        )

        result = result.model_copy(
            update={
                "simulation_id":
                    str(
                        insert_result
                        .inserted_id
                    ),

                "saved":
                    True,

                "created_at":
                    created_at,
            }
        )

    except Exception as exc:
        print(
            "[LIVA] Simulation history "
            f"save warning: {exc}"
        )

    return result


# ============================================================
# Simulation history
# ============================================================

@router.get(
    "/history/{project_id}",
    response_model=list[
        SimulationHistoryItem
    ],
)
def get_simulation_history(
    project_id: str,
    limit: int = Query(
        default=10,
        ge=1,
        le=50,
    ),
):
    """
    Return previous What-if simulations
    for one project.
    """

    try:
        collection = db[
            "simulation_runs"
        ]

        cursor = (
            collection
            .find(
                {
                    "project_id":
                        project_id
                }
            )
            .sort(
                "created_at",
                -1,
            )
            .limit(
                limit
            )
        )

        records = []

        for document in cursor:

            records.append(
                SimulationHistoryItem(
                    simulation_id=str(
                        document["_id"]
                    ),

                    project_id=document[
                        "project_id"
                    ],

                    project_name=document.get(
                        "project_name"
                    ),

                    current_risk_score=float(
                        document.get(
                            "current_risk_score",
                            0,
                        )
                    ),

                    simulated_risk_score=float(
                        document.get(
                            "simulated_risk_score",
                            0,
                        )
                    ),

                    current_risk_level=str(
                        document.get(
                            "current_risk_level",
                            "LOW",
                        )
                    ),

                    simulated_risk_level=str(
                        document.get(
                            "simulated_risk_level",
                            "LOW",
                        )
                    ),

                    score_change=float(
                        document.get(
                            "score_change",
                            0,
                        )
                    ),

                    risk_reduction_points=float(
                        document.get(
                            "risk_reduction_points",
                            0,
                        )
                    ),

                    direction=document.get(
                        "direction",
                        "UNCHANGED",
                    ),

                    applied_changes=document.get(
                        "applied_changes",
                        {},
                    ),

                    created_at=document.get(
                        "created_at",
                        datetime.now(
                            timezone.utc
                        ),
                    ),
                )
            )

        return records

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to load simulation "
                f"history: {exc}"
            ),
        )