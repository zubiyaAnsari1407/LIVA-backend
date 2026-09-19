from fastapi import (
    APIRouter,
    HTTPException,
)

from pydantic import (
    BaseModel,
    Field,
)

from ml.mongo_feature_service import (
    build_project_risk_features,
)

from ml.model_loader import (
    load_model_metadata,
    load_risk_model,
    predict_schedule_delay,
)

from ml.risk_engine import (
    predict_delay_risk,
)

from ml.schemas import (
    RiskFeatureInput,
    RiskPredictionResponse,
)


router = APIRouter(
    prefix="/api/risk",
    tags=["Risk Intelligence"],
)


# =========================================================
# ML schemas
# =========================================================

class GeneralDelayMLInput(
    BaseModel
):
    original_cost_cr: float = Field(
        ge=0
    )

    expenditure_cr: float = Field(
        ge=0
    )

    expenditure_ratio: float = Field(
        ge=0
    )

    physical_progress_pct: float = Field(
        ge=0,
        le=100,
    )

    original_completion_year: int = Field(
        ge=1900,
        le=2200,
    )

    sanction_year: int = Field(
        ge=1900,
        le=2200,
    )

    sector: str

    line_ministry: str


# =========================================================
# Existing rule-based engine
# =========================================================

@router.get("/health")
def risk_health():
    return {
        "status": "ok",
        "module": (
            "LIVA Risk Intelligence"
        ),
        "rule_engine": (
            "liva-rule-baseline-v1"
        ),
        "ml_model_available": (
            True
        ),
    }


@router.post(
    "/predict",
    response_model=(
        RiskPredictionResponse
    ),
)
def predict_project_risk(
    payload: RiskFeatureInput,
):
    """
    Transparent land-acquisition workflow
    risk engine.
    """

    return predict_delay_risk(
        payload
    )


@router.get(
    "/project/{project_id}",
    response_model=(
        RiskPredictionResponse
    ),
)
def predict_saved_project_risk(
    project_id: str,
):
    """
    Risk prediction from saved LIVA
    MongoDB workflow records.
    """

    try:
        features = (
            build_project_risk_features(
                project_id
            )
        )

        return predict_delay_risk(
            features
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/project/{project_id}/features",
    response_model=RiskFeatureInput,
)
def get_saved_project_features(
    project_id: str,
):
    try:
        return (
            build_project_risk_features(
                project_id
            )
        )

    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


# =========================================================
# Government-data-trained ML engine
# =========================================================

@router.get(
    "/ml/health"
)
def ml_health():
    try:
        load_risk_model()

        metadata = (
            load_model_metadata()
        )

        return {
            "status": "ok",
            "model_loaded": True,
            "model_name": (
                metadata.get(
                    "model_name"
                )
            ),
            "training_rows": (
                metadata.get(
                    "training_rows"
                )
            ),
            "metrics": (
                metadata.get(
                    "metrics"
                )
            ),
            "model_scope": (
                "General infrastructure "
                "schedule-delay prediction"
            ),
        }

    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc


@router.post(
    "/ml/predict"
)
def predict_general_delay(
    payload: GeneralDelayMLInput,
):
    """
    Government-data-trained Random Forest
    schedule-delay prediction with SHAP XAI.

    Important:
    This is a general infrastructure delay
    signal trained on official MoSPI/PAIMANA
    project records.

    It does not replace the land-acquisition
    workflow risk engine.
    """

    try:
        return predict_schedule_delay(
            payload.model_dump()
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "ML prediction failed: "
                f"{exc}"
            ),
        ) from exc