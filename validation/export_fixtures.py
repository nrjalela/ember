"""Export reference outputs used by tests/parity.spec.js to check the JS port."""

import json
import math
import random
from pathlib import Path

from ember_model import Landscape, Weather, arrival_times, danger_band, ffdi, rate_of_spread

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "parity.json"


def main():
    ffdi_cases = []
    for t, rh, v, df in [(46, 6, 55, 10), (22, 45, 15, 4), (35, 20, 30, 8), (41, 8, 50, 10), (30, 60, 5, 2)]:
        f = ffdi(t, rh, v, df)
        ffdi_cases.append({"t": t, "rh": rh, "v": v, "df": df, "ffdi": f, "band": danger_band(f)})

    ros_cases = [
        {"ffdi": f, "w": w, "slope": s, "ros": rate_of_spread(f, w, s)}
        for f, w, s in [(172.5, 20, 0), (50, 12, 8), (30, 5, -15), (100, 25, 30)]
    ]

    # Small landscape with a hill, a river and noisy fuel
    rng = random.Random(7)
    nx, ny = 41, 31
    fuel, elev = [], []
    for y in range(ny):
        for x in range(nx):
            elev.append(300 * math.exp(-((x - 28) ** 2 + (y - 10) ** 2) / 60.0))
            fuel.append(0.0 if x in (12, 13) and y > 8 else round(rng.uniform(5, 25), 3))
    land = Landscape(nx, ny, 100.0, fuel, elev)
    wx = Weather(40, 10, 45, 10, 315)
    sources = [(15 * nx + 20, 0.0), (25 * nx + 5, 0.1)]
    arrival = arrival_times(land, wx, sources)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "ffdi": ffdi_cases,
        "ros": ros_cases,
        "spread": {
            "nx": nx, "ny": ny, "cellM": 100.0, "fuel": fuel, "elev": elev,
            "weather": {"temp": 40, "rh": 10, "wind": 45, "df": 10, "windFrom": 315},
            "sources": [{"i": i, "t": t} for i, t in sources],
            "arrival": [None if math.isinf(a) else a for a in arrival],
        },
    }))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
