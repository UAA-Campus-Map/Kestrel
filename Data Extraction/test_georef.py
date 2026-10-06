"""Tests for georef.py. Run from this folder with: python -m pytest test_georef.py"""

import numpy as np
import pytest

import georef

ESH = (-149.83210, 61.18871)  # roughly Eugene Short Hall


def synthetic(scale=0.0254, rotation_deg=17.0, n=12, seed=1):
    """CAD points plus the lon/lat a known transform sends them to."""
    rng = np.random.default_rng(seed)
    cad = rng.uniform([2800, 450], [5000, 1300], size=(n, 2))
    truth = {"type": "similarity", "cad_ref": [3900.0, 875.0], "ref_lonlat": list(ESH),
             "scale_m_per_unit": scale, "rotation_deg": rotation_deg}
    return cad, georef.apply(truth, cad)


def test_plane_round_trip():
    lonlat = np.array([[-149.8325, 61.1886], [-149.8317, 61.1888], ESH])
    back = georef.from_plane(georef.to_plane(lonlat, ESH), ESH)
    assert np.allclose(back, lonlat, atol=1e-12)


def test_plane_distance_matches_known_length():
    # 0.001 degree of latitude at 61 N is about 111.43 m on WGS84
    en = georef.to_plane(np.array([[ESH[0], ESH[1] + 0.001]]), ESH)
    assert en[0, 1] == pytest.approx(111.43, abs=0.01)


# The fit centers its local plane on the points, not on the synthetic truth's
# reference, so results differ by ~1e-8 relative (micrometers on a building).

def test_recovers_synthetic_transform():
    cad, lonlat = synthetic()
    t = georef.fit_similarity(cad, lonlat)
    assert t["scale_m_per_unit"] == pytest.approx(0.0254, rel=1e-6)
    assert t["rotation_deg"] == pytest.approx(17.0, abs=1e-4)
    assert georef.residuals_m(t, cad, lonlat).max() < 1e-3


def test_locked_scale_still_recovers_rotation():
    cad, lonlat = synthetic(rotation_deg=-3.5)
    t = georef.fit_similarity(cad, lonlat, scale=0.0254)
    assert t["scale_m_per_unit"] == 0.0254
    assert t["rotation_deg"] == pytest.approx(-3.5, abs=1e-4)
    assert georef.residuals_m(t, cad, lonlat).max() < 1e-3


def test_outlier_is_flagged_not_dropped():
    cad, lonlat = synthetic(n=20)
    rng = np.random.default_rng(2)
    noisy = georef.from_plane(georef.to_plane(lonlat, ESH) + rng.normal(0, 0.5, size=(20, 2)), ESH)
    noisy[7] = georef.from_plane(georef.to_plane(noisy[7:8], ESH) + [15.0, 0.0], ESH)[0]
    t = georef.fit_similarity(cad, noisy)
    res = georef.residuals_m(t, cad, noisy)
    assert georef.flag_outliers(res) == [7]
    assert len(res) == 20


def test_apply_maps_cad_ref_to_ref_lonlat():
    cad, lonlat = synthetic()
    t = georef.fit_similarity(cad, lonlat)
    assert np.allclose(georef.apply(t, [t["cad_ref"]])[0], t["ref_lonlat"], atol=1e-9)
