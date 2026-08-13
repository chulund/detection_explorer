"""Footprints: exact for AHI, reconstructed and doubled for polar.

The AHI side is a lookup. Each Himawari pixel has a known polygon in the sensor grid, so the
only work is reprojecting it out of geostationary metres. The first test is the one that
matters: it proves the projection was derived correctly by checking a reprojected centroid
against the grid's own latitude and longitude, which means no projection constant has to be
hardcoded and trusted.

The polar side is a reconstruction, and it returns two polygons rather than one. A FIRMS row
cannot say which side of the ground track the pixel lay on, and at these latitudes the two
possibilities differ materially: measured IoU 0.7802 with corners up to 476 m apart. Drawing
one would assert something the source does not know.
"""

from __future__ import annotations

import pytest
from pyproj import Geod

from app.footprints.ahi import grid_lookup, pixel_footprint
from app.footprints.polar import polar_footprint_for

GEOD = Geod(ellps="WGS84")

# A real detection from the staged scene: x,y join x_subset,y_subset in the pixel grid.
SAMPLE_XY = (671, 287)

SNPP_ROW = {"lat": -37.02728, "lon": 141.11269, "scan": 0.4, "track": 0.37,
            "satellite": "N", "daynight": "D", "instrument": "VIIRS"}


# ------------------------------------------------------------------ AHI

def test_grid_lookup_is_keyed_by_subset_coordinates():
    lookup = grid_lookup()
    assert SAMPLE_XY in lookup


def test_reprojected_centroid_matches_the_grids_own_lonlat():
    """Proves the CRS was derived correctly, without hardcoding projection constants."""
    lookup = grid_lookup()
    entry = lookup[SAMPLE_XY]
    poly = pixel_footprint(*SAMPLE_XY)
    assert abs(poly.centroid.x - entry["lon"]) < 1e-3
    assert abs(poly.centroid.y - entry["lat"]) < 1e-3


def test_ahi_pixel_is_about_four_square_kilometres():
    """The sensor grid is 2 km at nadir, so a pixel is roughly 4 km2."""
    area, _ = GEOD.geometry_area_perimeter(pixel_footprint(*SAMPLE_XY))
    assert 2.0e6 < abs(area) < 8.0e6


def test_ahi_footprint_is_a_closed_valid_ring():
    poly = pixel_footprint(*SAMPLE_XY)
    assert poly.is_valid
    assert poly.exterior.is_ring


def test_unknown_pixel_returns_none():
    assert pixel_footprint(999999, 999999) is None


# ------------------------------------------------------------------ polar

def test_polar_returns_two_candidates_and_says_so():
    geometry, side = polar_footprint_for(SNPP_ROW)
    assert side == "ambiguous"
    assert geometry.geom_type == "MultiPolygon"
    assert len(geometry.geoms) == 2


def test_the_two_candidates_actually_differ():
    """Guards against silently emitting the same polygon twice."""
    geometry, _ = polar_footprint_for({**SNPP_ROW, "scan": 1.5, "track": 0.9})
    a, b = geometry.geoms
    assert a.intersection(b).area / a.union(b).area < 0.99


def test_both_candidates_are_valid():
    geometry, _ = polar_footprint_for(SNPP_ROW)
    assert all(g.is_valid and g.area > 0 for g in geometry.geoms)


def test_viirs_pixel_is_far_smaller_than_an_ahi_pixel():
    """The comparison the whole interface exists to make."""
    geometry, _ = polar_footprint_for(SNPP_ROW)
    viirs_area, _ = GEOD.geometry_area_perimeter(geometry.geoms[0])
    ahi_area, _ = GEOD.geometry_area_perimeter(pixel_footprint(*SAMPLE_XY))
    assert abs(viirs_area) < abs(ahi_area) / 10


def test_viirs_pixel_area_is_physically_plausible():
    """375 m nominal, so roughly 0.14 km2 near nadir."""
    geometry, _ = polar_footprint_for(SNPP_ROW)
    area, _ = GEOD.geometry_area_perimeter(geometry.geoms[0])
    assert 5.0e4 < abs(area) < 5.0e5


def test_modis_and_viirs_use_different_scan_models():
    modis = {**SNPP_ROW, "satellite": "Aqua", "instrument": "MODIS",
             "scan": 1.0, "track": 1.0}
    modis_geom, _ = polar_footprint_for(modis)
    viirs_geom, _ = polar_footprint_for(SNPP_ROW)
    m_area, _ = GEOD.geometry_area_perimeter(modis_geom.geoms[0])
    v_area, _ = GEOD.geometry_area_perimeter(viirs_geom.geoms[0])
    assert abs(m_area) > abs(v_area) * 3


def test_unknown_satellite_is_refused_rather_than_guessed():
    with pytest.raises(KeyError):
        polar_footprint_for({**SNPP_ROW, "satellite": "MYSTERY-1"})


# ------------------------------------------------------------------ attachment

def test_attached_record_carries_the_whole_provenance_block(make_detection):
    from app.footprints.polar import attach_polar_footprint

    record = make_detection()
    attached = attach_polar_footprint(record, SNPP_ROW)
    assert attached.footprint["type"] == "MultiPolygon"
    assert attached.footprint_kind == "satellite_pixel_footprint"
    assert attached.footprint_method == "polar_reconstructed"
    assert attached.footprint_status == "experimental"
    assert attached.footprint_side == "ambiguous"
    assert attached.footprint_model_version


def test_ahi_attachment_is_validated_not_experimental(make_detection):
    from app.footprints.ahi import attach_ahi_footprint

    record = make_detection(instrument="AHI", platform="Himawari-9")
    attached = attach_ahi_footprint(record, *SAMPLE_XY)
    assert attached.footprint_method == "ahi_grid"
    assert attached.footprint_status == "validated"
    assert attached.footprint_side is None
