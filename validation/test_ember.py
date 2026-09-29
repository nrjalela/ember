import math
import random

import pytest

from ember_model import (
    Landscape,
    Weather,
    arrival_times,
    danger_band,
    direction_factor,
    ffdi,
    rate_of_spread,
    uniform_landscape,
)

# ---------------------------------------------------------------- FFDI


def test_ffdi_black_saturday_reference():
    # 46 C, 6 % RH, 55 km/h, DF 10 -> ~172
    assert ffdi(46, 6, 55, 10) == pytest.approx(172.5, abs=1.0)


def test_ffdi_monotonic_in_each_driver():
    base = ffdi(30, 20, 30, 8)
    assert ffdi(35, 20, 30, 8) > base
    assert ffdi(30, 10, 30, 8) > base
    assert ffdi(30, 20, 40, 8) > base
    assert ffdi(30, 20, 30, 9) > base


def test_ffdi_zero_drought_factor_is_zero():
    assert ffdi(40, 10, 50, 0) == 0.0


@pytest.mark.parametrize(
    "value,band",
    [
        (0, "LOW-MODERATE"),
        (11.9, "LOW-MODERATE"),
        (12, "HIGH"),
        (24.9, "HIGH"),
        (25, "VERY HIGH"),
        (50, "SEVERE"),
        (75, "EXTREME"),
        (99.9, "EXTREME"),
        (100, "CATASTROPHIC"),
        (172.5, "CATASTROPHIC"),
    ],
)
def test_legacy_mcarthur_bands(value, band):
    assert danger_band(value) == band


# ---------------------------------------------------------------- ROS


def test_ros_formula():
    assert rate_of_spread(50, 20) == pytest.approx(0.0012 * 50 * 20)


def test_ros_linear_in_ffdi_and_fuel():
    assert rate_of_spread(100, 20) == pytest.approx(2 * rate_of_spread(50, 20))
    assert rate_of_spread(50, 30) == pytest.approx(3 * rate_of_spread(50, 10))


def test_ros_slope_doubles_per_10_degrees():
    flat = rate_of_spread(50, 20, 0)
    assert rate_of_spread(50, 20, 10) / flat == pytest.approx(2.0, rel=0.01)
    assert rate_of_spread(50, 20, -10) / flat == pytest.approx(0.5, rel=0.01)


def test_ros_slope_clamped_at_20_degrees():
    assert rate_of_spread(50, 20, 35) == rate_of_spread(50, 20, 20)


def test_ros_no_fuel_no_spread():
    assert rate_of_spread(150, 0) == 0.0


def test_direction_factor_head_back_ratio_at_reference_wind():
    assert direction_factor(30, 1) / direction_factor(30, -1) == pytest.approx(4.0)
    assert direction_factor(30, 1) == pytest.approx(1.0)
    assert direction_factor(0, -1) == pytest.approx(1.0)


# ---------------------------------------------------------------- CA spread


def _burn(land, wx, t_end):
    cx, cy = land.nx // 2, land.ny // 2
    t = arrival_times(land, wx, [(cy * land.nx + cx, 0.0)])
    cells = [(i % land.nx, i // land.nx) for i, ti in enumerate(t) if ti <= t_end]
    return cx, cy, cells


def _extents(cx, cy, cells):
    xs = [x for x, _ in cells]
    ys = [y for _, y in cells]
    return max(xs) - cx, cx - min(xs), max(ys) - cy, cy - min(ys)


def _t_for_head_cells(wx, fuel, cells):
    return cells * 0.1 / rate_of_spread(wx.ffdi, fuel)


WEST_30 = Weather(temp_c=35, rh_pct=15, wind_kmh=30, drought_factor=9, wind_from_deg=270)


def test_ca_downwind_is_about_4x_upwind():
    land = uniform_landscape(241, 241)
    cx, cy, cells = _burn(land, WEST_30, _t_for_head_cells(WEST_30, 20, 80))
    down, up, _, _ = _extents(cx, cy, cells)
    ratio = down / up
    print(f"downwind {down} cells, upwind {up} cells, ratio {ratio:.2f}")
    assert 3.0 <= ratio <= 5.0


def test_ca_burn_scar_is_elliptical():
    land = uniform_landscape(241, 241)
    cx, cy, cells = _burn(land, WEST_30, _t_for_head_cells(WEST_30, 20, 80))
    down, up, south, north = _extents(cx, cy, cells)
    length, width = down + up + 1, south + north + 1
    # Symmetric about the wind axis
    assert abs(south - north) <= 1
    # Longer along the wind than across it
    assert length > width
    # Area matches pi*a*b of the bounding ellipse within 10 %
    ellipse_area = math.pi * (length / 2) * (width / 2)
    assert len(cells) == pytest.approx(ellipse_area, rel=0.10)


def test_ca_ratio_holds_with_heterogeneous_fuel():
    rng = random.Random(42)
    nx = ny = 241
    land = Landscape(nx, ny, 100.0, [rng.uniform(15, 25) for _ in range(nx * ny)], [0.0] * (nx * ny))
    cx, cy, cells = _burn(land, WEST_30, _t_for_head_cells(WEST_30, 20, 80))
    down, up, _, _ = _extents(cx, cy, cells)
    assert 3.0 <= down / up <= 5.0


def test_ca_wind_direction_rotates_spread():
    wx = Weather(35, 15, 30, 9, wind_from_deg=0)  # northerly -> fire runs south
    land = uniform_landscape(121, 121)
    cx, cy, cells = _burn(land, wx, _t_for_head_cells(wx, 20, 40))
    _, _, south, north = _extents(cx, cy, cells)
    assert 3.0 <= south / north <= 5.0


def test_ca_calm_wind_is_circular():
    wx = Weather(35, 15, 0, 9, wind_from_deg=270)
    land = uniform_landscape(121, 121)
    cx, cy, cells = _burn(land, wx, _t_for_head_cells(wx, 20, 40))
    down, up, south, north = _extents(cx, cy, cells)
    assert down == up == south == north
    assert len(cells) == pytest.approx(math.pi * 40.5**2, rel=0.08)


def test_ca_runs_faster_upslope():
    nx = ny = 121
    rise = math.tan(math.radians(10)) * 100.0  # 10 deg slope rising to the east
    elev = [(i % nx) * rise for i in range(nx * ny)]
    land = Landscape(nx, ny, 100.0, [20.0] * (nx * ny), elev)
    wx = Weather(35, 15, 0, 9, 270)
    cx, cy, cells = _burn(land, wx, _t_for_head_cells(wx, 20, 20))
    upslope, downslope, _, _ = _extents(cx, cy, cells)
    # Theory: exp(0.069*10) / exp(-0.069*10) = 3.97
    assert upslope / downslope == pytest.approx(3.97, rel=0.2)


def test_ca_water_is_a_firebreak():
    nx = ny = 81
    fuel = [20.0] * (nx * ny)
    for y in range(ny):
        for x in (50, 51):  # two-cell-wide river
            fuel[y * nx + x] = 0.0
    land = Landscape(nx, ny, 100.0, fuel, [0.0] * (nx * ny))
    t = arrival_times(land, WEST_30, [(40 * nx + 20, 0.0)])
    assert all(math.isinf(t[y * nx + x]) for y in range(ny) for x in range(50, nx))
    assert not math.isinf(t[40 * nx + 49])


def test_ca_higher_ffdi_burns_more():
    land = uniform_landscape(121, 121)
    mild = Weather(25, 40, 30, 5, 270)
    severe = Weather(42, 8, 30, 10, 270)
    t_end = 1.0
    _, _, a = _burn(land, mild, t_end)
    _, _, b = _burn(land, severe, t_end)
    assert len(b) > len(a)


def test_ca_recompute_mid_fire_never_backdates():
    land = uniform_landscape(61, 61)
    t0 = arrival_times(land, WEST_30, [(30 * 61 + 30, 0.0)])
    t_now = 0.2
    burning = [(i, ti) for i, ti in enumerate(t0) if ti <= t_now]
    change = Weather(30, 25, 35, 9, wind_from_deg=225)  # SW change
    t1 = arrival_times(land, change, burning, t_now=t_now)
    for i, ti in enumerate(t1):
        if t0[i] > t_now:
            assert ti >= t_now
        else:
            assert ti == t0[i]
