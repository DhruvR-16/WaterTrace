# WaterTrace v1 benchmark

Evaluated locally on 15 October 2026. [Machine-readable counts, case hashes and results](benchmarks/watertrace-v1.json).

## Protocol

- All 90 chips of Sen1Floods11 v1.1 `flood_test_data.csv`; 10 events, 20,517,367 labeled pixels. No post-hoc scene selection.
- Classification policy frozen in commit `51ea204` before the test run. The first attempt stopped at an insufficient-valid-data scene; the evaluator was corrected to retain rejected scenes as wholly unknown and to verify CRS/transform alignment as well as shape. Inference thresholds were not changed after viewing test scores.
- Only Sentinel-1 VV/VH pixels enter classification. Label NoData (-1) is excluded **only when scoring**. The model does not get the truth mask.
- Prediction 2 is water. Prediction 1 and unknown 0 count as negative in full-coverage recall/IoU. Thus unknown water is a false negative, not a free abstention.
- All scenes share the same input-admission policy for both methods. Rejected scene: `Paraguay_34417_S1Hand.tif`. It remains in the denominator for both methods, with no assessed pixels.
- Baseline: raw VH Otsu on the same fixed quantization range, no dual-band agreement, spatial filtering or component rule. This is a simple ablation reference, not a state-of-the-art comparator.
- Precision = TP/(TP+FP), recall = TP/(TP+FN), IoU = TP/(TP+FP+FN). Undefined ratios are null. Assessed fraction is evaluated on labeled pixels; the UI's scene coverage includes all scene pixels, so they are not interchangeable.
- Test scenes are separate chips but not an event-disjoint geographic holdout from all development examples. Correlated pixels are not independent trials. No confidence interval or statistical significance claim is made.

## Pooled results

| Method | Precision | Recall | IoU | Assessed fraction |
|---|---:|---:|---:|---:|
| WaterTrace v1 | 75.57% | 52.87% | 45.15% | 68.60% |
| VH Otsu | 25.51% | 72.17% | 23.22% | 99.64% |

WaterTrace: TP 1,356,572; FP 438,521; FN 1,209,529; TN 17,512,745. Of the false negatives, 889,876 water pixels were unknown. Higher precision does not erase this recall cost.

## Every event

| Event | Precision | Recall | WaterTrace IoU | Baseline IoU | Assessed fraction |
|---|---:|---:|---:|---:|---:|
| Ghana | 87.2% | 43.5% | 40.9% | 12.2% | 74.1% |
| India | 94.4% | 69.1% | 66.4% | 38.8% | 82.6% |
| Mekong | 96.2% | 69.9% | 68.0% | 31.5% | 88.7% |
| Nigeria | 96.3% | 63.8% | 62.3% | 30.0% | 65.4% |
| Pakistan | 33.1% | 24.1% | 16.2% | 20.0% | 58.6% |
| Paraguay | 56.2% | 46.9% | 34.4% | 16.7% | 71.7% |
| Somalia | 39.1% | 39.1% | 24.3% | 16.1% | 46.4% |
| Spain | 86.3% | 61.7% | 56.2% | 41.9% | 68.9% |
| Sri-Lanka | 84.1% | 21.7% | 20.8% | 22.5% | 71.5% |
| USA | 46.0% | 75.8% | 40.2% | 7.8% | 52.3% |

Pakistan and Sri Lanka are explicit failures relative to the baseline's IoU. Sri Lanka recall is only 21.7%; do not present pooled precision as universal reliability. Terrain, vegetation and calibration effects are plausible error sources, not diagnoses proven by this evaluation.

## Limits and next evaluation

These labels distinguish water/no-water, not newly flooded farmland, crop damage, depth, irrigation intent, duration or access safety. No field-boundary ground truth or human task-time study was run. No learned/published flood model comparison was run. Runtime measurements include local environment effects and are not a cloud/backend benchmark.

The test data are now exposed. Further tuning must use training/validation data and a **new event-disjoint blind evaluation** before renewed held-out generalization claims. Keep this frozen v1 result as a regression baseline. Evaluate threshold/abstention trade-offs and agricultural context separately, without excluding difficult scenes.

## Reproduce

```sh
.venv/bin/python scripts/fetch_watertrace_data.py --split test
.venv/bin/python scripts/evaluate_watertrace.py --split test --output artifacts/reproduction.json
```

Compare counts and input hashes with the tracked JSON. Elapsed time is not a correctness assertion. Missing files or label-grid mismatch fail the evaluator; rejection by the inference admission rules is counted explicitly. Downloads and raw labels are not committed.
