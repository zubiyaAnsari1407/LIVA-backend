import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pymongo.errors import PyMongoError

from database import db
from project_registry import require_project
from workflow_common import decorate, oid, unavailable

router = APIRouter(tags=["Workflow summaries and reports"])


TERMINAL_STATUSES = {
    "completed",
    "complete",
    "closed",
    "resolved",
    "approved",
    "verified",
    "done",
    "disposed",
}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("_", " ")


def _is_open(record: dict) -> bool:
    if any(record.get(key) is True for key in ("completed", "is_completed", "isComplete")):
        return False

    status = _record_status(record)

    if not status:
        return True

    return status not in TERMINAL_STATUSES


def _is_high_priority(record: dict) -> bool:
    return _text(record.get("priority")) in {
        "high",
        "critical",
        "urgent",
    }


def _is_high_risk_case(record: dict) -> bool:
    return _text(
        record.get("risk")
        or record.get("riskLevel")
        or record.get("risk_level")
        or record.get("severity")
        or record.get("priority")
    ) in {"high", "critical", "very high"}


def _has_risk_value(record: dict) -> bool:
    return any(
        record.get(key) is not None
        for key in ("risk", "riskLevel", "risk_level", "severity", "priority")
    )


def _record_status(record: dict) -> str:
    for key in (
        "status",
        "stage",
        "state",
        "review_status",
        "workflow_status",
        "case_status",
        "payment_status",
        "approval_status",
        "task_status",
    ):
        value = record.get(key)
        if value is not None and str(value).strip():
            return _text(value)
    return ""


def _breakdown(values: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        label = _text(value) or "unspecified"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _is_missing_document(record: dict) -> bool:
    status = _text(
        record.get("status")
        or record.get("state")
    )

    if status in {
        "missing",
        "not submitted",
        "not_submitted",
        "rejected",
        "pending",
    }:
        return True

    required = record.get(
        "required",
        record.get("isRequired", record.get("mandatory")),
    )
    uploaded = record.get(
        "uploaded",
        record.get("isUploaded", record.get("verified")),
    )

    return required is True and uploaded is False


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return 0.0

    return 0.0


def _project_refs(project_id: str) -> list[Any]:
    project = require_project(project_id)
    project_ref = str(project["_projectRef"])
    if project.get("_isLivaProject"):
        return [project_ref]
    project_oid = oid(project_ref, "project")
    return [project_ref, project_oid]


def _linked_query(project_id: str) -> dict:
    refs = _project_refs(project_id)
    return {
        "$or": [
            {"projectId": {"$in": refs}},
            {"project_id": {"$in": refs}},
        ]
    }


def _project_records(collection: str, project_id: str | None) -> list[dict]:
    if not project_id:
        return list(db[collection].find({}))
    return list(
        db[collection]
        .find(_linked_query(project_id))
    )


def _parcel_review_status(
    parcel: dict,
    review_key: str,
    fallback_key: str,
) -> str:
    review = parcel.get(review_key)

    if isinstance(review, dict):
        status = review.get("status")
        if status is not None:
            return _text(status)

    return _text(parcel.get(fallback_key))


def _is_review_pending(status: str) -> bool:
    if not status:
        return False

    return status not in TERMINAL_STATUSES


def _parcel_completed(parcel: dict) -> bool:
    status = _text(
        parcel.get("stage")
        or parcel.get("status")
    )

    return status in {
        "completed",
        "complete",
        "closed",
        "acquired",
    }


def _completion_value(project: dict) -> float | None:
    for key in (
        "completion_percentage",
        "completionPercentage",
        "progress_percentage",
        "progress",
        "physicalProgress",
        "physical_progress_pct",
    ):
        if project.get(key) is None:
            continue
        value = _number(project[key])
        if 0 < value <= 1:
            value *= 100
        return max(0.0, min(value, 100.0))
    return None


def _money_to_paise(record: dict, rupees_key: str, paise_key: str) -> int:
    if record.get(paise_key) is not None:
        return max(0, int(round(_number(record[paise_key]))))
    value = record.get(rupees_key)
    if value is None:
        return 0
    try:
        return max(0, int((Decimal(str(value).replace(",", "").strip()) * 100).quantize(Decimal("1"))))
    except (InvalidOperation, ValueError):
        return 0


def _payment_status(record: dict) -> str:
    raw = record.get("paymentStatus") or record.get("payment_status")
    if raw:
        return _text(raw)
    approved = _money_to_paise(record, "approved", "approvedPaise")
    paid = _money_to_paise(record, "disbursed", "disbursedPaise")
    if approved == 0:
        return "no amount recorded"
    if paid == 0:
        return "unpaid"
    if paid >= approved:
        return "paid"
    return "part paid"


def _overdue_days(record: dict, include_terminal: bool = False) -> int:
    if not include_terminal and not _is_open(record):
        return 0

    raw = (
        record.get("dueDate")
        or record.get("due_date")
        or record.get("targetDate")
        or record.get("target_date")
        or record.get("nextHearing")
        or record.get("next_hearing")
    )

    if not raw:
        return 0

    try:
        if isinstance(raw, datetime):
            due = raw
        else:
            value = str(raw).replace("Z", "+00:00")
            due = datetime.fromisoformat(value)

        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        seconds = (now - due).total_seconds()

        if seconds <= 0:
            return 0

        return int(seconds // 86400)
    except (TypeError, ValueError):
        return 0


def _summary(project_id: str | None) -> dict:
    project = None
    if project_id:
        project = require_project(project_id)

    parcels = _project_records("parcels", project_id)
    litigation = _project_records("litigation", project_id)
    compensation = _project_records("compensation", project_id)
    rehabilitation = _project_records("rehabilitation", project_id)
    actions = _project_records("actions", project_id)

    collection_names = set(db.list_collection_names())
    approvals_available = "approvals" in collection_names
    approvals = _project_records("approvals", project_id) if approvals_available else []
    legacy_documents_available = "documents" in collection_names
    legacy_documents = _project_records("documents", project_id) if legacy_documents_available else []

    total_parcels = len(parcels)
    completed_parcels = sum(1 for parcel in parcels if _parcel_completed(parcel))
    pending_parcels = max(total_parcels - completed_parcels, 0)

    ownership_statuses = [
        _parcel_review_status(parcel, "ownershipReview", "ownership")
        for parcel in parcels
    ]
    survey_statuses = [
        _parcel_review_status(parcel, "surveyReview", "")
        for parcel in parcels
    ]
    ownership_pending = sum(1 for status in ownership_statuses if _is_review_pending(status))
    ownership_disputes = sum(1 for status in ownership_statuses if "dispute" in status)
    survey_pending = sum(1 for status in survey_statuses if _is_review_pending(status))

    active_litigation = sum(1 for record in litigation if _is_open(record))
    risk_is_complete = not litigation or all(_has_risk_value(record) for record in litigation)
    high_risk_litigation = (
        sum(1 for record in litigation if _is_open(record) and _is_high_risk_case(record))
        if risk_is_complete else None
    )

    gridfs_query: dict = {"metadata.archived": {"$ne": True}}
    if project_id:
        gridfs_query["metadata.projectId"] = {"$in": _project_refs(project_id)}
    uploaded_files = list(db["document_files.files"].find(gridfs_query, {"metadata": 1}))
    uploaded_documents = len(uploaded_files)
    document_status_supported = legacy_documents_available and (
        not legacy_documents
        or any(
            any(key in record for key in ("status", "state", "required", "isRequired", "mandatory"))
            for record in legacy_documents
        )
    )
    missing_documents = (
        sum(1 for record in legacy_documents if _is_missing_document(record))
        if document_status_supported else None
    )
    document_categories = _breakdown([
        (item.get("metadata") or {}).get("category") for item in uploaded_files
    ])

    approved_paise = sum(_money_to_paise(record, "approved", "approvedPaise") for record in compensation)
    disbursed_paise = sum(_money_to_paise(record, "disbursed", "disbursedPaise") for record in compensation)
    compensation_statuses = [_payment_status(record) for record in compensation]
    compensation_pending = sum(
        1 for status in compensation_statuses
        if status in {"unpaid", "part paid", "partially paid", "pending", "open"}
    )

    approval_statuses = [_record_status(record) for record in approvals]
    pending_approvals = sum(1 for record in approvals if _is_open(record)) if approvals_available else None

    action_statuses = [_record_status(record) for record in actions]
    open_actions = sum(1 for record in actions if _is_open(record))
    overdue_actions = sum(1 for record in actions if _overdue_days(record) > 0)
    high_priority_open_actions = sum(
        1 for record in actions if _is_open(record) and _is_high_priority(record)
    )

    rehabilitation_statuses = [_record_status(record) for record in rehabilitation]
    rehabilitation_pending = sum(
        1 for record in rehabilitation if _text(record.get("status")) not in {"delivered", "closed"}
    )
    rehabilitation_completed = len(rehabilitation) - rehabilitation_pending
    overdue_rehabilitation = sum(
        1 for record in rehabilitation
        if _text(record.get("status")) not in {"delivered", "closed"}
        and _overdue_days(record, include_terminal=True) > 0
    )
    overdue_litigation = sum(
        1 for record in litigation if _is_open(record) and _overdue_days(record) > 0
    )
    overdue_days = [
        *(_overdue_days(record) for record in actions),
        *(_overdue_days(record) for record in litigation),
        *(
            _overdue_days(record, include_terminal=True)
            for record in rehabilitation
            if _text(record.get("status")) not in {"delivered", "closed"}
        ),
    ]
    overdue_total = overdue_actions + overdue_rehabilitation + overdue_litigation

    completion_percentage = _completion_value(project) if project else None
    if completion_percentage is None and not project_id:
        projects = list(db.projects.find({}))
        reported_progress = [value for value in (_completion_value(item) for item in projects) if value is not None]
        completion_percentage = round(sum(reported_progress) / len(reported_progress), 2) if reported_progress else None

    return {
        "generatedAt": datetime.now(timezone.utc),
        "includesDemo": True,
        # Existing response keys retained for the report and summary clients.
        "projects": (
            1 if project_id else
            db.projects.count_documents({}) + db["liva_projects"].count_documents({})
        ),
        "parcels": total_parcels,
        "documents": uploaded_documents,
        "cases": len(litigation),
        "compensationRecords": len(compensation),
        "rehabilitationRecords": len(rehabilitation),
        "openActions": open_actions,
        # Existing Digital Twin metric keys.
        "totalParcels": total_parcels,
        "pendingParcels": pending_parcels,
        "completedParcels": completed_parcels,
        "ownershipDisputes": ownership_disputes,
        "ownershipPending": ownership_pending,
        "surveyPending": survey_pending,
        "activeLitigationCases": active_litigation,
        "highRiskLitigationCases": high_risk_litigation,
        "missingDocuments": missing_documents,
        "compensationPending": compensation_pending,
        "pendingApprovals": pending_approvals,
        "overdueActions": overdue_actions,
        "highPriorityOpenActions": high_priority_open_actions,
        "maxOverdueDays": max(overdue_days, default=0),
        "completionPercentage": completion_percentage,
        "approvedPaise": int(approved_paise),
        "disbursedPaise": int(disbursed_paise),
        "balancePaise": int(max(approved_paise - disbursed_paise, 0)),
        "approvedAmount": round(approved_paise / 100, 2),
        "disbursedAmount": round(disbursed_paise / 100, 2),
        "balanceAmount": round(max(approved_paise - disbursed_paise, 0) / 100, 2),
        # Additive breakdowns and availability make unsupported metrics explicit.
        "parcelStageBreakdown": _breakdown([parcel.get("stage") for parcel in parcels]),
        "parcelStatusBreakdown": _breakdown([
            parcel.get("status") or parcel.get("stage") for parcel in parcels
        ]),
        "ownershipStatusBreakdown": _breakdown(ownership_statuses),
        "surveyStatusBreakdown": _breakdown(survey_statuses),
        "litigationStatusBreakdown": _breakdown([_record_status(record) for record in litigation]),
        "litigationCaseTypeBreakdown": (
            _breakdown([record.get("caseType") for record in litigation])
            if all(record.get("caseType") for record in litigation)
            else None
        ),
        "litigationRiskAvailable": risk_is_complete,
        "documentCategoryBreakdown": document_categories,
        "documentStatusBreakdown": _breakdown([_record_status(record) for record in legacy_documents]) if document_status_supported else None,
        "compensationStatusBreakdown": _breakdown(compensation_statuses),
        "approvalStatusBreakdown": _breakdown(approval_statuses) if approvals_available else None,
        "actionStatusBreakdown": _breakdown(action_statuses),
        "overdueLitigationCases": overdue_litigation,
        "overdueRehabilitationRecords": overdue_rehabilitation,
        "totalOverdueItems": overdue_total,
        "rehabilitationPending": rehabilitation_pending,
        "rehabilitationCompleted": rehabilitation_completed,
        "rehabilitationStatusBreakdown": _breakdown(rehabilitation_statuses),
        "metricAvailability": {
            "parcelStatus": bool(parcels),
            "litigationRisk": risk_is_complete,
            "litigationCaseType": all(record.get("caseType") for record in litigation),
            "documentStatus": document_status_supported,
            "approvalStatus": approvals_available,
            "completionPercentage": completion_percentage is not None,
            "compensationAmounts": any(
                record.get("approved") is not None or record.get("approvedPaise") is not None
                for record in compensation
            ),
        },
    }


@router.get("/api/workflow/summary")
def summary(projectId: str | None = None):
    try:
        return _summary(projectId)

    except PyMongoError:
        raise unavailable() from None


COLUMNS = {
    "compensation": [
        "id",
        "projectId",
        "project",
        "parcelId",
        "reference",
        "beneficiaryReference",
        "approved",
        "disbursed",
        "balance",
        "paymentStatus",
        "lastPaymentDate",
        "officer",
        "isDemo",
        "sourceName",
        "sourceUrl",
        "notes",
    ],
    "actions": [
        "id",
        "projectId",
        "project",
        "parcelId",
        "title",
        "officer",
        "priority",
        "status",
        "dueDate",
        "isDemo",
        "sourceName",
        "sourceUrl",
        "notes",
    ],
    "rehabilitation": [
        "id",
        "projectId",
        "project",
        "parcelId",
        "familyReference",
        "milestone",
        "status",
        "officer",
        "targetDate",
        "isDemo",
        "sourceName",
        "sourceUrl",
        "notes",
    ],
    "litigation": [
        "id",
        "projectId",
        "project",
        "parcelId",
        "reference",
        "title",
        "court",
        "status",
        "filedOn",
        "nextHearing",
        "isDemo",
        "sourceName",
        "sourceUrl",
        "notes",
    ],
}


def safe_cell(value):
    if value is None:
        return ""

    text = str(value)

    if (
        text.lstrip().startswith(("=", "+", "-", "@"))
        or text.startswith(("\t", "\r", "\n"))
    ):
        return "'" + text

    return text


@router.get("/api/workflow/reports/{kind}.csv")
def export_csv(
    kind: str,
    projectId: str | None = None,
):
    if kind not in COLUMNS:
        raise HTTPException(
            404,
            "Unknown report type.",
        )

    query = {}

    if projectId:
        query = _linked_query(projectId)

    try:
        if projectId:
            require_project(projectId)

        documents = list(
            db[kind]
            .find(query)
            .sort("_id", -1)
            .limit(10001)
        )

        if len(documents) > 10000:
            raise HTTPException(
                413,
                "Report exceeds 10,000 rows. Filter to one project.",
            )

        rows = decorate(documents)

    except PyMongoError:
        raise unavailable() from None

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    columns = COLUMNS[kind]

    writer.writerow(columns)

    for row in rows:
        writer.writerow(
            [safe_cell(row.get(column)) for column in columns]
        )

    return Response(
        content=(
            "\ufeff" + output.getvalue()
        ).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="liva-{kind}.csv"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
