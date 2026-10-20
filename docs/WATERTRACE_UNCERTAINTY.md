# Uncertainty audit protocol

Recorded before executing this audit on 19 October 2026. This is a repository
protocol, not external preregistration. The existing 90-chip benchmark is exposed;
this audit cannot establish unseen-event generalization.

Keep `surface-water-screen-v1` and all baseline parameters unchanged. Use every
record in the existing four-method experimental report, including rejected chips.
Compute coverage, errors divided by assessed labeled pixels (selective error),
full-coverage precision/recall/IoU and the share of labeled water left unassessed.
An all-abstaining method has zero coverage and undefined selective error, not
perfect accuracy. Unknown water remains a miss in full-coverage recall/IoU.

Report every event. For exploratory 95% percentile intervals, sample whole event
groups with replacement, retaining all chips within each sampled event. Use 2,000
replicates and seed 20261019. Each replicate pools counts before computing rates.
Do not resample individual pixels as independent observations. Report the number
of defined bootstrap replicates per metric; undefined ratios are not zero.

Methods assess different pixel subsets: comparing their selective errors is not
a controlled estimate of the benefit of abstention. No threshold sweep, tuned
parameter, probability calibration or accuracy-coverage curve is claimed. Ten
events give limited statistical support; these intervals are descriptive of this
exposed sample, not deployment guarantees or evidence of statistical superiority.

Independent event holdout, a published learned baseline with verified training
provenance, and date-matched temporal truth remain separate unfinished work.

## Reproduce

After installing the pinned development dependencies and downloading the test
split as described in the README:

```sh
make verify
make reproduce OUT=artifacts/uncertainty-reproduction
```

The output directory must be new and its parent must exist. No network requests
or cloud resources are needed for these commands. The audit consumes the complete
four-method evaluator report and records its SHA-256. This is local consistency,
not independent authentication. Retain the evaluation JSON alongside the audit.
Both commands publish complete private reports without overwriting existing
paths, using same-directory staging and exclusive hard links. A handled publication
failure removes staging and leaves no partial destination. Hard-link support is
required; crash leftovers and power-loss durability have the same limitations
as CLI exports documented in the README.

## Recorded results — 19 October 2026

All 90 chips across 10 events; rejected observations remain in the denominator.
The production detector was not changed.

| Method | Assessed coverage | Error within assessed pixels | Labeled water left unassessed | Full water recall |
|---|---:|---:|---:|---:|
| WaterTrace | 68.60% | 5.39% | 34.68% | 52.87% |
| VH Otsu | 99.64% | 29.70% | 1.99% | 72.17% |
| Filtered VH Otsu | 98.85% | 28.57% | 2.78% | 74.60% |
| Filtered dual Otsu | 98.85% | 20.12% | 2.78% | 64.90% |

WaterTrace's exploratory event-bootstrap intervals: coverage **60.55–76.44%**,
selective error **3.78–8.22%**, water recall **37.81–64.10%**, IoU
**30.73–57.15%**, water abstention **24.72–48.85%**. All 2,000 replicates have
defined denominators for these metrics. Full per-event rates and all-method
intervals are in the generated report; they are not selectively suppressed.

**Interpretation:** lower error on the subset assessed accompanies substantial
coverage loss and missed water. Different subsets and class balance prevent a
causal superiority claim. This is not “94.6% flood accuracy,” a calibrated
confidence score, or new evidence of generalization. The broad event intervals
reinforce that pooled results hide geographic variation.
