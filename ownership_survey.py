import logging
from datetime import date, datetime, timezone
from typing import Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from database import db

logger = logging.getLogger("uvicorn.error")

router = APIRouter(
    prefix="/api/ownership-survey",
    tags=["Ownership & Survey"],
)


class ReviewFields(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    officer: str = Field(min_length=2, max_length=150)
    reviewDate: date
    remarks: str = Field(default="", max_length=5000)


class OwnershipReview(ReviewFields):
    status: Literal[
        "Pending verification",
        "Verified",
        "Disputed",
    ]


class SurveyReview(ReviewFields):
    status: Literal[
        "Requested",
        "Scheduled",
        "Field work completed",
        "Under review",
        "Approved",
    ]

    measuredAreaHa: float | None = Field(
        default=None,
        gt=0,
        allow_inf_nan=False,
    )


def parcel_object_id(parcel_id: str) -> ObjectId:
    if not ObjectId.is_valid(parcel_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid parcel ID.",
        )

    return ObjectId(parcel_id)


def serialize_record(document: dict) -> dict:
    return {
        "parcelId": str(document["_id"]),
        "projectId": str(document.get("projectId", "")),
        "surveyNumber": document.get("surveyNumber", ""),
        "village": document.get("village", ""),
        "district": document.get("district", ""),
        "areaHa": document.get("areaHa"),
        "ownership": document.get(
            "ownership", "Pending verification"
        ),
        "stage": document.get("stage", "Survey"),
        "isDemo": document.get("isDemo", True),
        "ownershipReview": document.get("ownershipReview"),
        "surveyReview": document.get("surveyReview"),
    }


@router.get("/{parcel_id}")
def get_reviews(parcel_id: str):
    oid = parcel_object_id(parcel_id)

    try:
        document = db.parcels.find_one({"_id": oid})
    except PyMongoError:
        logger.exception("Could not load parcel reviews")
        raise HTTPException(
            status_code=503,
            detail="Could not load reviews. Check the backend terminal.",
        ) from None

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Parcel not found.",
        )

    return serialize_record(document)


def save_review(
    parcel_id: str,
    field: str,
    payload: OwnershipReview | SurveyReview,
):
    oid = parcel_object_id(parcel_id)
    now = datetime.now(timezone.utc)

    review = payload.model_dump(mode="json")
    review["updatedAt"] = now

    changes = {
        field: review,
        "updatedAt": now,
    }

    # Keep the registry's ownership status in sync.
    if field == "ownershipReview":
        changes["ownership"] = review["status"]

    # Survey measurements remain review data.
    # They do not automatically replace the recorded parcel area
    # or change the project's acquisition stage.
    try:
        document = db.parcels.find_one_and_update(
            {"_id": oid},
            {"$set": changes},
            return_document=ReturnDocument.AFTER,
        )
    except PyMongoError:
        logger.exception("Could not save parcel review")
        raise HTTPException(
            status_code=503,
            detail="Review save failed. Check the backend terminal.",
        ) from None

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Parcel not found.",
        )

    return serialize_record(document)


@router.put("/{parcel_id}/ownership")
def save_ownership(
    parcel_id: str,
    payload: OwnershipReview,
):
    return save_review(
        parcel_id,
        "ownershipReview",
        payload,
    )


@router.put("/{parcel_id}/survey")
def save_survey(
    parcel_id: str,
    payload: SurveyReview,
):
    return save_review(
        parcel_id,
        "surveyReview",
        payload,
    )