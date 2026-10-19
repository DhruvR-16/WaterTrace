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
