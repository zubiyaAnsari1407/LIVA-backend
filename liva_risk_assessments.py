from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import db
from liva_projects import projects_collection
from ml.risk_engine import predict_delay_risk
from ml.schemas import RiskFeatureInput


router = APIRouter(
    prefix="/api/liva/risk-assessments",
    tags=["LIVA Risk Assessments"],
)
assessments_collection = db["liva_risk_assessments"]
grievances_collection = db["liva_grievances"]
_indexes_ready = False


INDEXES = (
    ("assessmentId", True),
    ("sourceGrievanceId", True),
    ("projectId", False),
    ("createdAt", False),
)


def extract_verified_grievance_counts(
    grievances: list[dict],
) -> dict[str, int]:
    """Count issue and action signals explicitly confirmed by an Officer."""
    verified = [
        grievance
        for grievance in grievances
        if grievance.get("status") == "PROBLEM_VERIFIED"
    ]
    reports = [item.get("officerReport") or {} for item in verified]
    ownership_disputes = 0
    for grievance in verified:
        report = grievance.get("officerReport") or {}
        confirmed = report.get("ownershipIssueConfirmed")
        ownership_disputes += int(
            confirmed if confirmed is not None
            else grievance.get("type") == "ownership" and "officerReport" not in grievance
        )
    return {
        "ownership_disputes": ownership_disputes,
        "survey_pending": sum(int(report.get("surveyPending") is True) for report in reports),
        "compensation_pending": sum(int(report.get("compensationPending") is True) for report in reports),
        "open_actions": sum(int(report.get("workStatus") in {"NOT_STARTED", "IN_PROGRESS", "ON_HOLD"}) for report in reports),
        "overdue_actions": sum(int(isinstance(report.get("overdueDays"), int) and report["overdueDays"] > 0) for report in reports),
        "max_overdue_days": max((report["overdueDays"] for report in reports if isinstance(report.get("overdueDays"), int)), default=0),
    }


def extract_verified_grievance_features(
    project: dict,
    grievances: list[dict],
) -> tuple[RiskFeatureInput, dict[str, bool]]:
    """Extract only risk inputs supported by verified LIVA grievance data."""
    verified = [
        grievance for grievance in grievances
        if grievance.get("status") == "PROBLEM_VERIFIED"
    ]
    grievance_counts = extract_verified_grievance_counts(verified)
    reports = [item.get("officerReport") or {} for item in verified]
    ownership_available = any(
        isinstance((item.get("officerReport") or {}).get("ownershipIssueConfirmed"), bool)
        or ("officerReport" not in item and item.get("type") == "ownership")
        for item in verified
    )

    # RiskFeatureInput keeps zero defaults for unmeasured modules to preserve
    # the existing engine contract. Availability distinguishes those defaults
    # from values actually extracted from LIVA records.
    availability = {
        "ownership_disputes": ownership_available,
        "survey_pending": any(report.get("surveyPending") is not None for report in reports),
        "compensation_pending": any(report.get("compensationPending") is not None for report in reports),
        "total_parcels": False,
        "pending_parcels": False,
        "ownership_pending": False,
        "active_litigation_cases": False,
        "high_risk_litigation_cases": False,
        "missing_documents": False,
        "pending_approvals": False,
        "max_overdue_days": any(isinstance(report.get("overdueDays"), int) for report in reports),
        "open_actions": any(report.get("workStatus") in {"NOT_STARTED", "IN_PROGRESS", "ON_HOLD", "RESOLVED"} for report in reports),
        "overdue_actions": any(isinstance(report.get("overdueDays"), int) for report in reports),
        "high_priority_open_actions": False,
        "completion_percentage": False,
    }
    features = RiskFeatureInput(
        project_id=project["projectId"],
        project_name=project.get("projectName"),
        state=project.get("state"),
        district=project.get("district"),
        available_features=[name for name, available in availability.items() if available],
        **grievance_counts,
    )
    return features, availability


def ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return

    try:
        for field, unique in INDEXES:
            assessments_collection.create_index(
                field,
                unique=unique,
                name=(
                    f"uq_liva_risk_{field.lower()}"
                    if unique
                    else f"ix_liva_risk_{field.lower()}"
                ),
            )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA risk assessment storage is unavailable.",
        ) from None

    _indexes_ready = True


def _serialize(record: dict) -> dict:
    record.pop("_id", None)
    return record


def create_or_get_assessment_for_verified_grievance(
    grievance: dict,
) -> dict | None:
    project_id = grievance.get("projectId")
    if not project_id:
        return None

    ensure_indexes()
    source_grievance_id = grievance["grievanceId"]

    try:
        existing_assessment = assessments_collection.find_one(
            {"sourceGrievanceId": source_grievance_id}
        )

        project = projects_collection.find_one({"projectId": project_id})
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The verified grievance references an unavailable LIVA project.",
            )

        verified_grievances = list(
            grievances_collection.find(
                {
                    "projectId": project_id,
                    "status": "PROBLEM_VERIFIED",
                }
            )
        )

        features, feature_availability = extract_verified_grievance_features(
            project,
            verified_grievances,
        )
        prediction = predict_delay_risk(features)

        numeric_suffix = "".join(
            character
            for character in source_grievance_id
            if character.isdigit()
        )
        assessment = {
            "assessmentId": (
                existing_assessment.get("assessmentId")
                if existing_assessment
                else f"LIVA-RISK-{numeric_suffix or source_grievance_id}"
            ),
            "projectId": project_id,
            "projectName": project.get("projectName"),
            "sourceGrievanceId": source_grievance_id,
            "sourceGrievanceIds": [
                item["grievanceId"] for item in verified_grievances
            ],
            "verifiedGrievanceCount": len(verified_grievances),
            "features": features.model_dump(mode="json"),
            "featureAvailability": feature_availability,
            "prediction": prediction.model_dump(mode="json"),
            "riskScore": prediction.risk_score,
            "riskLevel": prediction.risk_level,
            "createdAt": (
                existing_assessment.get("createdAt")
                if existing_assessment
                else datetime.now(timezone.utc)
            ),
            "updatedAt": datetime.now(timezone.utc),
        }

        if existing_assessment is not None:
            assessments_collection.update_one(
                {"sourceGrievanceId": source_grievance_id},
                {"$set": assessment},
            )
            return assessment

        try:
            assessments_collection.insert_one(assessment)
            return assessment
        except DuplicateKeyError:
            existing_assessment = assessments_collection.find_one(
                {"sourceGrievanceId": source_grievance_id}
            )
            if existing_assessment is not None:
                return _serialize(existing_assessment)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Risk assessment ID already exists.",
            ) from None
    except HTTPException:
        raise
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA risk assessment storage is unavailable.",
        ) from None


@router.get("/project/{project_id}")
def get_latest_project_risk_assessment(project_id: str):
    ensure_indexes()
    try:
        record = assessments_collection.find_one(
            {"projectId": project_id},
            sort=[("createdAt", -1)],
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA risk assessment storage is unavailable.",
        ) from None

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LIVA risk assessment not found.",
        )
    return record["prediction"]


@router.get("/project/{project_id}/features")
def get_latest_project_risk_features(project_id: str):
    ensure_indexes()
    try:
        record = assessments_collection.find_one(
            {"projectId": project_id},
            sort=[("createdAt", -1)],
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA risk assessment storage is unavailable.",
        ) from None

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="LIVA risk assessment not found.",
        )
    return record["features"]


@router.get("/project/{project_id}/history")
def list_project_risk_assessments(project_id: str):
    ensure_indexes()
    try:
        records = list(
            assessments_collection.find({"projectId": project_id})
            .sort("createdAt", -1)
            .limit(100)
        )
    except PyMongoError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LIVA risk assessment storage is unavailable.",
        ) from None
    return [_serialize(record) for record in records]
