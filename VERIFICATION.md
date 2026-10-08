# MVP verification

Verified locally on macOS with Python 3.13.6, OpenCV 5.0.0, and Tesseract 5.5.2.

## Automated checks

`python -m pytest -q`: **16 passed**. The test client currently emits one upstream Starlette/httpx deprecation warning; no test failed.

Checks cover the four self-authored chart fixtures, numerical recovery, a resized/compressed JPEG with a changed filename, removing the axis, blank images, invalid/oversized uploads, sample allowlisting, numeric parsing, source hashes, trace timings, nonlinear tick rejection, missing OCR, image format/dimension validation, escaped OCR text, and inspection concurrency limits.

`python scripts/evaluate.py`: all four self-authored fixture decisions matched their expectations. Mean absolute numeric errors were about 0.008, 0.115, and 0.100 chart units for the truncated, conventional, and inverted examples. These are fixture-specific results, **not external benchmark accuracy**.

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

## Not yet verified

Public dataset performance, unseen-chart generalization, Docker build/runtime, AWS deployment, COOL execution, multi-user production security, and competition eligibility are not established by these checks. Drag/drop and paste handlers exist but were not manually exercised.
