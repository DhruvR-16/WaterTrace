"""Evaluate water screening against independent Sen1Floods11 labels.

Never use label NoData to alter inference. Unknown predictions count as missed
water in full-coverage recall/IoU. This does NOT evaluate crop damage or new floods.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import cv2
import rasterio
from watertrace.engine import POLICY, InvalidRaster, classify, otsu_db, read_raster


def metrics(prediction, truth, assessed):
    valid = truth >= 0
    wet = truth == 1
    tp = int(np.sum(valid & prediction & wet))
    fp = int(np.sum(valid & prediction & ~wet))
    fn = int(np.sum(valid & ~prediction & wet))
    tn = int(np.sum(valid & ~prediction & ~wet))
    return dict(tp=tp, fp=fp, fn=fn, tn=tn, labeled=int(valid.sum()), assessed=int((valid & assessed).sum()),
                unknown_water=int((valid & wet & ~assessed).sum()))


def rates(counts):
    tp,fp,fn = (counts[k] for k in ("tp","fp","fn"))
    return {**counts, "precision":tp/(tp+fp) if tp+fp else None, "recall":tp/(tp+fn) if tp+fn else None,
            "iou":tp/(tp+fp+fn) if tp+fp+fn else None,
            "assessed_fraction":counts["assessed"]/counts["labeled"] if counts["labeled"] else None}


def experimental_baselines(raster):
    """Fixed diagnostic ablations, never used by the application or tuned on labels."""
    valid = cv2.erode(raster.valid.astype(np.uint8), np.ones((3, 3), np.uint8),
                      borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
    water = []
    for band in raster.bands:
        filled = np.where(raster.valid, band, np.median(band[raster.valid])).astype(np.float32)
        filtered = cv2.medianBlur(filled, 3)
        water.append((filtered < otsu_db(filtered, valid)) & valid if valid.any() else np.zeros(valid.shape, bool))
    return {'filtered_vh_otsu': (water[1], valid), 'filtered_dual_otsu': (water[0] & water[1], valid)}


def evaluate(data, split, *, experiments=False):
    manifest_path = data / (split+"-manifest.json")
    manifest = json.loads(manifest_path.read_text())
    records = []
    started = time.perf_counter()
    for image, label in manifest["pairs"]:
        raw = (data/"data/flood_events/HandLabeled/S1Hand"/image).read_bytes()
        with rasterio.open(data/"data/flood_events/HandLabeled/LabelHand"/label) as src:
            truth = src.read(1)
            label_crs, label_transform = src.crs, src.transform
        with rasterio.open(data/"data/flood_events/HandLabeled/S1Hand"/image) as src:
            if truth.shape != (src.height, src.width) or src.crs != label_crs or not src.transform.almost_equals(label_transform, precision=1e-10):
                raise ValueError("Label alignment mismatch")
        rejection = None
        try:
            raster = read_raster(raw)
            classes, _ = classify(raster)
            vh = raster.bands[1]
            baseline = (vh < otsu_db(vh, raster.valid)) & raster.valid
            baseline_valid = raster.valid
            experimental = experimental_baselines(raster) if experiments else {}
        except InvalidRaster as exc:
            # Rejected observations remain in the denominator, entirely unknown.
            rejection = str(exc)
            classes = np.zeros(truth.shape, np.uint8)
            baseline = baseline_valid = np.zeros(truth.shape, bool)
            experimental = {k: (baseline, baseline_valid) for k in ('filtered_vh_otsu', 'filtered_dual_otsu')} if experiments else {}
        records.append({"image":image, "sha256":hashlib.sha256(raw).hexdigest(), "event":image.split("_")[0],
                        "rejection":rejection,
                        "watertrace":metrics(classes==2,truth,classes!=0), "vh_otsu":metrics(baseline,truth,baseline_valid)})
        records[-1].update({k: metrics(prediction, truth, assessed) for k, (prediction, assessed) in experimental.items()})
    methods = ('watertrace', 'vh_otsu', 'filtered_vh_otsu', 'filtered_dual_otsu') if experiments else ('watertrace', 'vh_otsu')
    def summary(rows):
        return {method:rates({key:sum(r[method][key] for r in rows) for key in rows[0][method]}) for method in methods}
    return {"policy":POLICY, "split":split, "chips":len(records), "rejected_chips":sum(r["rejection"] is not None for r in records), "scope":"Water/no-water labels, not flood onset, agricultural impact, or inspection success.",
            "protocol":"NoData truth excluded only during scoring. Unknown predictions count as negatives in full recall/IoU. Rejected scenes are entirely unknown for all methods and remain in scoring. Baseline is unfiltered VH Otsu under the same input-admission policy." + (" Diagnostic ablations: fixed 3x3 median and valid-neighborhood erosion; unbounded Otsu on VH or agreement of VV and VH. No margin or component filtering. Exposed-test exploratory comparison, not blind validation or a learned-model benchmark." if experiments else ''),
            "manifest_sha256":hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "pooled":summary(records), "by_event":{event:summary([r for r in records if r["event"]==event]) for event in sorted({r["event"] for r in records})},
            "elapsed_seconds":round(time.perf_counter()-started,3), "cases":records}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["demo","valid","test"], default="test")
    parser.add_argument("--data", type=Path, default=ROOT/"data/watertrace")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--experiments", action="store_true", help="Include fixed median-filtered VH and dual-band Otsu diagnostic ablations. Does not change inference.")
    args = parser.parse_args()
    report = evaluate(args.data, args.split, experiments=args.experiments)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as output:
            json.dump(report, output, indent=2, allow_nan=False)
            output.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k != "cases"}, indent=2, allow_nan=False))
