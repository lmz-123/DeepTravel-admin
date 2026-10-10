"""Durable, leased city-map jobs. OSS contains immutable, validated GeoJSON."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from models import City, CityMap

SOURCE = "https://geo.datav.aliyun.com/areas_v3/bound"
MAX_BYTES = 4 * 1024 * 1024


@lru_cache(maxsize=1)
def city_directory():
    return json.loads((Path(__file__).parent / "data/map_cities.json").read_text())


def search_cities(query=""):
    query = query.strip()
    return [
        row
        for row in city_directory()
        if not query
        or query in row["name"]
        or query in row["province"]
        or query == row["adcode"]
    ][:30]


def resolve_city(name, adcode=None):
    if adcode:
        match = next((row for row in city_directory() if row["adcode"] == adcode), None)
        if match is None:
            raise ValueError("请选择目录中的城市")
        return match
    # No guessing from partial names or coordinates: an ambiguous match needs selection.
    matches = [
        row
        for row in city_directory()
        if row["name"] == name.strip() or row["name"].removesuffix("市") == name.strip()
    ]
    return matches[0] if len(matches) == 1 else None


def enqueue(db, city, adcode=None, *, force=False):
    row = db.get(CityMap, city.id)
    resolved = resolve_city(city.name, adcode)
    code = resolved["adcode"] if resolved else None
    if row is not None and not force and row.adcode == code:
        return row
    if row is None:
        row = CityMap(city_id=city.id)
        db.add(row)
    if row.adcode != code:
        row.object_key, row.version, row.district_count = None, None, 0
    row.adcode = code
    row.status = "pending" if code else "needs_city"
    row.error = None if code else "请选择对应的行政城市，系统会自动准备底图"
    row.attempts = 0
    row.lease_token = None
    row.next_attempt_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()
    return row


def map_status(row):
    if row is None:
        return {"status": "pending", "adcode": None, "district_count": 0, "error": None}
    return {
        "status": row.status,
        "adcode": row.adcode,
        "district_count": row.district_count,
        "error": row.error,
        "version": row.version,
    }


def validate_geometry(data, adcode):
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError("地图格式无效")
    features = data.get("features")
    if not isinstance(features, list) or not 1 <= len(features) <= 200:
        raise ValueError("地图缺少区县边界")
    count = 0

    def point(value):
        return (
            isinstance(value, list)
            and len(value) >= 2
            and all(
                isinstance(n, (int, float))
                and not isinstance(n, bool)
                and math.isfinite(n)
                for n in value[:2]
            )
            and abs(value[0]) <= 180
            and abs(value[1]) <= 85
        )

    for feature in features:
        props = feature.get("properties", {})
        if (
            not isinstance(props.get("name"), str)
            or not props["name"].strip()
            or not point(props.get("center"))
            or str((props.get("parent") or {}).get("adcode")) != adcode
        ):
            raise ValueError("地图区县与所选城市不符")
        geometry = feature.get("geometry", {})
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("地图边界格式无效")
        polygons = geometry.get("coordinates")
        if geometry["type"] == "Polygon":
            polygons = [polygons]
        if not isinstance(polygons, list) or not polygons:
            raise ValueError("地图边界为空")
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("地图多边形为空")
            for ring in polygon:
                if (
                    not isinstance(ring, list)
                    or len(ring) < 4
                    or ring[0] != ring[-1]
                    or not all(point(p) for p in ring)
                ):
                    raise ValueError("地图坐标无效")
                count += len(ring)
                if count > 120_000:
                    raise ValueError("地图过大")
    return data


def download_geometry(adcode):
    # Only directory codes on the fixed HTTPS data source are fetched, never user URLs.
    resolve_city("", adcode)
    with httpx.stream(
        "GET", f"{SOURCE}/{adcode}_full.json", timeout=15, follow_redirects=False
    ) as response:
        response.raise_for_status()
        payload = bytearray()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > MAX_BYTES:
                raise ValueError("地图文件过大")
    return validate_geometry(json.loads(payload), adcode)


class CityMapWorker:
    def __init__(self, sessions, storage, fetch=download_geometry):
        self.sessions, self.storage, self.fetch = sessions, storage, fetch

    def reconcile(self):
        # Includes cities created by package imports and older CMS installations.
        with self.sessions() as db:
            missing = list(
                db.scalars(
                    select(City)
                    .outerjoin(CityMap, City.id == CityMap.city_id)
                    .where(CityMap.city_id.is_(None))
                    .limit(50)
                )
            )
            for city in missing:
                enqueue(db, city)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()  # Another worker already created these jobs.

    def run_one(self):
        now = datetime.utcnow()
        with self.sessions() as db:
            row = db.scalar(
                select(CityMap)
                .where(
                    CityMap.status.in_(["pending", "failed", "processing"]),
                    CityMap.next_attempt_at <= now,
                )
                .order_by(CityMap.next_attempt_at)
                .limit(1)
            )
            if row is None:
                return False
            city_id, adcode, attempts = row.city_id, row.adcode, row.attempts + 1
            token = str(uuid4())
            claimed = db.execute(
                update(CityMap)
                .where(
                    CityMap.city_id == city_id,
                    CityMap.adcode == adcode,
                    CityMap.next_attempt_at <= now,
                    CityMap.status.in_(["pending", "failed", "processing"]),
                )
                .values(
                    status="processing",
                    lease_token=token,
                    attempts=attempts,
                    next_attempt_at=now + timedelta(minutes=5),
                    updated_at=now,
                )
            )
            db.commit()
            if claimed.rowcount != 1:
                return True
        try:
            data = validate_geometry(self.fetch(adcode), adcode)
            payload = json.dumps(
                data, ensure_ascii=False, separators=(",", ":")
            ).encode()
            if len(payload) > MAX_BYTES:
                raise ValueError("地图文件过大")
            version = hashlib.sha256(payload).hexdigest()
            key = f"maps/cities/{adcode}/{version}.geojson"
            if not self.storage.exists(key):
                try:
                    self.storage.put(key, payload, "application/geo+json")
                except Exception:
                    # Concurrent cities can share the same immutable map object.
                    if not self.storage.exists(key):
                        raise
            values = dict(
                status="ready",
                object_key=key,
                version=version,
                district_count=len(data["features"]),
                error=None,
            )
        except Exception:
            # SDK errors can contain credentials/URLs; keep them out of public status.
            values = dict(
                status="failed", error="底图获取暂未成功，将自动重试，也可手动重试"
            )
        with self.sessions() as db:
            db.execute(
                update(CityMap)
                .where(CityMap.city_id == city_id, CityMap.lease_token == token)
                .values(
                    **values,
                    lease_token=None,
                    updated_at=datetime.utcnow(),
                    next_attempt_at=datetime.utcnow()
                    + timedelta(seconds=min(21600, 60 * 2 ** min(attempts - 1, 9))),
                )
            )
            db.commit()
        return True
