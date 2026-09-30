import logging
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo import ReturnDocument

from database import db
from project_registry import project_refs, require_project

logger = logging.getLogger("uvicorn.error")


def oid(value, label="record"):
    if not ObjectId.is_valid(value):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {label} ID.",
        )

    return ObjectId(value)


def unavailable():
    logger.exception("Workflow database operation failed")

    return HTTPException(
        status_code=503,
        detail="Database operation failed. Check the backend terminal.",
    )


def linked_document(payload, require_source=True):
    project = require_project(payload.projectId)
    project_id = project["_projectRef"]

    if not payload.isDemo and project.get("isDemo") is True:
        raise HTTPException(
            422,
            "Non-demo records cannot link to a demo project.",
        )

    if require_source and not payload.isDemo and not project.get("_isLivaProject") and (
        not payload.sourceName or payload.sourceUrl is None
    ):
        raise HTTPException(
            422,
            "Source-backed records require a source name and URL.",
        )

    document = payload.model_dump(mode="json")
    document["projectId"] = str(project_id)
    document["parcelId"] = None

    if payload.parcelId:
        parcel_id = oid(payload.parcelId, "parcel")
        parcel = db.parcels.find_one({"_id": parcel_id})

        if parcel is None:
            raise HTTPException(404, "Parcel not found.")

        if str(parcel.get("projectId")) != str(project_id):
            raise HTTPException(
                422,
                "Parcel belongs to another project.",
            )

        if not payload.isDemo and parcel.get("isDemo") is True:
            raise HTTPException(
                422,
                "Non-demo records cannot link to a demo parcel.",
            )

        document["parcelId"] = str(parcel_id)

    return document


def decorate(documents):
    project_ids = {
        str(document.get("projectId", ""))
        for document in documents
    }

    projects = project_refs(project_ids)

    results = []

    for document in documents:
        item = {
            key: value
            for key, value in document.items()
            if key != "_id"
        }

        item["id"] = str(document["_id"])
        item["project"] = projects.get(
            str(item.get("projectId")),
            "Project unavailable",
        )

        if "approvedPaise" in item:
            approved = item["approvedPaise"]
            paid = item["disbursedPaise"]
            balance = approved - paid

            item["approved"] = (
                f"{approved // 100}.{approved % 100:02d}"
            )
            item["disbursed"] = (
                f"{paid // 100}.{paid % 100:02d}"
            )
            item["balance"] = (
                f"{balance // 100}.{balance % 100:02d}"
            )

            if approved == 0:
                item["paymentStatus"] = "No amount recorded"
            elif paid == 0:
                item["paymentStatus"] = "Unpaid"
            elif paid == approved:
                item["paymentStatus"] = "Paid"
            else:
                item["paymentStatus"] = "Part paid"

        results.append(item)

    return results


def list_records(
    collection,
    project_id=None,
    skip=0,
    limit=100,
):
    query = {}

    if project_id:
        project = require_project(project_id)
        query["projectId"] = project["_projectRef"]

    documents = list(
        db[collection]
        .find(query)
        .sort("_id", -1)
        .skip(skip)
        .limit(limit)
    )

    return {
        "items": decorate(documents),
        "count": len(documents),
        "total": db[collection].count_documents(query),
        "skip": skip,
        "limit": limit,
    }


def save_record(collection, payload, record_id=None):
    record_oid = oid(record_id) if record_id else None

    if record_oid:
        existing = db[collection].find_one(
            {"_id": record_oid},
            {"_id": 1},
        )

        if existing is None:
            raise HTTPException(404, "Record not found.")

    document = linked_document(
        payload,
        require_source=collection not in {"actions", "compensation", "rehabilitation"},
    )

    if collection == "compensation":
        document.pop("approved")
        document.pop("disbursed")

        # Integer paise avoids floating-point rounding.
        document["approvedPaise"] = int(payload.approved * 100)
        document["disbursedPaise"] = int(payload.disbursed * 100)

    now = datetime.now(timezone.utc)
    document["updatedAt"] = now

    if record_oid:
        document = db[collection].find_one_and_update(
            {"_id": record_oid},
            {"$set": document},
            return_document=ReturnDocument.AFTER,
        )

        if document is None:
            raise HTTPException(404, "Record not found.")
    else:
        document["createdAt"] = now
        result = db[collection].insert_one(document)
        document["_id"] = result.inserted_id

    return decorate([document])[0]
