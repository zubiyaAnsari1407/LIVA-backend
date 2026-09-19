from datetime import date, datetime, timezone
from typing import Any, Literal

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)
from pymongo.errors import PyMongoError

from database import db


router = APIRouter(
    prefix="/api/gis",
    tags=["GIS"],
)


GeometryType = Literal[
    "Polygon",
    "MultiPolygon",
]


def _validate_point(
    point: Any,
) -> None:
    if (
        not isinstance(point, list)
        or len(point) < 2
    ):
        raise ValueError(
            "Invalid coordinate point."
        )

    lon = point[0]
    lat = point[1]

    if not isinstance(
        lon,
        (int, float),
    ):
        raise ValueError(
            "Longitude must be numeric."
        )

    if not isinstance(
        lat,
        (int, float),
    ):
        raise ValueError(
            "Latitude must be numeric."
        )

    if not -180 <= lon <= 180:
        raise ValueError(
            "Longitude must be between -180 and 180."
        )

    if not -90 <= lat <= 90:
        raise ValueError(
            "Latitude must be between -90 and 90."
        )


def _validate_ring(
    ring: Any,
) -> None:
    if (
        not isinstance(ring, list)
        or len(ring) < 4
    ):
        raise ValueError(
            "Polygon ring requires at least 4 points."
        )

    for point in ring:
        _validate_point(
            point
        )

    if ring[0][:2] != ring[-1][:2]:
        raise ValueError(
            "Polygon ring must be closed."
        )


def validate_geometry(
    geometry: dict[str, Any],
) -> dict[str, Any]:
    geometry_type = geometry.get(
        "type"
    )

    coordinates = geometry.get(
        "coordinates"
    )

    if geometry_type not in {
        "Polygon",
        "MultiPolygon",
    }:
        raise ValueError(
            "Only Polygon and MultiPolygon geometry are supported."
        )

    if not isinstance(
        coordinates,
        list,
    ):
        raise ValueError(
            "GeoJSON coordinates are required."
        )

    if geometry_type == "Polygon":
        if not coordinates:
            raise ValueError(
                "Polygon requires at least one ring."
            )

        for ring in coordinates:
            _validate_ring(
                ring
            )

    if geometry_type == "MultiPolygon":
        if not coordinates:
            raise ValueError(
                "MultiPolygon requires polygons."
            )

        for polygon in coordinates:
            if (
                not isinstance(
                    polygon,
                    list,
                )
                or not polygon
            ):
                raise ValueError(
                    "Invalid MultiPolygon."
                )

            for ring in polygon:
                _validate_ring(
                    ring
                )

    return geometry


class GeometryPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    geometry: dict[str, Any]

    isDemo: bool = True

    sourceName: str | None = Field(
        default=None,
        max_length=250,
    )

    sourceUrl: HttpUrl | None = None

    sourceRecordId: str | None = Field(
        default=None,
        max_length=250,
    )

    sourceDate: date | None = None

    @field_validator(
        "geometry"
    )
    @classmethod
    def validate_geojson(
        cls,
        value: dict[str, Any],
    ):
        return validate_geometry(
            value
        )

    @model_validator(
        mode="after"
    )
    def validate_source(
        self,
    ):
        if not self.isDemo and (
            not self.sourceName
            or self.sourceUrl is None
        ):
            raise ValueError(
                "Verified non-demo geometry requires sourceName and sourceUrl."
            )

        return self


def project_oid(
    project_id: str,
) -> ObjectId:
    if not ObjectId.is_valid(
        project_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid project ID.",
        )

    return ObjectId(
        project_id
    )


def parcel_oid(
    parcel_id: str,
) -> ObjectId:
    if not ObjectId.is_valid(
        parcel_id
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid parcel ID.",
        )

    return ObjectId(
        parcel_id
    )


@router.get(
    "/health"
)
def gis_health():
    try:
        located_projects = (
            db.projects.count_documents(
                {
                    "latitude": {
                        "$type": "number"
                    },
                    "longitude": {
                        "$type": "number"
                    },
                }
            )
        )

        parcel_geometries = (
            db.parcels.count_documents(
                {
                    "geometry.type": {
                        "$in": [
                            "Polygon",
                            "MultiPolygon",
                        ]
                    }
                }
            )
        )

        boundaries = (
            db.gis_project_boundaries
            .count_documents({})
        )

        return {
            "status": "ok",
            "locatedProjects":
                located_projects,
            "parcelGeometries":
                parcel_geometries,
            "projectBoundaries":
                boundaries,
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="GIS database unavailable.",
        ) from None


@router.get(
    "/projects"
)
def project_geojson(
    state: str | None = None,
    district: str | None = None,
    stage: str | None = None,
):
    query: dict[str, Any] = {
        "latitude": {
            "$type": "number"
        },
        "longitude": {
            "$type": "number"
        },
    }

    if state:
        query["state"] = state

    if district:
        query["district"] = district

    if stage:
        query["stage"] = stage

    try:
        documents = list(
            db.projects.find(
                query,
                {
                    "name": 1,
                    "state": 1,
                    "district": 1,
                    "stage": 1,
                    "progress": 1,
                    "latitude": 1,
                    "longitude": 1,
                    "locationDisplayName": 1,
                    "locationSource": 1,
                    "isDemo": 1,
                    "sourceName": 1,
                },
            ).limit(1000)
        )

        features = []

        for project in documents:
            features.append(
                {
                    "type": "Feature",
                    "id": str(
                        project["_id"]
                    ),
                    "geometry": {
                        "type": "Point",
                        "coordinates": [
                            project.get(
                                "longitude"
                            ),
                            project.get(
                                "latitude"
                            ),
                        ],
                    },
                    "properties": {
                        "projectId": str(
                            project["_id"]
                        ),
                        "name":
                            project.get(
                                "name",
                                "",
                            ),
                        "state":
                            project.get(
                                "state",
                                "",
                            ),
                        "district":
                            project.get(
                                "district",
                                "",
                            ),
                        "stage":
                            project.get(
                                "stage",
                                "",
                            ),
                        "progress":
                            project.get(
                                "progress"
                            ),
                        "locationDisplayName":
                            project.get(
                                "locationDisplayName"
                            ),
                        "locationSource":
                            project.get(
                                "locationSource"
                            ),
                        "isDemo":
                            project.get(
                                "isDemo",
                                True,
                            ),
                        "sourceName":
                            project.get(
                                "sourceName"
                            ),
                    },
                }
            )

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="GIS database unavailable.",
        ) from None


@router.get(
    "/parcels"
)
def parcel_geojson(
    projectId: str | None = None,
    stage: str | None = None,
    ownership: str | None = None,
    limit: int = Query(
        default=2000,
        ge=1,
        le=5000,
    ),
):
    query: dict[str, Any] = {
        "geometry.type": {
            "$in": [
                "Polygon",
                "MultiPolygon",
            ]
        }
    }

    if projectId:
        if not ObjectId.is_valid(
            projectId
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid project ID.",
            )

        query["projectId"] = projectId

    if stage:
        query["stage"] = stage

    if ownership:
        query[
            "ownership"
        ] = ownership

    try:
        documents = list(
            db.parcels.find(
                query
            ).limit(
                limit
            )
        )

        project_ids = {
            ObjectId(
                item["projectId"]
            )
            for item in documents
            if ObjectId.is_valid(
                str(
                    item.get(
                        "projectId",
                        "",
                    )
                )
            )
        }

        project_names = {
            str(item["_id"]):
                item.get(
                    "name",
                    "",
                )
            for item in db.projects.find(
                {
                    "_id": {
                        "$in": list(
                            project_ids
                        )
                    }
                },
                {
                    "name": 1
                },
            )
        }

        features = []

        for parcel in documents:
            project_id = str(
                parcel.get(
                    "projectId",
                    "",
                )
            )

            features.append(
                {
                    "type": "Feature",
                    "id": str(
                        parcel["_id"]
                    ),
                    "geometry":
                        parcel["geometry"],
                    "properties": {
                        "parcelId": str(
                            parcel["_id"]
                        ),
                        "projectId":
                            project_id,
                        "projectName":
                            project_names.get(
                                project_id,
                                "Project unavailable",
                            ),
                        "surveyNumber":
                            parcel.get(
                                "surveyNumber",
                                "",
                            ),
                        "village":
                            parcel.get(
                                "village",
                                "",
                            ),
                        "district":
                            parcel.get(
                                "district",
                                "",
                            ),
                        "areaHa":
                            parcel.get(
                                "areaHa"
                            ),
                        "ownership":
                            parcel.get(
                                "ownership",
                                "Pending verification",
                            ),
                        "stage":
                            parcel.get(
                                "stage",
                                "Survey",
                            ),
                        "isDemo":
                            parcel.get(
                                "isDemo",
                                True,
                            ),
                        "sourceName":
                            parcel.get(
                                "sourceName"
                            ),
                    },
                }
            )

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="GIS database unavailable.",
        ) from None


@router.put(
    "/parcels/{parcel_id}/geometry"
)
def save_parcel_geometry(
    parcel_id: str,
    payload: GeometryPayload,
):
    oid = parcel_oid(
        parcel_id
    )

    try:
        parcel = db.parcels.find_one(
            {
                "_id": oid
            }
        )

        if parcel is None:
            raise HTTPException(
                status_code=404,
                detail="Parcel not found.",
            )

        data = payload.model_dump(
            mode="json"
        )

        now = datetime.now(
            timezone.utc
        )

        db.parcels.update_one(
            {
                "_id": oid
            },
            {
                "$set": {
                    "geometry":
                        data[
                            "geometry"
                        ],
                    "geometrySource": {
                        "isDemo":
                            data[
                                "isDemo"
                            ],
                        "sourceName":
                            data.get(
                                "sourceName"
                            ),
                        "sourceUrl":
                            data.get(
                                "sourceUrl"
                            ),
                        "sourceRecordId":
                            data.get(
                                "sourceRecordId"
                            ),
                        "sourceDate":
                            data.get(
                                "sourceDate"
                            ),
                    },
                    "geometryUpdatedAt":
                        now,
                }
            },
        )

        return {
            "status": "saved",
            "parcelId":
                parcel_id,
            "geometry":
                data[
                    "geometry"
                ],
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="GIS database unavailable.",
        ) from None


@router.delete(
    "/parcels/{parcel_id}/geometry"
)
def remove_parcel_geometry(
    parcel_id: str,
):
    oid = parcel_oid(
        parcel_id
    )

    try:
        result = (
            db.parcels.update_one(
                {
                    "_id": oid
                },
                {
                    "$unset": {
                        "geometry": "",
                        "geometrySource": "",
                        "geometryUpdatedAt": "",
                    }
                },
            )
        )

        if (
            result.matched_count
            == 0
        ):
            raise HTTPException(
                status_code=404,
                detail="Parcel not found.",
            )

        return {
            "status": "removed",
            "parcelId":
                parcel_id,
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="GIS database unavailable.",
        ) from None


@router.get(
    "/boundaries"
)
def project_boundaries(
    projectId: str | None = None,
):
    query: dict[str, Any] = {}

    if projectId:
        if not ObjectId.is_valid(
            projectId
        ):
            raise HTTPException(
                status_code=400,
                detail="Invalid project ID.",
            )

        query[
            "projectId"
        ] = projectId

    try:
        documents = list(
            db.gis_project_boundaries
            .find(
                query
            )
            .limit(1000)
        )

        project_ids = {
            ObjectId(
                item[
                    "projectId"
                ]
            )
            for item in documents
            if ObjectId.is_valid(
                item.get(
                    "projectId",
                    "",
                )
            )
        }

        project_names = {
            str(item["_id"]):
                item.get(
                    "name",
                    "",
                )
            for item in db.projects.find(
                {
                    "_id": {
                        "$in": list(
                            project_ids
                        )
                    }
                },
                {
                    "name": 1
                },
            )
        }

        features = []

        for item in documents:
            project_id = item[
                "projectId"
            ]

            features.append(
                {
                    "type": "Feature",
                    "id": str(
                        item["_id"]
                    ),
                    "geometry":
                        item[
                            "geometry"
                        ],
                    "properties": {
                        "projectId":
                            project_id,
                        "projectName":
                            project_names.get(
                                project_id,
                                "Project",
                            ),
                        "isDemo":
                            item.get(
                                "isDemo",
                                True,
                            ),
                        "sourceName":
                            item.get(
                                "sourceName"
                            ),
                    },
                }
            )

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="GIS database unavailable.",
        ) from None


@router.put(
    "/projects/{project_id}/boundary"
)
def save_project_boundary(
    project_id: str,
    payload: GeometryPayload,
):
    oid = project_oid(
        project_id
    )

    try:
        project = db.projects.find_one(
            {
                "_id": oid
            }
        )

        if project is None:
            raise HTTPException(
                status_code=404,
                detail="Project not found.",
            )

        data = payload.model_dump(
            mode="json"
        )

        now = datetime.now(
            timezone.utc
        )

        db.gis_project_boundaries.update_one(
            {
                "projectId":
                    project_id
            },
            {
                "$set": {
                    "projectId":
                        project_id,
                    "geometry":
                        data[
                            "geometry"
                        ],
                    "isDemo":
                        data[
                            "isDemo"
                        ],
                    "sourceName":
                        data.get(
                            "sourceName"
                        ),
                    "sourceUrl":
                        data.get(
                            "sourceUrl"
                        ),
                    "sourceRecordId":
                        data.get(
                            "sourceRecordId"
                        ),
                    "sourceDate":
                        data.get(
                            "sourceDate"
                        ),
                    "updatedAt":
                        now,
                },
                "$setOnInsert": {
                    "createdAt":
                        now,
                },
            },
            upsert=True,
        )

        return {
            "status": "saved",
            "projectId":
                project_id,
            "geometry":
                data[
                    "geometry"
                ],
        }

    except PyMongoError:
        raise HTTPException(
            status_code=503,
            detail="GIS database unavailable.",
        ) from None