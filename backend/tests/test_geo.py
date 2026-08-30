from app.models.schemas import DateTimeSpec, HeatmapJobSpec
from app.tools.geo import polygon_area_km2, validate_env_params, validate_heatmap
from tests.fixtures.geo import DUBAI_AOI, PHOENIX_WAREHOUSE_AOI
from app.models.schemas import EnvParamsJobSpec


def test_phoenix_pocket_is_under_basic_aoi_cap():
    area_km2 = polygon_area_km2(PHOENIX_WAREHOUSE_AOI)
    assert area_km2 < 20
    job = HeatmapJobSpec(
        polygon_aoi=PHOENIX_WAREHOUSE_AOI,
        date_time=DateTimeSpec(start_date="2024-07-15", start_time="14:00", filter_type=1),
        granularity=100,
    )
    assert validate_heatmap(job, max_aoi_mi2=10) == []


def test_dubai_rejected():
    job = HeatmapJobSpec(
        polygon_aoi=DUBAI_AOI,
        date_time=DateTimeSpec(start_date="2024-07-15", start_time="14:00", filter_type=1),
        granularity=100,
    )
    errors = validate_heatmap(job, max_aoi_mi2=10)
    assert any("U.S." in msg for msg in errors)


def test_forecast_beyond_12h_rejected():
    job = HeatmapJobSpec(
        polygon_aoi=PHOENIX_WAREHOUSE_AOI,
        date_time=DateTimeSpec(start_date="2099-01-01", start_time="14:00", filter_type=1),
        granularity=100,
    )
    errors = validate_heatmap(job, max_aoi_mi2=10)
    assert any("horizon" in msg for msg in errors)


def test_pre_2021_rejected():
    job = HeatmapJobSpec(
        polygon_aoi=PHOENIX_WAREHOUSE_AOI,
        date_time=DateTimeSpec(start_date="2020-08-01", start_time="14:00", filter_type=1),
        granularity=100,
    )
    errors = validate_heatmap(job, max_aoi_mi2=10)
    assert any("2021-01-01" in msg for msg in errors)


def test_env_params_caps_analysis_list_for_basic_plan():
    job = EnvParamsJobSpec(
        latitude=33.44,
        longitude=-112.07,
        temperature=40.0,
        date_time=DateTimeSpec(start_date="2024-07-15", start_time="14:00", filter_type=1),
        analysis=["heat_index_celsius", "wet_bulb_temperature_celsius", "air_quality:idx", "co2_ppm"],
    )
    errors = validate_env_params(job)
    assert any("3 parameters" in msg for msg in errors)
