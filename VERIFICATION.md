# v0.2 verification

Verified locally on macOS with Python 3.13.6, OpenCV 5.0.0, and Tesseract 5.5.2.

## Automated checks

`python -m pytest -q`: **50 passed**. Upstream Starlette/httpx and Matplotlib/Pyparsing deprecation warnings remain; no test failed.

Checks cover five self-authored demo fixtures, 15 independently rendered challenge cases, numerical recovery, a resized/compressed JPEG with a changed filename, removing the axis or baseline tick, blank images, invalid/oversized uploads, sample allowlisting, strict numeric parsing, source hashes, trace timings, mixed-unit/nonlinear tick rejection, missing OCR, image validation, escaped OCR text, corrupted reconstructions, evaluator correctness, and inspection concurrency limits.

`python scripts/evaluate.py --suite all`: **20/20 cases met the decision, issue-type, bar-count, reconstruction, and numeric-error checks**. All 14 supported examples were reconstructed; all 6 unsupported/incomplete examples were referred for review. No clean example was flagged. The numeric-error limit is 1.5% of the largest absolute ground-truth value per supported case.

The challenge images are generated with Pillow instead of the demo's Matplotlib renderer. They include grayscale, black truncated bars, mixed colored/grayscale bars, compact currency, fractional values, narrow bars, inverted axes, equal-height inverted bars, missing ticks, logarithmic axes, grouped spacing, multicolor stacks, and positive/negative mixtures. The baseline-tick removal and corrupted-SVG cases are additional tests outside the 20-image evaluator.

These were development regression cases, not an independent dataset or held-out evaluation. The 20/20 result does not establish real-world generalization. Demo mean absolute errors are about 0.0064, 0.1127, 0.0743, and 0.0668 chart units for truncated, conventional, inverted, and grayscale examples respectively.

`node --check app/static/app.js`: passed.

## Browser checks

- Truncated-axis example: original vs reconstruction, approximately 4.0× visible bar ratio vs 1.065× recovered-value ratio.
- Conventional-axis example: supported axis checks pass without asserting that the source data is true.
- Missing-scale example: real second OCR pass, review result, reconstruction download disabled.
- File picker upload of the inverted-axis PNG: image processed and downward numeric axis flagged.
- Visual-evidence tab: four bar regions and numeric tick overlays.
- Recovered-data tab: numeric estimates and OCR category labels.
- JSON, CSV, and SVG downloads completed through the browser.
- Desktop breakpoint at 1440 × 1000 and mobile at 390 × 844 inspected; mobile document width matches viewport width.
- No browser console errors or warnings were observed during the upload test.

Additional v0.2 browser checks: the grayscale example reconstructed successfully; recovered data displayed per-bar pixel-fit ranges with the statistical-confidence disclaimer; CSV download included unit and range columns; keyboard arrow navigation selected the adjacent tab with a single active tab stop; the unreadable example disabled reconstruction; the expanded table fit a 390-pixel viewport without document overflow.

## Not yet verified

Public dataset performance, unseen-chart generalization, Docker build/runtime, AWS deployment, COOL execution, multi-user production security, and competition eligibility are not established by these checks. Drag/drop and paste handlers exist but were not manually exercised.
