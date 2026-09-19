import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pymongo.errors import PyMongoError

from database import db
from workflow_common import decorate, oid, unavailable

router = APIRouter(tags=["Workflow summaries and reports"])


@router.get("/api/workflow/summary")
def summary(projectId: str | None = None):
    query = {}

    if projectId:
        query["projectId"] = str(oid(projectId, "project"))

    try:
        project_query = (
            {"_id": oid(projectId, "project")}
            if projectId
            else {}
        )

        if projectId and not db.projects.find_one(
            project_query,
            {"_id": 1},
        ):
            raise HTTPException(404, "Project not found.")

        totals = list(
            db.compensation.aggregate(
                [
                    {"$match": query},
                    {
                        "$group": {
                            "_id": None,
                            "approvedPaise": {
                                "$sum": "$approvedPaise"
                            },
                            "disbursedPaise": {
                                "$sum": "$disbursedPaise"
                            },
                        }
                    },
                ]
            )
        )

        amounts = (
            totals[0]
            if totals
            else {
                "approvedPaise": 0,
                "disbursedPaise": 0,
            }
        )

        documents_query = {
            "metadata.archived": {"$ne": True}
        }

        if projectId:
            documents_query["metadata.projectId"] = query["projectId"]

        return {
            "generatedAt": datetime.now(timezone.utc),
            "includesDemo": True,
            "projects": db.projects.count_documents(project_query),
            "parcels": db.parcels.count_documents(query),
            "documents": db["document_files.files"].count_documents(
                documents_query
            ),
            "cases": db.litigation.count_documents(query),
            "compensationRecords": db.compensation.count_documents(query),
            "rehabilitationRecords": db.rehabilitation.count_documents(
                query
            ),
            "openActions": db.actions.count_documents(
                {
                    **query,
                    "status": {"$ne": "Completed"},
                }
            ),
            "approvedPaise": amounts["approvedPaise"],
            "disbursedPaise": amounts["disbursedPaise"],
            "balancePaise": (
                amounts["approvedPaise"]
                - amounts["disbursedPaise"]
            ),
        }

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

    # Prevent text fields from becoming spreadsheet formulas.
    if (
        text.lstrip().startswith(("=", "+", "-", "@"))
        or text.startswith(("\t", "\r", "\n"))
    ):
        return "'" + text

    return text


@router.get("/api/workflow/reports/{kind}.csv")
def export_csv(kind: str, projectId: str | None = None):
    if kind not in COLUMNS:
        raise HTTPException(404, "Unknown report type.")

    query = {}

    if projectId:
        query["projectId"] = str(oid(projectId, "project"))

    try:
        if projectId and not db.projects.find_one(
            {"_id": oid(projectId, "project")},
            {"_id": 1},
        ):
            raise HTTPException(404, "Project not found.")

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
        content=("\ufeff" + output.getvalue()).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="liva-{kind}.csv"'
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )