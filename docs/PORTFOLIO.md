# Presenting ChartCourt as a portfolio project

## Positioning

**A privacy-first chart screenshot auditor that explains its measurements and refuses unsupported reconstructions.** Lead with the problem and the engineering, not an award prediction or “AI-powered” label. OpenCV, OCR, numerical calibration, API design, robustness testing, and failure handling are the substantive work.

## A short demo

1. Inspect **The growth illusion**. Show the approximately 4× visible bar-length ratio versus approximately 1.065× recovered-value ratio. Explain why a nonzero baseline changes the visual comparison.
2. Open **Visual evidence** and the inspection trace. Point to the actual bar boxes, axis ticks, category labels, and pixel-to-value calibration.
3. Inspect **The vanishing value**. Show why a missing bar does not justify silently deleting its category or inventing a zero. The app withholds numeric/SVG exports while retaining the evidence report.
4. Run `python -m app.cli` on a supported chart and a flagged chart. Explain its exit-code contract, explicit inputs, bounded reads, and no-overwrite reports.
5. Show the verification report and local test results. Once hosted CI can run and actually passes, show that run too. The first hosted attempt was blocked before execution; the workflow definition alone does not demonstrate a passing build. State clearly which results are synthetic and what remains unverified.

## Resume wording to adapt

Use only statements you can explain and reproduce. Replace or remove metrics if a later version changes them.

- Built a local chart-auditing application with OpenCV, Tesseract, FastAPI, and a batch CLI; calibrated screenshot pixels to numeric values, detected axis distortions, and generated evidence-linked reconstructions with abstention safeguards.
- Developed regression tests for OCR, image transformations, omitted categories, upload limits, privacy, and API/CLI failures; added SHA-pinned CI and non-root container smoke checks with reproducible synthetic evaluation.

Once independently validated, add the real dataset size, protocol, coverage, and error metrics. Do **not** call the current synthetic result “100% real-world accuracy,” claim production security, AWS/COOL execution, published research, or hackathon awards that have not happened.

## Be ready to explain

- Why bar-chart geometry is deliberately narrower than general chart extraction.
- How a linear axis fit works, why three ticks are required, and why a low residual can still be wrong.
- The omitted-zero-bar bug, the test that reproduced it, and the label-to-mark consistency check that caught it.
- Why size-aware OCR enlargement improved the local transformation set, and how a held-out set would test whether that improvement generalizes.
- The difference between successful reconstruction and safe refusal; why reporting only one is misleading.
- Why stopping the browser request does not kill an OCR subprocess already running on the server.
- What the SVG verification proves and what it does not.
- Where upload limits apply, why temporary disk spooling still exists, and what would change for public hosting.

Review the code and be transparent about tools and assistance used if asked. The strongest interview discussion is an experiment, its failure, the reasoning behind a fix, and evidence of its limits.

## Before sharing with recruiters

The repository remains private unless its owner explicitly changes that. A private link alone is not a usable public portfolio demo. Prepare a sanitized screen recording or grant appropriate repository access; do not publish private charts, reports, credentials, or personal machine data. Confirm any competition publication rules before sharing a submission publicly.

Prioritize an independent evaluation set and feedback from a few real users before adding more surface features. They provide stronger evidence of usefulness than a longer feature list.
