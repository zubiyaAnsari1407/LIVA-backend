from datetime import date, datetime, timezone
import os
from typing import Literal
from urllib.parse import unquote, urlparse

from bson import ObjectId
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)
from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

import cloudinary
import cloudinary.uploader

from database import db


router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"],
)


Stage = Literal[
    "Not specified",
    "Survey",
    "Verification",
    "Award",
    "Compensation",
    "Possession",
]


MAX_PROJECT_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_PROJECT_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}


def configure_cloudinary() -> None:
    cloudinary_url = os.getenv("CLOUDINARY_URL", "").strip()

    if cloudinary_url:
        parsed = urlparse(cloudinary_url)
        if (
            parsed.scheme != "cloudinary"
            or not parsed.hostname
            or not parsed.username
            or not parsed.password
        ):
            raise HTTPException(
                status_code=503,
                detail="CLOUDINARY_URL is invalid.",
            )

        cloudinary.config(
            cloud_name=parsed.hostname,
            api_key=unquote(parsed.username),
            api_secret=unquote(parsed.password),
            secure=True,
        )
        return

    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME", "").strip()
    api_key = os.getenv("CLOUDINARY_API_KEY", "").strip()
    api_secret = os.getenv("CLOUDINARY_API_SECRET", "").strip()

    if not cloud_name or not api_key or not api_secret:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cloudinary is not configured. Add CLOUDINARY_URL or "
                "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY and "
                "CLOUDINARY_API_SECRET to backend .env."
            ),
        )

    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )


def destroy_cloudinary_image(public_id: str | None) -> bool:
    if not public_id:
        return False

    try:
        configure_cloudinary()
        result = cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            invalidate=True,
        )
        return result.get("result") in {"ok", "not found"}
    except Exception as exc:
        print(
            f"CLOUDINARY DELETE WARNING: {type(exc).__name__}: {exc}",
            flush=True,
        )
        return False


class ImageDeleteRequest(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    publicId: str = Field(
        min_length=1,
        max_length=500,
    )


class ProjectFields(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    name: str = Field(
        min_length=3,
        max_length=500,
    )

    state: str = Field(
        min_length=2,
        max_length=100,
    )

    district: str = Field(
        min_length=2,
        max_length=100,
    )

    stage: Stage = "Survey"

    progress: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
    )

    description: str = Field(
        default="",
        max_length=3000,
    )

    image: str | None = Field(
        default=None,
        max_length=1000,
    )

    imagePublicId: str | None = Field(
        default=None,
        max_length=500,
    )

    # ML project context
    sector: str | None = Field(
        default=None,
        max_length=150,
    )

    line_ministry: str | None = Field(
        default=None,
        max_length=200,
    )

    original_cost_cr: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    expenditure_cr: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    physical_progress_pct: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
    )

    original_completion_year: int | None = Field(
        default=None,
        ge=1900,
        le=2200,
    )

    sanction_year: int | None = Field(
        default=None,
        ge=1900,
        le=2200,
    )

    # GIS location
    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        allow_inf_nan=False,
    )

    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        allow_inf_nan=False,
    )

    locationDisplayName: str | None = Field(
        default=None,
        max_length=500,
    )

    locationSource: str | None = Field(
        default=None,
        max_length=150,
    )

    # Data provenance
    isDemo: bool = True

    sourceName: str | None = Field(
        default=None,
        max_length=200,
    )

    sourceUrl: HttpUrl | None = None

    sourceRecordId: str | None = Field(
        default=None,
        max_length=200,
    )

    sourceDate: date | None = None

    @model_validator(mode="after")
    def validate_project(self):
        if not self.isDemo and (
            not self.sourceName
            or self.sourceUrl is None
        ):
            raise ValueError(
                "Non-demo records require a source name and source URL."
            )

        if (
            self.latitude is None
        ) != (
            self.longitude is None
        ):
            raise ValueError(
                "Latitude and longitude must be supplied together."
            )

        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    name: str | None = Field(
        default=None,
        min_length=3,
        max_length=500,
    )

    state: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    district: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    stage: Stage | None = None

    progress: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
    )

    description: str | None = Field(
        default=None,
        max_length=3000,
    )

    image: str | None = Field(
        default=None,
        max_length=1000,
    )

    imagePublicId: str | None = Field(
        default=None,
        max_length=500,
    )

    sector: str | None = Field(
        default=None,
        max_length=150,
    )

    line_ministry: str | None = Field(
        default=None,
        max_length=200,
    )

    original_cost_cr: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    expenditure_cr: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
    )

    physical_progress_pct: float | None = Field(
        default=None,
        ge=0,
        le=100,
        allow_inf_nan=False,
    )

    original_completion_year: int | None = Field(
        default=None,
        ge=1900,
        le=2200,
    )

    sanction_year: int | None = Field(
        default=None,
        ge=1900,
        le=2200,
    )

    # GIS
    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        allow_inf_nan=False,
    )

    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        allow_inf_nan=False,
    )

    locationDisplayName: str | None = Field(
        default=None,
        max_length=500,
    )

    locationSource: str | None = Field(
        default=None,
        max_length=150,
    )

    # Provenance
    sourceName: str | None = Field(
        default=None,
        max_length=200,
    )

    sourceUrl: HttpUrl | None = None

    sourceRecordId: str | None = Field(
        default=None,
        max_length=200,
    )

    sourceDate: date | None = None

    @model_validator(mode="after")
    def reject_null_required_fields(self):
        required_fields = [
            "name",
            "state",
            "district",
            "stage",
            "description",
        ]

        for field in required_fields:
            if (
                field in self.model_fields_set
                and getattr(self, field) is None
            ):
                raise ValueError(
                    f"{field} cannot be null."
                )

        return self


def serialize_project(
    document: dict,
) -> dict:
    return {
        "id": str(document["_id"]),
        "name": document.get(
            "name",
            "",
        ),
        "state": document.get(
            "state",
            "",
        ),
        "district": document.get(
            "district",
            "",
        ),
        "stage": document.get(
            "stage",
            "Survey",
        ),
        "progress": document.get(
            "progress"
        ),
        "description": document.get(
            "description",
            "",
        ),
        "image": document.get(
            "image"
        ),
        "imagePublicId": document.get(
            "imagePublicId"
        ),

        "sector": document.get(
            "sector"
        ),
        "line_ministry": document.get(
            "line_ministry"
        ),
        "original_cost_cr": document.get(
            "original_cost_cr"
        ),
        "expenditure_cr": document.get(
            "expenditure_cr"
        ),
        "physical_progress_pct": document.get(
            "physical_progress_pct"
        ),
        "original_completion_year": document.get(
            "original_completion_year"
        ),
        "sanction_year": document.get(
            "sanction_year"
        ),

        # GIS
        "latitude": document.get(
            "latitude"
        ),
        "longitude": document.get(
            "longitude"
        ),
        "locationDisplayName": document.get(
            "locationDisplayName"
        ),
        "locationSource": document.get(
            "locationSource"
        ),
        "locationUpdatedAt": document.get(
            "locationUpdatedAt"
        ),

        # Provenance
        "isDemo": document.get(
            "isDemo",
            True,
        ),
        "sourceName": document.get(
            "sourceName"
        ),
        "sourceUrl": document.get(
            "sourceUrl"
        ),
        "sourceRecordId": document.get(
            "sourceRecordId"
        ),
        "sourceDate": document.get(
            "sourceDate"
        ),
    }


@router.post(
    "",
    status_code=201,
)
def create_project(
    payload: ProjectFields,
):
    document = payload.model_dump(
        mode="json"
    )

    now = datetime.now(
        timezone.utc
    )

    document[
        "createdAt"
    ] = now

    document[
        "updatedAt"
    ] = now

    if (
        document.get("latitude")
        is not None
        and document.get(
            "longitude"
        ) is not None
    ):
        document[
            "locationUpdatedAt"
        ] = now

    try:
        result = (
            db.projects.insert_one(
                document
            )
        )

        document[
            "_id"
        ] = result.inserted_id

        return serialize_project(
            document
        )

    except PyMongoError as exc:
        print(
            (
                "PROJECT SAVE ERROR: "
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
            flush=True,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Project save failed. "
                "Check the backend terminal."
            ),
        ) from None


@router.get("")
def list_projects():
    try:
        documents = list(
            db.projects
            .find()
            .sort(
                "_id",
                -1,
            )
            .limit(100)
        )

        return {
            "items": [
                serialize_project(
                    item
                )
                for item
                in documents
            ],
            "count": len(
                documents
            ),
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable.",
        ) from None


@router.post(
    "/upload-image",
    status_code=201,
)
async def upload_project_image(
    file: UploadFile = File(...),
):
    if file.content_type not in ALLOWED_PROJECT_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Use a JPG, PNG or WEBP image.",
        )

    content = await file.read(
        MAX_PROJECT_IMAGE_BYTES + 1
    )

    if len(content) > MAX_PROJECT_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Project image must be 5 MB or smaller.",
        )

    if not content:
        raise HTTPException(
            status_code=400,
            detail="The selected image is empty.",
        )

    configure_cloudinary()

    try:
        result = cloudinary.uploader.upload(
            content,
            folder="liva/projects",
            resource_type="image",
            use_filename=True,
            unique_filename=True,
            overwrite=False,
            transformation=[
                {
                    "width": 1600,
                    "height": 1000,
                    "crop": "limit",
                    "quality": "auto",
                    "fetch_format": "auto",
                }
            ],
        )
    except Exception as exc:
        print(
            f"CLOUDINARY UPLOAD ERROR: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Project image upload failed.",
        ) from None

    secure_url = result.get("secure_url")
    public_id = result.get("public_id")

    if not secure_url or not public_id:
        raise HTTPException(
            status_code=503,
            detail="Cloudinary returned an invalid upload response.",
        )

    return {
        "url": secure_url,
        "publicId": public_id,
        "width": result.get("width"),
        "height": result.get("height"),
        "format": result.get("format"),
        "bytes": result.get("bytes"),
    }


@router.delete(
    "/upload-image",
)
def delete_uploaded_project_image(
    payload: ImageDeleteRequest,
):
    configure_cloudinary()

    try:
        result = cloudinary.uploader.destroy(
            payload.publicId,
            resource_type="image",
            invalidate=True,
        )
    except Exception as exc:
        print(
            f"CLOUDINARY DELETE ERROR: {type(exc).__name__}: {exc}",
            flush=True,
        )
        raise HTTPException(
            status_code=503,
            detail="Uploaded image cleanup failed.",
        ) from None

    return {
        "deleted": result.get("result") in {"ok", "not found"},
        "result": result.get("result"),
    }


@router.get(
    "/{project_id}"
)
def get_project(
    project_id: str,
):
    if not ObjectId.is_valid(
        project_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid project ID."
            ),
        )

    try:
        document = (
            db.projects.find_one(
                {
                    "_id":
                        ObjectId(
                            project_id
                        )
                }
            )
        )

        if document is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Project not found."
                ),
            )

        return serialize_project(
            document
        )

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable.",
        ) from None


@router.patch(
    "/{project_id}"
)
def update_project(
    project_id: str,
    payload: ProjectUpdate,
):
    if not ObjectId.is_valid(
        project_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid project ID."
            ),
        )

    changes = payload.model_dump(
        mode="json",
        exclude_unset=True,
    )

    if not changes:
        raise HTTPException(
            status_code=400,
            detail=(
                "No changes supplied."
            ),
        )

    try:
        oid = ObjectId(
            project_id
        )

        existing = (
            db.projects.find_one(
                {
                    "_id": oid
                }
            )
        )

        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Project not found."
                ),
            )

        previous_image_public_id = existing.get(
            "imagePublicId"
        )

        source_name = (
            changes.get(
                "sourceName",
                existing.get(
                    "sourceName"
                ),
            )
        )

        source_url = (
            changes.get(
                "sourceUrl",
                existing.get(
                    "sourceUrl"
                ),
            )
        )

        if (
            not existing.get(
                "isDemo",
                True,
            )
            and (
                not source_name
                or not source_url
            )
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Non-demo records require "
                    "a source name and source URL."
                ),
            )

        candidate_lat = (
            changes.get(
                "latitude",
                existing.get(
                    "latitude"
                ),
            )
        )

        candidate_lon = (
            changes.get(
                "longitude",
                existing.get(
                    "longitude"
                ),
            )
        )

        if (
            candidate_lat is None
        ) != (
            candidate_lon is None
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    "Latitude and longitude "
                    "must be supplied together."
                ),
            )

        now = datetime.now(
            timezone.utc
        )

        if (
            "latitude" in changes
            or "longitude" in changes
            or "locationDisplayName"
            in changes
            or "locationSource"
            in changes
        ):
            changes[
                "locationUpdatedAt"
            ] = now

        changes[
            "updatedAt"
        ] = now

        updated = (
            db.projects
            .find_one_and_update(
                {
                    "_id": oid
                },
                {
                    "$set":
                        changes
                },
                return_document=
                    ReturnDocument.AFTER,
            )
        )

        if updated is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Project not found."
                ),
            )

        current_image_public_id = updated.get(
            "imagePublicId"
        )

        if (
            previous_image_public_id
            and previous_image_public_id
            != current_image_public_id
        ):
            destroy_cloudinary_image(
                previous_image_public_id
            )

        return serialize_project(
            updated
        )

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable.",
        ) from None

@router.delete(
    "/{project_id}",
)
def delete_project(
    project_id: str,
    cascade: bool = Query(
        default=False,
        description=(
            "When true, remove records in other LIVA collections "
            "that reference this project ID before deleting the project."
        ),
    ),
):
    if not ObjectId.is_valid(project_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID.",
        )

    oid = ObjectId(project_id)

    try:
        existing = db.projects.find_one(
            {"_id": oid}
        )

        if existing is None:
            raise HTTPException(
                status_code=404,
                detail="Project not found.",
            )

        relation_filter = {
            "$or": [
                {"projectId": project_id},
                {"projectId": oid},
                {"project_id": project_id},
                {"project_id": oid},
            ]
        }

        related_counts: dict[str, int] = {}

        for collection_name in db.list_collection_names():
            if (
                collection_name == "projects"
                or collection_name.startswith("system.")
            ):
                continue

            count = db[collection_name].count_documents(
                relation_filter,
                limit=1,
            )

            if count:
                related_counts[collection_name] = count

        if related_counts and not cascade:
            linked_total = sum(related_counts.values())
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Project has linked LIVA records ({linked_total}). "
                    "Retry with cascade=true to remove the project and "
                    "its linked records."
                ),
            )

        deleted_related: dict[str, int] = {}

        if cascade:
            for collection_name in list(related_counts):
                result = db[collection_name].delete_many(
                    relation_filter
                )

                if result.deleted_count:
                    deleted_related[
                        collection_name
                    ] = result.deleted_count

        result = db.projects.delete_one(
            {"_id": oid}
        )

        image_deleted = destroy_cloudinary_image(
            existing.get("imagePublicId")
        )

        if result.deleted_count != 1:
            raise HTTPException(
                status_code=404,
                detail="Project not found.",
            )

        return {
            "deleted": True,
            "projectId": project_id,
            "projectName": existing.get(
                "name",
                "",
            ),
            "cascade": cascade,
            "relatedDeleted": deleted_related,
            "imageDeleted": image_deleted,
        }

    except HTTPException:
        raise

    except PyMongoError as exc:
        print(
            (
                "PROJECT DELETE ERROR: "
                f"{type(exc).__name__}: {exc}"
            ),
            flush=True,
        )

        raise HTTPException(
            status_code=503,
            detail=(
                "Project deletion failed. "
                "Check the backend terminal."
            ),
        ) from None

