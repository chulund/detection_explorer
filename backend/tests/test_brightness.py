"""Brightness temperature, carried with the channel that produced it.

Every source measures a brightness temperature and every one of them measures it in a
different band: VIIRS reports I4 at 3.74 um, MODIS reports T21 at 4 um, BRIGHT reports the
AHI B07 mid-infrared at 3.9 um, and DEA reports a Kelvin value without saying which band
at all. A single unlabelled number would present four different measurements as one
quantity, so `brightness_channel` travels with `brightness_k` for the same reason
`confidence_scheme` travels with `confidence`.
"""

from __future__ import annotations

from app.providers.dea import parse_wfs_xml
from app.providers.firms import parse_firms_csv

WINDOW = {"start": "2026-04-09T04:00:00Z", "end": "2026-04-09T05:00:00Z"}

VIIRS_CSV = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,"
    "confidence,version,bright_ti5,frp,daynight,type\n"
    "-32.20486,152.21204,334.45,0.6,0.71,2026-04-09,0428,N,VIIRS,n,2,292.5,6.58,D,0\n"
)

MODIS_CSV = (
    "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,"
    "confidence,version,bright_t31,frp,daynight,type\n"
    "-35.3007,149.803,312.9,2,1.4,2026-04-09,0430,Aqua,MODIS,60,61.03,293.3,25.6,D,0\n"
)


def _one(csv_text: str, product: str):
    [record] = parse_firms_csv(csv_text, product, WINDOW["end"], "static", WINDOW)
    return record


# ------------------------------------------------------------------ FIRMS

def test_viirs_carries_the_i4_fire_channel():
    record = _one(VIIRS_CSV, "VIIRS_SNPP_SP")
    assert record.brightness_k == 334.45
    assert "3.74" in record.brightness_channel
    assert "I4" in record.brightness_channel


def test_modis_carries_the_t21_fire_channel():
    """MODIS names the same physical quantity differently, and the label must follow."""
    record = _one(MODIS_CSV, "MODIS_SP")
    assert record.brightness_k == 312.9
    assert "T21" in record.brightness_channel


def test_the_two_instruments_do_not_share_a_channel_label():
    """Guards the whole point of carrying the channel: 3.74 um is not 4 um."""
    viirs = _one(VIIRS_CSV, "VIIRS_SNPP_SP")
    modis = _one(MODIS_CSV, "MODIS_SP")
    assert viirs.brightness_channel != modis.brightness_channel


def test_a_missing_brightness_column_is_absent_rather_than_zero():
    text = ("latitude,longitude,scan,track,acq_date,acq_time,satellite,instrument,"
            "confidence,version,frp,daynight,type\n"
            "-32.2,152.2,0.6,0.71,2026-04-09,0428,N,VIIRS,n,2,6.58,D,0\n")
    record = _one(text, "VIIRS_SNPP_SP")
    assert record.brightness_k is None
    assert record.brightness_channel is None


def test_an_unparseable_brightness_is_absent_rather_than_guessed():
    record = _one(VIIRS_CSV.replace("334.45", "n/a"), "VIIRS_SNPP_SP")
    assert record.brightness_k is None
    assert record.brightness_channel is None


# ------------------------------------------------------------------ DEA

DEA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0"
                       xmlns:public="http://sentinel.ga.gov.au/geoserver/public">
  <wfs:member>
    <public:hotspots>
      <public:id>1</public:id>
      <public:latitude>-32.0</public:latitude>
      <public:longitude>148.0</public:longitude>
      <public:datetime>2026-04-09T04:10:00Z</public:datetime>
      <public:satellite>HIMAWARI-9</public:satellite>
      <public:sensor>AHI</public:sensor>
      <public:power>12.5</public:power>
      <public:confidence>50</public:confidence>
      <public:temp_kelvin>318.7</public:temp_kelvin>
      <public:process_algorithm>BRIGHT AHI</public:process_algorithm>
      <public:process_algorithm_version>1.86</public:process_algorithm_version>
    </public:hotspots>
  </wfs:member>
</wfs:FeatureCollection>
"""


def test_dea_carries_temp_kelvin():
    [record] = parse_wfs_xml(DEA_XML.encode(), WINDOW["end"], "static", WINDOW)
    assert record.brightness_k == 318.7


def test_dea_does_not_invent_a_wavelength_it_was_not_told():
    """The WFS gives a Kelvin value and never says which band. Say so, do not guess."""
    [record] = parse_wfs_xml(DEA_XML.encode(), WINDOW["end"], "static", WINDOW)
    assert record.brightness_channel == "unspecified (DEA temp_kelvin)"
    assert "um" not in record.brightness_channel


def test_dea_without_temp_kelvin_is_absent():
    stripped = DEA_XML.replace(
        "<public:temp_kelvin>318.7</public:temp_kelvin>", "")
    [record] = parse_wfs_xml(stripped.encode(), WINDOW["end"], "static", WINDOW)
    assert record.brightness_k is None
    assert record.brightness_channel is None


# ------------------------------------------------------------------ the model

def test_a_record_built_without_brightness_still_validates(make_detection):
    """Every existing construction site omits these fields and must keep working."""
    record = make_detection()
    assert record.brightness_k is None
    assert record.brightness_channel is None


def test_brightness_survives_attaching_a_footprint(make_detection):
    """`with_footprint` rebuilds the record; the measurement must not be dropped."""
    from shapely.geometry import Polygon

    record = make_detection(brightness_k=331.0, brightness_channel="VIIRS I4 3.74 um")
    attached = record.with_footprint(
        Polygon([(0, 0), (1, 0), (1, 1), (0, 0)]),
        method="polar_reconstructed", model_version="v1",
        status="experimental", side="ambiguous")
    assert attached.brightness_k == 331.0
    assert attached.brightness_channel == "VIIRS I4 3.74 um"
