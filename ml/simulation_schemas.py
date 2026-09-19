from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ml.schemas import (
    RiskFeatureInput,
    RiskPredictionResponse,
)


SimulationDirection = Literal[
    "IMPROVED",
    "UNCHANGED",
    "WORSENED",
]


class SimulationChangeSet(BaseModel):
    """
    Values represent the simulated future state
    of a project's acquisition workflow.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    pending_parcels: int | None = Field(
        default=None,
        ge=0,
    )

    ownership_disputes: int | None = Field(
        default=None,
        ge=0,
    )

    ownership_pending: int | None = Field(
        default=None,
        ge=0,
    )

    survey_pending: int | None = Field(
        default=None,
        ge=0,
    )

    active_litigation_cases: int | None = Field(
        default=None,
        ge=0,
    )

    high_risk_litigation_cases: int | None = Field(
        default=None,
        ge=0,
    )

    missing_documents: int | None = Field(
        default=None,
        ge=0,
    )

    compensation_pending: int | None = Field(
        default=None,
        ge=0,
    )

    pending_approvals: int | None = Field(
        default=None,
        ge=0,
    )

    max_overdue_days: int | None = Field(
        default=None,
        ge=0,
    )

    open_actions: int | None = Field(
        default=None,
        ge=0,
    )

    overdue_actions: int | None = Field(
        default=None,
        ge=0,
    )

    high_priority_open_actions: int | None = Field(
        default=None,
        ge=0,
    )

    completion_percentage: float | None = Field(
        default=None,
        ge=0,
        le=100,
    )


class SimulationRequest(BaseModel):
    current_features: RiskFeatureInput

    changes: SimulationChangeSet


class SimulationResponse(BaseModel):
    project_id: str

    project_name: str | None = None

    current_prediction: RiskPredictionResponse

    simulated_prediction: RiskPredictionResponse

    score_change: float

    risk_reduction_points: float

    direction: SimulationDirection

    improved: bool

    applied_changes: dict[
        str,
        int | float,
    ] = Field(
        default_factory=dict,
    )

    summary: str

    simulation_id: str | None = None

    saved: bool = False

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        )
    )


class SimulationHistoryItem(BaseModel):
    simulation_id: str

    project_id: str

    project_name: str | None = None

    current_risk_score: float

    simulated_risk_score: float

    current_risk_level: str

    simulated_risk_level: str

    score_change: float

    risk_reduction_points: float

    direction: SimulationDirection

    applied_changes: dict[
        str,
        int | float,
    ] = Field(
        default_factory=dict,
    )

    created_at: datetime