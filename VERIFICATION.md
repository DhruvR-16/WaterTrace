# ChartCourt v0.3 verification — archived predecessor

These results do not describe FieldWatch. See [FieldWatch benchmark](docs/FIELDWATCH_BENCHMARK.md) and [readiness](docs/FIELDWATCH_READINESS.md) for the current project.

Verified locally on macOS with Python 3.13.6, OpenCV 5.0.0, and Tesseract 5.5.2.

## Automated checks

`python -m pytest -q`: **124 passed**. Upstream Starlette/httpx and Matplotlib/Pyparsing deprecation warnings remain; no test failed.

Checks cover six self-authored demo fixtures, 15 independently rendered challenge cases, numerical recovery, a resized/compressed JPEG with a changed filename, removing the axis or baseline tick, blank images, invalid/oversized uploads, sample allowlisting, strict numeric parsing, source hashes, trace timings, mixed-unit/nonlinear tick rejection, missing OCR, image validation, escaped OCR text, corrupted reconstructions, evaluator correctness, and inspection concurrency limits.

Upload-boundary tests additionally cover rejection before reading oversized declared bodies, chunked/underreported bodies, exact size boundaries, invalid/duplicate lengths, compressed request rejection, disconnect/timeout/cancellation cleanup, concurrent upload admission, one-file multipart shape, temporary-file closure, display-filename sanitization, private exception-message suppression, and security headers on early errors. Stream-level tests exercise the ASGI middleware directly; they do not establish reverse-proxy/network behavior under load.

`python scripts/evaluate.py --suite all`: **21/21 cases met the decision, issue-type, bar-count, reconstruction, and numeric-error checks**. All 14 supported examples were reconstructed; all 7 unsupported/incomplete examples were referred for review. No clean example was flagged. The numeric-error limit is 1.5% of the largest absolute ground-truth value per supported case.

The challenge images are generated with Pillow instead of the demo's Matplotlib renderer. They include grayscale, black truncated bars, mixed colored/grayscale bars, compact currency, fractional values, narrow bars, inverted axes, equal-height inverted bars, missing ticks, logarithmic axes, grouped spacing, multicolor stacks, and positive/negative mixtures. The baseline-tick removal and corrupted-SVG cases are additional tests outside the 21-image evaluator.

These were development regression cases, not an independent dataset or held-out evaluation. The 21/21 result does not establish real-world generalization. Demo numeric errors remain below the declared tolerance; exact values depend on OCR version and image rendering.

`python scripts/evaluate_variants.py --suite all --summary`: **126 transformed cases checked**: all 84 supported variants reconstructed within the issue/count/numeric checks, and all 42 unsupported variants refused. The transformations are JPEG quality 50, WebP quality 60, two-thirds resize, 0.6-pixel blur, 40-pixel white padding, and EXIF-rotated JPEG. Before size-aware OCR enlargement, the same development set recovered 52/84 supported variants and refused 32. This before/after improvement is not an independent evaluation. The evaluator separates correct recovery from safe refusal and can enforce a minimum supported-coverage fraction; CI requires at least 95% as well as no incorrect accepted result.

Category tests reproduce omitted zero/short first and final bars, alternating missing marks, numeric/multiword labels, separate footer rows, and unreadable labels. CLI tests cover real OCR without a server, all documented exit codes, mixed valid/invalid batches, size limits, sanitized failures, path privacy, file permissions, and refusing existing files or symlink destinations.

`node --check app/static/app.js`: passed.

`node --check app/static/network.js` and `node --test tests/network.test.cjs`: passed, **19 frontend unit tests**. These cover request options, error sanitization, malformed success bodies, bounded Retry-After delays, deadlines while connecting and reading the body, user cancellation, pre-cancelled requests, listener cleanup, and explicit upload retry without automatic resubmission.

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

Recovery checks: the local service was deliberately stopped, then a grayscale fixture was uploaded. The browser showed an actionable connection error, updated the engine indicator, displayed the correct image description, and disabled exports. After restarting the service, **Retry inspection** processed the same retained file without reopening the picker, cleared the error, and restored four data rows and export controls. The retry banner fit a 390 × 844 viewport without document overflow. With the local server temporarily paused, **Stop waiting** removed the busy state, explained that the server may still finish, and offered retry. The server was resumed after this check. Expected failed-network messages occurred during intentional disconnection tests; these are not application-script errors.

Category UI checks: **The vanishing value** showed three detected marks and four category words, including an unmatched North label. Category status was **Needs review**; numeric and SVG exports were disabled. The JSON report retained the unmatched category and source digest without image/SVG payloads. Category overlays and legend fit a 390-pixel viewport without document overflow.

## CI and container status

The repository includes a SHA-pinned, read-only-permission GitHub Actions workflow for Linux tests, synthetic evaluation, CLI execution, and a non-root read-only-filesystem container smoke test. The local Docker daemon is unavailable, so local container execution was not performed.

The [first hosted run](https://github.com/DhruvR-16/opencv_hackathon/actions/runs/38513256980) on October 14, 2026 was blocked by an account-level Actions restriction before any job steps started. This is neither a test failure nor a passing CI result. The repository owner must resolve that restriction and rerun the workflow before claiming Linux/container verification. No account settings were changed, and no successful container run is claimed here.

## Not yet verified

Public dataset performance, unseen-chart generalization, hosted CI/container execution, AWS deployment, COOL execution, multi-user production security, and competition eligibility are not established by these checks. Drag/drop and paste handlers exist but were not manually exercised.
