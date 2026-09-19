from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Common types
# ============================================================

RiskLevel = Literal[
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]

PredictionSource = Literal[
    "RULE_BASED",
    "ML",
    "HYBRID",
]

RiskDirection = Literal[
    "INCREASES_RISK",
    "REDUCES_RISK",
]

ActionPriority = Literal[
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
]


# ============================================================
# Input features
# ============================================================

class RiskFeatureInput(BaseModel):
    """
    Normalized features used by the LIVA delay-risk engine.

    These values can be generated automatically from:
    - projects
    - parcels
    - ownership reviews
    - survey reviews
    - litigation
    - compensation
    - documents
    - approvals
    - action centre
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    # --------------------------------------------------------
    # Project identification
    # --------------------------------------------------------

    project_id: str = Field(
        ...,
        min_length=1,
        description="Unique project identifier",
    )

    project_name: str | None = Field(
        default=None,
        description="Human-readable project name",
    )

    state: str | None = Field(
        default=None,
        description="State associated with the project",
    )

    district: str | None = Field(
        default=None,
        description="District associated with the project",
    )

    # --------------------------------------------------------
    # Parcel / acquisition status
    # --------------------------------------------------------

    total_parcels: int = Field(
        default=0,
        ge=0,
    )

    pending_parcels: int = Field(
        default=0,
        ge=0,
    )

    # --------------------------------------------------------
    # Ownership
    # --------------------------------------------------------

    ownership_disputes: int = Field(
        default=0,
        ge=0,
        description="Number of unresolved ownership disputes",
    )

    ownership_pending: int = Field(
        default=0,
        ge=0,
        description="Ownership reviews still pending",
    )

    # --------------------------------------------------------
    # Survey
    # --------------------------------------------------------

    survey_pending: int = Field(
        default=0,
        ge=0,
        description="Parcels with incomplete survey work",
    )

    # --------------------------------------------------------
    # Litigation
    # --------------------------------------------------------

    active_litigation_cases: int = Field(
        default=0,
        ge=0,
        description="Active court / litigation cases",
    )

    high_risk_litigation_cases: int = Field(
        default=0,
        ge=0,
    )

    # --------------------------------------------------------
    # Documents
    # --------------------------------------------------------

    missing_documents: int = Field(
        default=0,
        ge=0,
        description="Mandatory documents currently missing",
    )

    # --------------------------------------------------------
    # Compensation
    # --------------------------------------------------------

    compensation_pending: int = Field(
        default=0,
        ge=0,
        description="Pending compensation records",
    )

    # --------------------------------------------------------
    # Approvals
    # --------------------------------------------------------

    pending_approvals: int = Field(
        default=0,
        ge=0,
    )

    max_overdue_days: int = Field(
        default=0,
        ge=0,
        description="Maximum number of days any workflow item is overdue",
    )

    # --------------------------------------------------------
    # Action centre
    # --------------------------------------------------------

    open_actions: int = Field(
        default=0,
        ge=0,
    )

    overdue_actions: int = Field(
        default=0,
        ge=0,
    )

    high_priority_open_actions: int = Field(
        default=0,
        ge=0,
    )

    # --------------------------------------------------------
    # Overall progress
    # --------------------------------------------------------

    completion_percentage: float = Field(
        default=0,
        ge=0,
        le=100,
    )


# ============================================================
# Risk explanation
# ============================================================

class RiskFactor(BaseModel):
    """
    One factor explaining why project risk increased or decreased.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    code: str = Field(
        ...,
        min_length=1,
    )

    label: str = Field(
        ...,
        min_length=1,
    )

    observed_value: str | int | float | bool | None = None

    impact_score: float = Field(
        default=0,
        ge=-100,
        le=100,
        description="Contribution of this factor to the risk prediction",
    )

    direction: RiskDirection = "INCREASES_RISK"

    reason: str = Field(
        ...,
        min_length=1,
    )


# ============================================================
# Recommended intervention
# ============================================================

class RecommendedAction(BaseModel):
    """
    Action suggested by LIVA to reduce acquisition-delay risk.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    code: str = Field(
        ...,
        min_length=1,
    )

    title: str = Field(
        ...,
        min_length=1,
    )

    description: str = Field(
        ...,
        min_length=1,
    )

    priority: ActionPriority = "MEDIUM"

    target_days: int | None = Field(
        default=None,
        ge=0,
    )

    related_factor: str | None = None


# ============================================================
# Government land acquisition reference
# ============================================================

class GovernmentLandReference(BaseModel):
    """
    Aggregated context from verified government
    land-acquisition records.

    This is contextual evidence and is not directly
    treated as a trained ML prediction.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    scope: Literal[
        "STATE",
        "ALL_STATES",
    ]

    state: str | None = None

    record_count: int = Field(
        ge=0,
    )

    average_pending_land_pct: float = Field(
        ge=0,
        le=100,
    )

    median_pending_land_pct: float = Field(
        ge=0,
        le=100,
    )

    high_backlog_projects: int = Field(
        ge=0,
    )

    zero_acquisition_projects: int = Field(
        ge=0,
    )

    source_files: list[str] = Field(
        default_factory=list,
    )

    note: str


# ============================================================
# Risk prediction response
# ============================================================

class RiskPredictionResponse(BaseModel):
    """
    Final response returned by the LIVA Risk Engine.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    project_id: str

    project_name: str | None = None

    risk_score: float = Field(
        ...,
        ge=0,
        le=100,
    )

    risk_level: RiskLevel

    prediction_source: PredictionSource = "RULE_BASED"

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
    )

    factors: list[RiskFactor] = Field(
        default_factory=list,
    )

    recommendations: list[RecommendedAction] = Field(
        default_factory=list,
    )

    government_context: GovernmentLandReference | None = None

    model_version: str = "liva-risk-v1"

    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ============================================================
# Project risk summary
# ============================================================

class ProjectRiskSummary(BaseModel):
    """
    Lightweight response useful for dashboard cards
    and project lists.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    project_id: str

    project_name: str | None = None

    risk_score: float = Field(
        ge=0,
        le=100,
    )

    risk_level: RiskLevel

    top_reason: str | None = None

    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )