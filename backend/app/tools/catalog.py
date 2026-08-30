"""Phoenix demo sites — small AOIs under the 10 mi² Basic cap."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def _box(west: float, south: float, east: float, north: float) -> dict[str, Any]:
    ring = [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        ],
    }


class Site(BaseModel):
    id: str
    name: str
    polygon_aoi: dict[str, Any]
    latitude: float
    longitude: float


PHOENIX_SITES: dict[str, Site] = {
    "phx_sky_harbor_yard": Site(
        id="phx_sky_harbor_yard",
        name="Sky Harbor industrial pocket",
        polygon_aoi=_box(-112.08, 33.43, -112.05, 33.45),
        latitude=33.44,
        longitude=-112.065,
    ),
    "phx_deer_valley": Site(
        id="phx_deer_valley",
        name="Deer Valley distribution yard",
        polygon_aoi=_box(-112.12, 33.67, -112.09, 33.69),
        latitude=33.68,
        longitude=-112.105,
    ),
    "phx_southwest_freight": Site(
        id="phx_southwest_freight",
        name="Southwest freight corridor",
        polygon_aoi=_box(-112.18, 33.38, -112.15, 33.40),
        latitude=33.39,
        longitude=-112.165,
    ),
    "phx_tempe_crossdock": Site(
        id="phx_tempe_crossdock",
        name="Tempe cross-dock",
        polygon_aoi=_box(-111.96, 33.40, -111.93, 33.42),
        latitude=33.41,
        longitude=-111.945,
    ),
}

DEFAULT_SITE_IDS = list(PHOENIX_SITES.keys())
