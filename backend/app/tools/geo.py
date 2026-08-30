from __future__ import annotations

from datetime import date, datetime, timezone

from pyproj import Geod
from shapely.geometry import Point, Polygon, shape

from app.models.schemas import (
    ALLOWED_GRANULARITIES,
    MIN_ALLOWED_DATE,
    DateTimeSpec,
    EnvParamsJobSpec,
    HeatmapJobSpec,
    TaskPlan,
    forecast_horizon,
)

GEOD = Geod(ellps="WGS84")

# Coarse U.S. coverage boxes (CONUS, Alaska, Hawaii, Puerto Rico, DC is inside CONUS).
# Vertices must fall in at least one box before we spend credits.
_US_BOXES = (
    {"name": "conus", "lat": (24.396308, 49.384358), "lon": (-124.848974, -66.885444)},
    {"name": "alaska", "lat": (51.214183, 71.538800), "lon": (-179.148909, -129.979506)},
    {"name": "hawaii", "lat": (18.910361, 22.235600), "lon": (-160.236000, -154.806000)},
    {"name": "puerto_rico", "lat": (17.883000, 18.516000), "lon": (-67.945000, -65.220000)},
)


class ValidationError(ValueError):
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        super().__init__("; ".join(messages))


def _in_us(lat: float, lon: float) -> bool:
    for box in _US_BOXES:
        lat_lo, lat_hi = box["lat"]
        lon_lo, lon_hi = box["lon"]
        if lat_lo <= lat <= lat_hi and lon_lo <= lon <= lon_hi:
            return True
    return False


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_datetime(day: str, time_hhmm: str | None) -> datetime:
    clock = time_hhmm or "00:00"
    naive = datetime.strptime(f"{day} {clock}", "%Y-%m-%d %H:%M")
    return naive.replace(tzinfo=timezone.utc)


def validate_date_time(spec: DateTimeSpec, *, allow_forecast: bool) -> list[str]:
    errors: list[str] = []
    start = _parse_date(spec.start_date)
    if start < MIN_ALLOWED_DATE:
        errors.append(
            f"start_date {spec.start_date} is before the allowed floor {MIN_ALLOWED_DATE.isoformat()}."
        )

    horizon = forecast_horizon() if allow_forecast else datetime.now(timezone.utc)
    start_dt = _parse_datetime(spec.start_date, spec.start_time)
    if start_dt > horizon:
        errors.append(
            f"start date/time {start_dt.isoformat()} is beyond the allowed horizon "
            f"{horizon.isoformat()} (forecasts are ≤12h for heatmaps only)."
        )

    if spec.filter_type not in {1, 2, 3}:
        errors.append(
            f"filter_type {spec.filter_type} is not in 1–3 "
            "(single hour / range of hours / single day). Types 4–5 are not used on live calls."
        )

    if spec.filter_type in {1, 2} and not spec.start_time:
        errors.append("start_time (HH:MM) is required for filter_type 1 and 2.")
    if spec.filter_type == 2 and not spec.end_time:
        errors.append("end_time (HH:MM) is required for filter_type 2.")
    if spec.filter_type == 4 and not spec.end_date:
        errors.append("end_date is required for filter_type 4.")

    if spec.end_date:
        end = _parse_date(spec.end_date)
        if end < start:
            errors.append("end_date is before start_date.")
        end_dt = _parse_datetime(spec.end_date, spec.end_time or "23:59")
        if end_dt > horizon:
            errors.append(f"end date/time {end_dt.isoformat()} is beyond the allowed horizon.")

    return errors


def _ring_from_aoi(polygon_aoi: dict) -> list[tuple[float, float]]:
    geom = polygon_aoi
    if polygon_aoi.get("type") == "FeatureCollection":
        features = polygon_aoi.get("features") or []
        if not features:
            raise ValidationError(["polygon_aoi FeatureCollection has no features."])
        geom = features[0].get("geometry") or {}
    elif polygon_aoi.get("type") == "Feature":
        geom = polygon_aoi.get("geometry") or {}

    if geom.get("type") != "Polygon":
        raise ValidationError(["polygon_aoi must be a GeoJSON Polygon (or Feature/FeatureCollection of one)."])

    rings = geom.get("coordinates") or []
    if not rings:
        raise ValidationError(["polygon_aoi has no coordinates."])
    ring = rings[0]
    if len(ring) < 4:
        raise ValidationError(["polygon ring must have at least 4 positions and be closed."])
    if ring[0] != ring[-1]:
        raise ValidationError(["polygon ring is not closed (first and last position must match)."])
    return [(float(lon), float(lat)) for lon, lat in ring]


def polygon_area_km2(polygon_aoi: dict) -> float:
    ring = _ring_from_aoi(polygon_aoi)
    poly = Polygon(ring)
    area_m2, _ = GEOD.geometry_area_perimeter(poly)
    return abs(area_m2) / 1_000_000.0


def validate_heatmap(job: HeatmapJobSpec, max_aoi_mi2: float) -> list[str]:
    errors = validate_date_time(job.date_time, allow_forecast=True)
    if job.granularity not in ALLOWED_GRANULARITIES:
        errors.append(f"granularity {job.granularity} must be one of {sorted(ALLOWED_GRANULARITIES)} meters.")

    try:
        ring = _ring_from_aoi(job.polygon_aoi)
    except ValidationError as exc:
        return errors + exc.messages

    for lon, lat in ring:
        if not _in_us(lat, lon):
            errors.append(f"coordinate [{lon}, {lat}] is outside supported U.S. coverage.")
            break

    area_km2 = polygon_area_km2(job.polygon_aoi)
    area_mi2 = area_km2 * 0.386102159
    if area_mi2 > max_aoi_mi2:
        errors.append(
            f"AOI is {area_mi2:.2f} mi² ({area_km2:.2f} km²), above the cap of {max_aoi_mi2:.1f} mi². "
            "Split the polygon or zoom in before submitting."
        )

    if job.analytic_type in {"exceedance", "persistence"} and job.threshold is None:
        errors.append("threshold (°C) is required for exceedance and persistence heatmaps.")

    return errors


def validate_env_params(job: EnvParamsJobSpec) -> list[str]:
    errors = validate_date_time(job.date_time, allow_forecast=False)
    if not _in_us(job.latitude, job.longitude):
        errors.append(
            f"point ({job.latitude}, {job.longitude}) is outside supported U.S. coverage."
        )
    if job.analysis is not None and len(job.analysis) > 3:
        errors.append(
            "analysis lists more than 3 parameters; API Basic/Startup reject extra names. "
            "Trim the list or confirm Premium access."
        )
    return errors


def validate_plan(plan: TaskPlan, max_aoi_mi2: float) -> list[str]:
    errors: list[str] = []
    if not plan.heatmap_jobs and not plan.env_params_jobs:
        errors.append("plan selected no FortyGuard jobs.")
    for job in plan.heatmap_jobs:
        errors.extend(validate_heatmap(job, max_aoi_mi2))
    for job in plan.env_params_jobs:
        errors.extend(validate_env_params(job))
    return errors


def point_in_us(lat: float, lon: float) -> bool:
    return _in_us(lat, lon)


def centroid_of_aoi(polygon_aoi: dict) -> Point:
    ring = _ring_from_aoi(polygon_aoi)
    return shape({"type": "Polygon", "coordinates": [ring]}).centroid
