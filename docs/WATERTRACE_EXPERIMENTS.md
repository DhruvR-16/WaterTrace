# Detection experiment protocol

Recorded 19 October 2026 before running these two new ablations. This is a repository protocol, not external preregistration. The existing 90-chip test set is already exposed: results here are exploratory and cannot establish generalization.

## Fixed comparison

Keep production `surface-water-screen-v1` unchanged. Compare the existing unfiltered VH Otsu baseline with:

1. `filtered_vh_otsu`: 3×3 median, exclude invalid neighborhoods and image border, unbounded Otsu on filtered VH.
2. `filtered_dual_otsu`: identical filtering, water requires both filtered VV and VH below their respective unbounded Otsu thresholds.

No labels enter either method. No parameter sweep, learned weights, threshold margin, component removal or post-result selection. The entire admitted valid neighborhood is assessed for these baselines. All rejected chips remain in the denominator as unknown. Report precision, recall, IoU and assessed fraction pooled and per event, including losses. Unknown predictions count as missed labeled water.

These are stronger *controls for the effect of filtering*, not claimed state-of-the-art flood systems or substitutes for a published learned-model baseline. Do not promote an ablation into production from this exposed-set result.

```sh
.venv/bin/python scripts/evaluate_watertrace.py --split test --experiments --output artifacts/filtered-baselines.json
```

The output path must be new. It includes all scene hashes and confusion counts. The default command retains the original two methods and counts.

## Next scientifically meaningful evaluation

- Obtain independent temporal reference polygons with acquisition times, validity/exclusion masks and redistribution terms. A disaster report is not pixel truth.
- Freeze a new geographic event holdout before inspecting labels. Keep all acquisitions/adjacent chips from an event together; prevent spatial and temporal leakage.
- Select a published flood-mapping model with reproducible preprocessing and compatible training data/license; verify any checkpoint was not trained on the held-out event. Match calibration and input resolution.
- Report event-level distribution and bootstrap intervals, not millions of correlated pixels treated as independent trials. Separate paddy, permanent water, terrain shadow, urban, vegetated flood and missing-baseline cases.
- Compare *new-water candidates* against temporal truth, separately from ordinary surface-water segmentation. Report temporal coverage and missing baseline area even when accuracy is high.
- Any retraining uses development events only. Record checkpoint, environment, seed and hashes; run the frozen holdout once, publish failures, then call it exposed.

No learned-model comparison, new blind test, crop-impact validation or performance gain is claimed by this release.

## Recorded exploratory results

Run 19 October 2026: all 90 chips, 20,517,367 labeled pixels, one rejected scene retained. Original WaterTrace counts unchanged. The filtered controls improve over the crude baseline in pooled IoU but do not justify replacing production: they have much lower precision and higher recall. This strengthens the comparison, not the application’s detection accuracy.

| Method | Precision | Recall | IoU | Assessed |
|---|---:|---:|---:|---:|
| WaterTrace v1 | 75.57% | 52.87% | 45.15% | 68.60% |
| Original VH Otsu | 25.51% | 72.17% | 23.22% | 99.64% |
| Filtered VH Otsu | 26.86% | 74.60% | 24.61% | 98.85% |
| Filtered dual Otsu | 33.87% | 64.90% | 28.63% | 98.85% |

IoU by event (all events shown):

| Event | WaterTrace | VH | Filtered VH | Filtered dual |
|---|---:|---:|---:|---:|
| Ghana | .4089 | .1223 | .1278 | .1848 |
| India | .6636 | .3880 | .3920 | .4446 |
| Mekong | .6800 | .3149 | .3326 | .4354 |
| Nigeria | .6226 | .3003 | .3049 | .3942 |
| Pakistan | .1621 | .2001 | .2079 | .1905 |
| Paraguay | .3438 | .1670 | .1864 | .2134 |
| Somalia | .2430 | .1608 | .1694 | .1577 |
| Spain | .5616 | .4193 | .4315 | .4464 |
| Sri Lanka | .2080 | .2251 | .2792 | .2389 |
| USA | .4015 | .0783 | .0791 | .1148 |

Pakistan and Sri Lanka remain clear weaknesses. Quantized Otsu also has edge cases on nearly constant scenes; these simple baselines are not robust operational alternatives. Use the command above to reproduce full counts and scene hashes; the generated local report is intentionally outside Git.
