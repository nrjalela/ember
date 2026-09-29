"""
EMBER reference fire-behaviour model.

This module is the single source of truth for the maths used by the browser
demo (index.html). Every function here is ported line-for-line to JavaScript;
tests/parity.spec.js checks the port against fixtures exported from this file.

References
----------
McArthur, A.G. (1967) Fire behaviour in eucalypt forests. Leaflet 107,
    Forestry and Timber Bureau, Canberra.
Noble, I.R., Bary, G.A.V. & Gill, A.M. (1980) McArthur's fire-danger meters
    expressed as equations. Australian Journal of Ecology 5, 201-203.
Anderson, H.E. (1983) Predicting wind-driven wild land fire size and shape.
    USDA Forest Service Research Paper INT-305.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

# --------------------------------------------------------------------------
# 1. McArthur Mk5 Forest Fire Danger Index (Noble et al. 1980)
# --------------------------------------------------------------------------


def ffdi(temp_c: float, rh_pct: float, wind_kmh: float, drought_factor: float) -> float:
    """McArthur Mk5 FFDI, algebraic form of Noble et al. (1980).

    FFDI = 2 exp(-0.45 + 0.987 ln(DF) - 0.0345 RH + 0.0338 T + 0.0234 V)
    """
    df = min(max(drought_factor, 0.0), 10.0)
    if df <= 0:
        return 0.0
    return 2.0 * math.exp(
        -0.45 + 0.987 * math.log(df) - 0.0345 * rh_pct + 0.0338 * temp_c + 0.0234 * wind_kmh
    )


# Legacy McArthur FDI categories (used in Australia until the AFDRS, 2022).
# Lower bound is inclusive.
DANGER_BANDS = [
    (0.0, "LOW-MODERATE"),
    (12.0, "HIGH"),
    (25.0, "VERY HIGH"),
    (50.0, "SEVERE"),
    (75.0, "EXTREME"),
    (100.0, "CATASTROPHIC"),
]


def danger_band(index: float) -> str:
    label = DANGER_BANDS[0][1]
    for lower, name in DANGER_BANDS:
        if index >= lower:
            label = name
    return label


# --------------------------------------------------------------------------
# 2. Rate of spread (McArthur Mk5 forest) with slope correction
# --------------------------------------------------------------------------

SLOPE_COEFF = 0.069   # ROS doubles per +10 deg upslope, halves per 10 deg downslope
SLOPE_LIMIT_DEG = 20.0  # McArthur slope correction is not valid beyond ~20 deg


def rate_of_spread(ffdi_value: float, fuel_load_tha: float, slope_deg: float = 0.0) -> float:
    """Head-fire rate of spread in km/h.

    ROS = 0.0012 * FFDI * W * exp(0.069 * slope)
    W is fine-fuel load in t/ha; slope in degrees, positive = upslope.
    """
    if fuel_load_tha <= 0 or ffdi_value <= 0:
        return 0.0
    s = min(max(slope_deg, -SLOPE_LIMIT_DEG), SLOPE_LIMIT_DEG)
    return 0.0012 * ffdi_value * fuel_load_tha * math.exp(SLOPE_COEFF * s)


# --------------------------------------------------------------------------
# 3. Directional spread: ellipse with the ignition point at the rear focus
# --------------------------------------------------------------------------
# R(theta) = R_head * (1 - e) / (1 - e cos theta)      (Anderson 1983 shape)
# head:back ratio = (1 + e) / (1 - e)
# Eccentricity grows with wind: e = 1 - exp(-K_WIND * V).
# K_WIND is calibrated so head:back = 4:1 at the 30 km/h reference wind.

REF_WIND_KMH = 30.0
REF_HEAD_BACK_RATIO = 4.0
_E_REF = (REF_HEAD_BACK_RATIO - 1.0) / (REF_HEAD_BACK_RATIO + 1.0)  # 0.6
K_WIND = -math.log(1.0 - _E_REF) / REF_WIND_KMH


def eccentricity(wind_kmh: float) -> float:
    return 1.0 - math.exp(-K_WIND * max(wind_kmh, 0.0))


def direction_factor(wind_kmh: float, cos_theta: float) -> float:
    """Fraction of head-fire ROS in a direction at angle theta to the wind."""
    e = eccentricity(wind_kmh)
    return (1.0 - e) / (1.0 - e * cos_theta)


def spread_vector(wind_from_deg: float) -> tuple[float, float]:
    """Unit vector (x east, y south/down-grid) the fire is pushed toward.

    Wind direction is meteorological: the bearing the wind blows FROM.
    """
    to = math.radians(wind_from_deg + 180.0)
    return math.sin(to), -math.cos(to)


# --------------------------------------------------------------------------
# 4. Cellular-automaton spread (minimum travel time)
# --------------------------------------------------------------------------
# Each cell holds an ignition clock. When a cell ignites it offers every
# neighbour a candidate ignition time t + distance / ROS(direction, slope,
# fuel); a neighbour ignites at the earliest offer. 16-neighbour stencil
# (8 adjacent + 8 knight moves) keeps the burn-scar shape close to the true
# ellipse. Knight moves need both cells they pass between to be burnable,
# so fire cannot jump water or breaks.

NEIGHBOURS = [
    (1, 0), (-1, 0), (0, 1), (0, -1),
    (1, 1), (1, -1), (-1, 1), (-1, -1),
    (2, 1), (2, -1), (-2, 1), (-2, -1),
    (1, 2), (1, -2), (-1, 2), (-1, -2),
]


@dataclass
class Landscape:
    nx: int
    ny: int
    cell_m: float
    fuel: list[float]   # t/ha, row-major; 0 = unburnable
    elev: list[float]   # metres, row-major


@dataclass
class Weather:
    temp_c: float
    rh_pct: float
    wind_kmh: float
    drought_factor: float
    wind_from_deg: float

    @property
    def ffdi(self) -> float:
        return ffdi(self.temp_c, self.rh_pct, self.wind_kmh, self.drought_factor)


def _knight_passable(land: Landscape, x: int, y: int, dx: int, dy: int) -> bool:
    if abs(dx) == 2:
        sx = x + dx // 2
        return land.fuel[y * land.nx + sx] > 0 and land.fuel[(y + dy) * land.nx + sx] > 0
    sy = y + dy // 2
    return land.fuel[sy * land.nx + x] > 0 and land.fuel[sy * land.nx + x + dx] > 0


def arrival_times(
    land: Landscape,
    wx: Weather,
    sources: list[tuple[int, float]],
    t_now: float = 0.0,
) -> list[float]:
    """Ignition time (hours) of every cell; inf if never reached.

    sources: (cell index, ignition time) of cells already alight. Offers made
    to unburnt cells are never earlier than t_now, so the field can be
    recomputed mid-fire after a weather change.
    """
    n = land.nx * land.ny
    t = [math.inf] * n
    fixed = [False] * n
    heap: list[tuple[float, int]] = []
    for i, ts in sources:
        if land.fuel[i] > 0 and ts < t[i]:
            t[i] = ts
            fixed[i] = True
            heapq.heappush(heap, (ts, i))

    index = wx.ffdi
    ux, uy = spread_vector(wx.wind_from_deg)
    cell_km = land.cell_m / 1000.0

    while heap:
        ti, i = heapq.heappop(heap)
        if ti > t[i]:
            continue
        x, y = i % land.nx, i // land.nx
        for dx, dy in NEIGHBOURS:
            nx_, ny_ = x + dx, y + dy
            if nx_ < 0 or ny_ < 0 or nx_ >= land.nx or ny_ >= land.ny:
                continue
            j = ny_ * land.nx + nx_
            if fixed[j] or land.fuel[j] <= 0:
                continue
            if (abs(dx) == 2 or abs(dy) == 2) and not _knight_passable(land, x, y, dx, dy):
                continue
            dist = math.hypot(dx, dy)
            slope = math.degrees(math.atan((land.elev[j] - land.elev[i]) / (dist * land.cell_m)))
            cos_theta = (dx * ux + dy * uy) / dist
            r = rate_of_spread(index, land.fuel[j], slope) * direction_factor(wx.wind_kmh, cos_theta)
            if r <= 0:
                continue
            cand = max(t_now, ti + dist * cell_km / r)
            if cand < t[j]:
                t[j] = cand
                heapq.heappush(heap, (cand, j))
    return t


def uniform_landscape(nx: int, ny: int, fuel: float = 20.0, cell_m: float = 100.0) -> Landscape:
    return Landscape(nx, ny, cell_m, [fuel] * (nx * ny), [0.0] * (nx * ny))
