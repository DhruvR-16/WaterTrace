"""Allowlisted public examples. No client-supplied paths or network requests."""
import os
from pathlib import Path

import numpy as np
import rasterio

from watertrace.service import png

DATA = Path(os.getenv("WATERTRACE_DATA", str(Path(__file__).resolve().parents[1]/"data"/"watertrace")))
RASTERS = DATA / "data/flood_events/HandLabeled"
EXAMPLES = [
    {"id":"india", "title":"Northeast India", "region":"India · historical flood-event imagery", "chip":"India_285297", "date":"2016-08-12", "optical_date":"2016-08-12", "orbit":77},
    {"id":"spain", "title":"Eastern Spain", "region":"Spain · historical flood-event imagery", "chip":"Spain_5923267", "date":"2019-09-17", "optical_date":"2019-09-18", "orbit":110},
    {"id":"usa", "title":"Central United States", "region":"USA · historical flood-event imagery", "chip":"USA_994009", "date":"2019-05-22", "optical_date":"2019-05-22", "orbit":136},
]


def examples():
    return [{**item, "available": radar_path(item).is_file()} for item in EXAMPLES]


def radar_path(item):
    return RASTERS / "S1Hand" / (item["chip"] + "_S1Hand.tif")


def optical_preview(item):
    path = RASTERS / "S2Hand" / (item["chip"] + "_S2Hand.tif")
    if not path.is_file():
        return None
    with rasterio.open(path) as source:
        # Sen1Floods11 S2: B2, B3, B4 are bands 2, 3, 4. OpenCV encoder expects BGR.
        bgr = source.read([2,3,4]).transpose(1,2,0).astype(float)
        bgr = np.clip(bgr / 3000, 0, 1) ** (1/1.4)
        return png(np.rint(bgr*255).astype(np.uint8))


def find_example(identifier):
    return next((item for item in EXAMPLES if item["id"] == identifier), None)
