# Evidence Lab: a bounded regional showcase

**Purpose:** demonstrate an inspectable review workflow, including what it cannot conclude. India is the starting region; Spain and the USA provide additional historical context. Pakistan and Sri Lanka supply selected difficult evaluation examples. These are individual dataset scenes—not country-wide coverage, agricultural validation or live monitoring.

## Run

Follow the main README setup, then run `python scripts/fetch_watertrace_data.py --split lab` using the virtual environment. Open **Evidence Lab** in the top bar. The nine synthetic exercises need no dataset download; the four real replays require approximately 6.8 MB. For headless checks, run `python scripts/check_watertrace_lab.py` (optional `--output artifacts/lab-checks.json`, refuses overwrite).

## Real contrast cases

All four were selected **after inspecting the exposed v1 test results**. The stronger India chip is the highest-IoU India chip in that set. The others are handpicked failures. Never average these four into a general accuracy claim; use the complete [90-chip benchmark](WATERTRACE_BENCHMARK.md), which also is no longer blind for future development.

| Case / acquisition | Chip | Precision | Recall | IoU | What to inspect |
|---|---|---:|---:|---:|---|
| India, 2016-08-12 | India_80221 | 95.5% | 92.6% | 88.8% | Stronger overlap, but still 4,983 false alarms and 8,440 missed-water pixels |
| India, 2016-08-12 | India_44475 | 0.0% | N/A | 0.0% | 30 false alarms; no labeled water, so recall is undefined |
| Pakistan, 2017-06-28 | Pakistan_167553 | 0.7% | 21.5% | 0.7% | 41,873 false alarms; a plausible-looking map can be wrong |
| Sri Lanka, 2017-05-30 | Sri-Lanka_534068 | 99.6% | 1.0% | 1.0% | 254,594 missed-water pixels; high precision alone is misleading |

Values are computed from current inference, not inserted as UI fixtures. Water predicted on a water label is a true positive; water predicted on no-water is a false positive; a water label without a water prediction is missed, including unknown predictions. Unlabeled pixels are excluded only during scoring. Precision, recall and IoU are null when their denominators are zero. Reference labels are not flawless ground truth and do not measure crop damage.

**Error map:** blue = correct water; coral = false alarm; violet = missed water, including unknown; grey = labeled no-water without a water prediction (possibly unknown); dark = unlabeled. Reference/error views suppress the inference overlay to avoid mixing meanings. The scene-level assessability card uses all scene pixels, while lab metrics use labeled pixels.

## Synthetic hard cases

| Exercise | Expected handling |
|---|---|
| New-water candidate | Detect a candidate from a matched earlier dry/current wet pair; no damage or duration claim |
| Water at both dates | No new-water candidate; two endpoints do not establish permanent water |
| Missing earlier pixels | Keep water without a baseline visible; zero new-water candidates must not imply no new flooding |
| Rice / paddy context | Ask for crop stage and intentional inundation context; do not infer crop loss |
| Conflicting radar bands | Preserve unknowns and withhold whole-zone conclusions |
| Four-pixel zone | Keep measurements inspectable but fail the resolution gate |
| Just outside the image | Withhold a whole-zone conclusion even when less than 1% of the boundary area is outside; assessed-pixel quality is not boundary coverage |
| Shifted grid | Reject before producing a change map, queue or export |
| All-NoData scene | Reject rather than produce a safe-looking no-water result |

These artificial 96×96 scenes exercise the actual ingestion/classification/report pipeline. Geometry and dates are synthetic; they do not simulate real acquisition physics or prove robustness to the full distribution of these conditions. In particular, the paddy exercise tests a supplied crop-context gate, not automatic paddy recognition.

## A concise walkthrough

1. Start with Northeast India. Explain actual radar, optical context, dates, unknown pixels and illustrative—not farm—zones.
2. Open the stronger India replay. Show the selection disclosure before discussing its numbers. Switch between radar, reference labels and errors.
3. Show Sri Lanka next: contrast 99.6% precision with 1.0% recall and the violet missed-water map. Abstention is not free accuracy.
4. Run tiny-zone, paddy-context and partial-zone exercises. Show the field-level review gate even when water-like pixels exist. In partial-zone, the detail panel explicitly says **Partial**; a high assessed fraction inside the image cannot fill the missing edge.
   Then run **Missing earlier pixels** and select **Survey sector 5**: the current image is fully assessed, but paired assessability is zero. All its current water appears as **Water without earlier baseline**, and the gate is **BASELINE REQUIRED**. Compare with **Water at both dates**: repeated water still does not prove permanence or continuous flooding.
5. Run shifted-grid after a successful report: the old map disappears, metrics clear, and export becomes unavailable.
6. Return to a normal example. Export a review with dates, source hashes, policy and human notes. Export before changing cases; notes are session-only.

## Boundaries before external use

The pixel policy is still `surface-water-screen-v1`; these additions do not improve its measured segmentation accuracy. Real matched temporal validation, verified agricultural polygons, stronger event-disjoint comparisons, practitioner review and upstream data/media permissions remain necessary. Read [data provenance](WATERTRACE_DATA.md) before redistributing imagery or derived previews. AWS deployment remains deferred by the owner. Do not describe the prototype as a warning service or recommend entering a flood-affected field from its output.
