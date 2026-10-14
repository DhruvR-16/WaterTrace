# ChartCourt: engineering design

ChartCourt is an image-only chart auditor, not a fact checker or a general chart-understanding model. Its useful output is an inspectable chain of measurements, including an explicit refusal when evidence is insufficient.

## Components and trust boundaries

```text
Browser → upload admission/body bounds → multipart validation ┐
                                                           ├→ vision.analyze(bytes)
Batch CLI → explicit file list / bounded reads ──────────────┘
  decode → color/luminance contours → tick OCR → linear fit
  → targeted OCR retry if needed → category-coverage check
  → axis findings → SVG reconstruction → read-back geometry verification
  → evidence, trace, source digest, estimated values or review
```

`app/vision.py` does not load fixture labels, filenames as answer keys, or evaluation truth. The API and CLI share that engine. Evaluation scripts can see ground truth; the engine cannot. The same PNG can therefore be renamed or transformed and still requires a fresh pixel-based decision.

## Core decisions

1. **Constrain the problem.** Positive, regularly spaced, solid vertical bars on light backgrounds are the supported target. Three consistent ticks must cover the geometry. More chart types would be useful, but accepting them without tests would make the output less trustworthy.
2. **Abstain before inventing values.** Missing scales, incompatible geometry, ambiguous baselines, or readable category labels without a corresponding mark withhold reconstruction. Missing marks are not assumed to equal zero.
3. **Adapt a bounded OCR retry.** The policy inspects the numeric column again only when evidence is insufficient. Small observed tick glyphs use 3× enlargement; larger ones use 2×. Contrast enhancement is reserved for low-contrast crops. The fit and coverage checks remain unchanged after retry; there is no unrestricted agent loop or guessed-digit substitution.
4. **Keep evidence inspectable.** Pixel boxes, parsed ticks, fit residuals, decision thresholds, category checks, source SHA-256, and actual tool timings are returned. A matching image digest establishes which bytes were inspected, not whether those bytes or their source claims are truthful.
5. **Separate estimates from certainty.** Pixel-fit ranges measure ±2-pixel perturbation plus tick-fit residual. They exclude OCR/model error and are not statistical confidence intervals. Values retain precision for auditability, not to imply source-data precision.
6. **Verify the generated artifact.** SVG rectangles are parsed back and checked for count, order, non-overlap, zero baseline, and preserved numeric heights. This checks the rendering transformation, not the original extraction's truth.

## Failure and resource model

- The HTTP upload guard admits two uploads per process, bounds total retained request bytes before multipart parsing, and enforces a 30-second body deadline. The parser accepts one file and no extra fields. Files are closed on success and failure.
- Two inspections per process and 15-second individual OCR deadlines limit work. Images are limited to 20 megapixels and resized to fit 1800 × 1800 before geometry/OCR. These controls do not impose a complete process-memory bound or replace proxy limits and worker isolation.
- A cancelled browser request does not promise cancellation of an already running native/OCR task. Retry requires an explicit user action; no job is silently queued.
- The CLI reads at most 8 MiB plus one sentinel byte per input, processes sequentially, and refuses existing report paths. Reports are intentionally sensitive even without embedded images.
- Uploaded names and exception messages are untrusted. Display names discard directories/control characters; unexpected failure messages do not expose local paths or OCR text. SVG labels are escaped, CSV text is formula-guarded, and runtime images are never used as executable code.

## Evidence-driven development

The first missing-category experiment found that `[0, 44, 61, 78]` could be reported as a clear three-bar chart. The fix cross-checks the readable category row and now refuses that partial recovery. Unit tests also cover short first bars, missing final bars, alternating missing bars, multiword labels, and unrelated footer text.

The initial transformation benchmark reconstructed 52 of 84 supported variants; 32 were refused because the zero tick was unreadable. Size-aware enlargement recovered 84 of 84 in the same local development set without changing acceptance thresholds; all 42 unsupported variants remained refused. This is a development-set before/after measurement, **not held-out accuracy**. See [verification](../VERIFICATION.md) for the recorded environment and actual CI status.

## Remaining risks and next experiments

OCR can be consistently wrong while a fit appears linear. A hidden multiplier, missing unreadable category, unusual layout, or cleverly constructed input can still defeat the heuristics. A category-row match is a consistency check, not proof of full recovery. Narrow scope and synthetic tests cannot establish real-world performance.

The highest-value next experiment is a licensed, independently sourced image set with a frozen annotation protocol: chart-type eligibility, expected issue, category count, values, and reasons for refusal. Split tuning and test families before changing thresholds. Report coverage, issue precision/recall, category completeness, numeric error, and failures—not only accepted-case accuracy.

There is no database, account system, background queue, remote model, or cloud deployment to administer. Add those only when real usage requires them. This keeps local use reproducible, private, and inexpensive while making future architecture decisions evidence-driven.
