import re
import threading
import time

import requests
from fastapi import APIRouter, HTTPException, Query


router = APIRouter(
    prefix="/api/geocode",
    tags=["GIS Geocoding"],
)


NOMINATIM_URL = (
    "https://nominatim.openstreetmap.org/search"
)

PHOTON_URL = (
    "https://photon.komoot.io/api/"
)

HEADERS = {
    "User-Agent": (
        "LIVA-Land-Acquisition-Research/1.0"
    ),
    "Accept": "application/json",
}


CACHE_TTL_SECONDS = 15 * 60
MAX_CACHE_ITEMS = 200

_cache: dict[
    str,
    tuple[float, list[dict]],
] = {}

_nominatim_lock = threading.Lock()
_last_nominatim_request = 0.0


def normalize_query(
    value: str,
) -> str:
    value = re.sub(
        r"[^\w\s,.-]",
        " ",
        value,
        flags=re.UNICODE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def wait_for_nominatim():
    global _last_nominatim_request

    with _nominatim_lock:
        now = time.monotonic()

        elapsed = (
            now
            - _last_nominatim_request
        )

        if elapsed < 1.05:
            time.sleep(
                1.05 - elapsed
            )

        _last_nominatim_request = (
            time.monotonic()
        )


def parse_nominatim(
    rows: list[dict],
) -> list[dict]:
    results = []

    for row in rows:
        try:
            lat = float(
                row["lat"]
            )

            lon = float(
                row["lon"]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ):
            continue

        bbox = None

        raw_bbox = row.get(
            "boundingbox"
        )

        if (
            isinstance(
                raw_bbox,
                list,
            )
            and len(raw_bbox) == 4
        ):
            try:
                bbox = [
                    float(
                        raw_bbox[0]
                    ),
                    float(
                        raw_bbox[1]
                    ),
                    float(
                        raw_bbox[2]
                    ),
                    float(
                        raw_bbox[3]
                    ),
                ]
            except (
                TypeError,
                ValueError,
            ):
                bbox = None

        display_name = str(
            row.get(
                "display_name",
                "",
            )
        )

        namedetails = (
            row.get(
                "namedetails"
            )
            or {}
        )

        name = (
            namedetails.get("name")
            or row.get("name")
            or display_name.split(
                ","
            )[0]
        )

        results.append(
            {
                "id": (
                    "nominatim-"
                    f"{row.get('place_id')}"
                ),
                "name": str(name),
                "display_name":
                    display_name,
                "lat": lat,
                "lon": lon,
                "type": row.get(
                    "type"
                ),
                "category": row.get(
                    "category"
                ),
                "source":
                    "OpenStreetMap Nominatim",
                "boundingbox":
                    bbox,
            }
        )

    return results


def nominatim_search(
    query: str,
) -> list[dict]:
    wait_for_nominatim()

    response = requests.get(
        NOMINATIM_URL,
        params={
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "namedetails": 1,
            "extratags": 1,
            "dedupe": 1,
            "limit": 8,
        },
        headers=HEADERS,
        timeout=10,
    )

    response.raise_for_status()

    return parse_nominatim(
        response.json()
    )


def nominatim_structured_search(
    name: str,
    city: str,
) -> list[dict]:
    wait_for_nominatim()

    response = requests.get(
        NOMINATIM_URL,
        params={
            "amenity": name,
            "city": city,
            "format": "jsonv2",
            "addressdetails": 1,
            "namedetails": 1,
            "dedupe": 1,
            "limit": 8,
        },
        headers=HEADERS,
        timeout=10,
    )

    response.raise_for_status()

    return parse_nominatim(
        response.json()
    )


def photon_search(
    query: str,
) -> list[dict]:
    response = requests.get(
        PHOTON_URL,
        params={
            "q": query,
            "limit": 8,
            "lang": "en",
        },
        headers=HEADERS,
        timeout=10,
    )

    response.raise_for_status()

    payload = response.json()

    features = payload.get(
        "features",
        [],
    )

    results = []

    for feature in features:
        geometry = (
            feature.get(
                "geometry"
            )
            or {}
        )

        coordinates = (
            geometry.get(
                "coordinates"
            )
        )

        if (
            not isinstance(
                coordinates,
                list,
            )
            or len(coordinates) < 2
        ):
            continue

        try:
            lon = float(
                coordinates[0]
            )

            lat = float(
                coordinates[1]
            )
        except (
            TypeError,
            ValueError,
        ):
            continue

        properties = (
            feature.get(
                "properties"
            )
            or {}
        )

        name = str(
            properties.get(
                "name"
            )
            or properties.get(
                "street"
            )
            or "Location"
        )

        address_parts = [
            name,
            properties.get(
                "street"
            ),
            properties.get(
                "locality"
            ),
            properties.get(
                "district"
            ),
            properties.get(
                "city"
            ),
            properties.get(
                "state"
            ),
            properties.get(
                "postcode"
            ),
            properties.get(
                "country"
            ),
        ]

        clean_parts = []

        for part in address_parts:
            if not part:
                continue

            text = str(part)

            if (
                not clean_parts
                or clean_parts[-1]
                != text
            ):
                clean_parts.append(
                    text
                )

        bbox = None

        extent = properties.get(
            "extent"
        )

        if (
            isinstance(
                extent,
                list,
            )
            and len(extent) == 4
        ):
            try:
                # Photon:
                # minLon, minLat,
                # maxLon, maxLat
                bbox = [
                    float(extent[1]),
                    float(extent[3]),
                    float(extent[0]),
                    float(extent[2]),
                ]
            except (
                TypeError,
                ValueError,
            ):
                bbox = None

        results.append(
            {
                "id": (
                    "photon-"
                    f"{properties.get('osm_type', '')}-"
                    f"{properties.get('osm_id', '')}-"
                    f"{lat}-{lon}"
                ),
                "name": name,
                "display_name":
                    ", ".join(
                        clean_parts
                    ),
                "lat": lat,
                "lon": lon,
                "type": properties.get(
                    "osm_value"
                )
                or properties.get(
                    "type"
                ),
                "category":
                    properties.get(
                        "osm_key"
                    ),
                "source":
                    "Photon / OpenStreetMap",
                "boundingbox":
                    bbox,
            }
        )

    return results


def deduplicate(
    rows: list[dict],
) -> list[dict]:
    seen = set()
    output = []

    for row in rows:
        key = (
            round(
                float(row["lat"]),
                5,
            ),
            round(
                float(row["lon"]),
                5,
            ),
        )

        if key in seen:
            continue

        seen.add(key)
        output.append(row)

    return output[:10]


@router.get("/search")
def search_places(
    q: str = Query(
        min_length=3,
        max_length=180,
    ),
):
    query = q.strip()

    cache_key = (
        query.lower()
    )

    cached = _cache.get(
        cache_key
    )

    if cached:
        saved_at, items = cached

        if (
            time.time()
            - saved_at
            < CACHE_TTL_SECONDS
        ):
            return {
                "query": query,
                "items": items,
                "count": len(items),
                "cached": True,
            }

    results: list[dict] = []

    errors = []

    # 1. Exact free-form
    try:
        results.extend(
            nominatim_search(
                query
            )
        )
    except requests.RequestException as exc:
        errors.append(
            f"Nominatim: {exc}"
        )

    # 2. Photon fallback
    if len(results) < 5:
        try:
            results.extend(
                photon_search(
                    query
                )
            )
        except requests.RequestException as exc:
            errors.append(
                f"Photon: {exc}"
            )

    # 3. Normalized query fallback
    if not results:
        normalized = (
            normalize_query(
                query
            )
        )

        if (
            normalized
            and normalized.lower()
            != query.lower()
        ):
            try:
                results.extend(
                    nominatim_search(
                        normalized
                    )
                )
            except requests.RequestException:
                pass

            try:
                results.extend(
                    photon_search(
                        normalized
                    )
                )
            except requests.RequestException:
                pass

    # 4. POI + city structured search
    if not results:
        parts = [
            part.strip()
            for part
            in query.split(",")
            if part.strip()
        ]

        if len(parts) >= 2:
            place_name = (
                parts[0]
            )

            city = (
                parts[-1]
            )

            try:
                results.extend(
                    nominatim_structured_search(
                        place_name,
                        city,
                    )
                )
            except requests.RequestException:
                pass

    results = deduplicate(
        results
    )

    if (
        not results
        and len(errors) >= 2
    ):
        raise HTTPException(
            status_code=503,
            detail=(
                "Location search providers "
                "are temporarily unavailable."
            ),
        )

    if len(_cache) >= MAX_CACHE_ITEMS:
        oldest_key = min(
            _cache,
            key=lambda key:
                _cache[key][0],
        )

        _cache.pop(
            oldest_key,
            None,
        )

    _cache[cache_key] = (
        time.time(),
        results,
    )

    return {
        "query": query,
        "items": results,
        "count": len(results),
        "cached": False,
    }