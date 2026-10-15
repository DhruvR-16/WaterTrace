# ChartCourt — archived predecessor

This document describes the previous project, not FieldWatch. Its complete runnable snapshot is preserved on branch `codex/chartcourt-v0.3`. Links and commands below are relative to that snapshot's repository root.

**Read between the axes.** A local, evidence-led visual audit for chart screenshots. Started for the OpenCV AI Competition 2026; developed as a reusable computer-vision tool.

ChartCourt measures bars, reads axis ticks, highlights the evidence, and reconstructs supported charts with a zero baseline and conventional axis direction. In the included truncated-axis example, the visible bars suggest a 4× ratio, while the recovered values differ by approximately 6.5%.

**Current implementation (v0.3):** local Python / OpenCV 5 app and batch CLI. It detects nonzero baselines and inverted axes in positive, regularly spaced single-series vertical bar charts on light backgrounds, including solid grayscale bars. An uncertain or incomplete scale triggers size-aware tick-column OCR; readable category labels are cross-checked for missed marks. Unresolved images are referred for review. No AI API key is needed. The inspection policy is a bounded state machine, not an LLM.

For the engineering design and tradeoffs, see [Architecture](docs/ARCHITECTURE.md). For an evidence-backed demo and resume outline, see [Portfolio guide](docs/PORTFOLIO.md).

## Quick start

Prerequisites: Python 3.13, Git, and the Tesseract executable. On macOS, install Tesseract with `brew install tesseract`; on Debian/Ubuntu, use `sudo apt-get install tesseract-ocr`. No API keys, cloud account, or hardware are needed to run locally.

```sh
git clone https://github.com/DhruvR-16/opencv_hackathon.git
cd opencv_hackathon
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [ChartCourt locally](http://127.0.0.1:8000). Upload, drag-and-drop, or paste a PNG/JPEG/WebP up to 8 MB and 20 megapixels. Images must be at least 100 pixels wide and tall. Examples are included and are inspected through the same pipeline as uploads. Stop the server with `Ctrl+C`.

On Windows, use `py -3.13 -m venv .venv` and replace `.venv/bin/python` with `.venv\Scripts\python.exe`; Tesseract must be installed and available on `PATH`. The documented verification was performed on macOS, not Windows.

## What works

- Six image examples: truncated axis, conventional axis, inverted axis, missing ticks, grayscale bars, and a zero-height category that must not silently disappear.
- Color/luminance segmentation, contour geometry, OCR tick reading, linear axis calibration, and value estimation.
- Strict numeric parsing for currency, percentages, English-style thousands separators, and k/M/B suffixes. Ambiguous comma decimals are rejected.
- Targeted reinspection when the axis is ambiguous or does not cover the bars, with recorded metrics and decision thresholds. Contrast enhancement is only applied to low-contrast retry crops.
- Geometry guards for irregular spacing, unaligned marks, and multicolor stacks; unsupported charts can still be misinterpreted, so review evidence.
- Category-row evidence overlays and missing-mark checks. A label without a detected bar triggers review, not an invented zero or a partial reconstruction.
- Pixel-fit sensitivity ranges in the data table, JSON, and CSV. These are **not statistical confidence intervals** and do not include OCR/model errors.
- Read-back verification of generated SVG bar count, order, baseline, and numerical heights before offering a reconstruction.
- Original/reconstruction comparison, evidence overlays, recovered values table, inspection trace.
- Downloadable reconstructed SVG, estimates CSV, and JSON inspection report with the original file's SHA-256 digest.
- Upload validation before multipart parsing, bounded upload/OCR execution and concurrency, safe failure messages, no persistent upload storage.
- Responsive browser workspace and keyboard-accessible controls.
- One-click retry after failures, connection-status feedback, and a stop-waiting control. Failed requests are not automatically resubmitted.
- Local batch CLI with bounded reads, structured errors, explicit exit codes, and private no-overwrite JSON output.

## Data flow

```text
Image bytes → decode/resize → color + luminance bar geometry → axis crop OCR
  → fit scale → if unclear/incomplete: isolate tick column + enlarge + OCR
  → unresolved: review / resolved: recover bar values + pixel-fit ranges
  → cross-check category coverage → axis findings → reconstruct → verify SVG
```

`app/vision.py` only sees image bytes and a display filename. It does not read fixture names, labels, expected answers, or sample metadata. The backend returns measured evidence and the browser renders it.

## Verification

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/evaluate.py
.venv/bin/python scripts/evaluate.py --suite all
.venv/bin/python scripts/evaluate_variants.py --suite all --summary
node --test tests/network.test.cjs
```

Tests run real OCR. The suite covers numerical recovery, image transformations, erased axes/baseline ticks, grayscale and currency charts, fractional values, small nonzero or uncertain baselines, missing categories, unsupported layouts, malformed/streamed uploads, CLI errors/privacy, and reconstruction integrity. See [VERIFICATION.md](VERIFICATION.md) for current results and outstanding validation.

The optional frontend tests use Node.js 22's built-in test runner, with no npm dependencies: **19 passing request-handling tests**. They cover deadlines, cancellation, safe response errors, retry delays, and reusing an uploaded file for an explicit retry.

The evaluator offers `--suite demo` (6 Matplotlib images), `--suite stress` (15 independently rendered Pillow cases), and `--suite all`. It checks the specific issue, recovered bar count, numerical error, and whether reconstruction should be withheld. It reports reconstruction coverage, unsupported refusal rate, and false flags on clean charts, and exits nonzero on a regression. The variant evaluator adds JPEG/WebP compression, resizing, blur, padding, and EXIF rotation (126 combinations). It reports successful recovery separately from safe refusal. These cases were used during development: they are **not a held-out or public-dataset accuracy benchmark**.

The [GitHub verification workflow](.github/workflows/verify.yml) runs Python/frontend tests, both evaluations, a real CLI invocation, and a non-root container smoke test. It uses read-only repository permissions and SHA-pinned actions. A workflow definition alone is not evidence of a passing run; check its actual status.

Regenerate our self-authored examples with `.venv/bin/python scripts/generate_samples.py`. Numerical ground truth lives in `tests/fixtures/truth.json` and is never served to the inspection pipeline. Development dependencies include Matplotlib only for fixture generation.

## Current boundaries

- Intended for positive, regularly spaced single-series vertical bars with solid colors or dark grayscale fills on a light background. Stacked/grouped bars, negative bars, log/broken axes, dark backgrounds, pictograms, and infographic layouts are unsupported. Detection heuristics can still misinterpret unsupported inputs; results need inspection.
- Three consistent OCR ticks must cover the full bar geometry, including the baseline. A good fit is an internal consistency check, not a calibrated probability of correctness.
- Category matching requires readable, approximately horizontal labels. It can catch omitted zero-height or very short bars, but cannot prove completeness when labels are missing, rotated, or misread. Zero-valued bars are not reconstructed by inference.
- Numeric formatting follows English-style notation. Decimal commas, scientific-notation tick labels, and implicit axis multipliers such as a separate “×10³” annotation are not supported. Units are recovered only when present in the tick text, not inferred from the axis title.
- Pixel-fit sensitivity is `2 × abs(axis slope) + maximum tick-fit residual` in chart units. It measures a small pixel perturbation, not source-data uncertainty or protection against incorrect OCR. Rendered axis ticks use human-readable intervals without changing the recovered data.
- Values are estimates from pixel positions. Decimal precision is reported for inspection, not a promise of equivalent source-data accuracy. OCR category names can be wrong.
- Truncated/inverted axes are design choices to investigate. They do not establish malicious intent, and a clean axis does not establish truthful source data.
- The app reads available evidence; it does not retrieve or verify the original dataset or accompanying claims.
- The local app makes no claim of AWS deployment, COOL execution, public benchmark accuracy, or award eligibility. The application does not retain uploads after processing; the multipart framework may temporarily spool large uploads to disk during a request. Downloaded reports remain on the user's device. Google Fonts is requested for typography and has local font fallbacks.

## Hackathon deployment

AWS deployment remains required for the competition and is not yet performed. The repository includes a container recipe:

```sh
docker build -t chartcourt .
docker run --rm -p 127.0.0.1:8000:8000 chartcourt
```

The image includes standard OpenCV 5, not COOL. It can be hosted on an appropriate AWS compute service. A public deployment needs HTTPS, access control and request/body limits at the proxy; this initial server binds to loopback for local use.

For the COOL award, use the official compatible Graviton Marketplace environment, preserve its OpenCV installation, install the other dependencies, run this same workload there, and measure against standard OpenCV 5 on equivalent hardware. Do not install `requirements.txt` over the COOL environment: that would replace its OpenCV package. Record the actual imported library path/build info. `cool_verified` is deliberately false until such verification exists.

## Evaluation roadmap

Use licensed subsets of [PlotQA](https://github.com/NiteshMethani/PlotQA) (CC BY 4.0) and [Misviz](https://tudatalib.ulb.tu-darmstadt.de/items/21f65047-c4d8-45a2-a717-e76f63dd0c33) (CC BY-SA 4.0). Neither dataset has been downloaded or evaluated in this version. Preserve attribution and license requirements. Filter to supported vertical-bar layouts using a fixed published protocol; separate tuning from held-out tests by source/data family, including paired variants. Report coverage/refusal rate alongside issue precision/recall and numeric error. Include clean charts and unsupported charts to expose false accusations and mistaken reconstructions.

## API

- `GET /api/health`: runtime OpenCV version, OCR availability and deployment label.
- `GET /api/samples`: public example titles, without numerical truth.
- `POST /api/samples/{id}/analyze`: inspect an allowlisted example image.
- `POST /api/analyze`: multipart field `file`; returns findings, geometry, ticks, trace, image preview and reconstructed SVG when supported.
- `/docs`: generated API reference.

Example upload from a second terminal while the server is running:

```sh
curl --fail http://127.0.0.1:8000/api/analyze \
  -F 'file=@app/static/samples/truncated.png'
```

The JSON response contains findings, the input file's SHA-256 digest, evidence boxes, recovered estimates, actual inspection steps, and a reconstruction when the evidence supports it.

Uploads accept one `file` part and no additional fields. The file limit is 8 MiB; the complete multipart body is capped at 8 MiB plus 64 KiB before parsing. Upload-body reads time out after 30 seconds. Per process, at most two uploads and two inspections run concurrently. Expected failure responses contain a JSON `detail`: `400` for malformed requests, `408` for upload timeout, `413` for size limits, `415` for unsupported request encoding/type, `422` for invalid images, and `429` when busy (with `Retry-After`). A generic `500` does not expose private exception details.

The browser bounds startup requests to 10 seconds and inspections to 90 seconds. **Stop waiting** cancels the browser request, not an OCR job already running on the server. Retry is explicit and retains the selected file only in the current browser page; busy responses briefly disable the retry button. Nothing is queued for background retry.

## Batch CLI

No web server or browser is needed:

```sh
.venv/bin/python -m app.cli app/static/samples/honest.png app/static/samples/truncated.png
mkdir -p artifacts
.venv/bin/python -m app.cli app/static/samples/honest.png --output artifacts/audit.json --fail-on-findings
```

The CLI processes up to 100 explicit file paths sequentially, with the same 8 MiB/image limits as the API. It continues after an invalid input and reports each input's index, display filename, result or structured error. It does not recursively scan directories. JSON goes to stdout unless `--output` is provided. Output parents must exist; existing files and symlinks are never overwritten. On POSIX, new reports have owner-only permissions (`0600`).

Exit `0` means processing completed; flagged/review results are still successful inspections by default. With `--fail-on-findings`, either outcome returns `1`. Input, processing, or output failures return `2`. Reports omit image payloads, SVG markup, and input directory paths but still contain OCR text and estimates: treat them as potentially sensitive.

## Repository layout

```text
app/
  main.py              FastAPI routes, upload validation, concurrency limits
  cli.py               Local batch audits and no-overwrite report output
  privacy.py           Shared filename and report boundaries
  upload_limits.py     Pre-parser body limits, deadlines, upload admission
  vision.py            OpenCV geometry, OCR, axis policy, reconstruction
  static/              Browser interface and self-authored example PNGs
scripts/
  generate_samples.py  Reproducible example chart generation
  evaluate.py          Evaluation against fixture ground truth
  evaluate_variants.py Transformed-image coverage and incorrect-acceptance checks
  stress_cases.py      Independent Pillow-based regression chart generator
tests/
  fixtures/truth.json  Ground truth; never used by the analysis pipeline
  test_inspection.py   Real-OCR regression and API tests
  test_reliability.py  Additional formats, refusal, and reconstruction tests
  test_upload_limits.py  Stream limits, cleanup, and failure privacy
  network.test.cjs     Dependency-free frontend request tests
docs/
  ARCHITECTURE.md      Design, trust boundaries, and engineering tradeoffs
  PORTFOLIO.md         Demo outline and defensible resume claims
```

## Privacy and repository hygiene

The local application does not send chart images to an external AI service or retain uploads after processing. Large multipart uploads can use temporary disk storage during a request. Google Fonts is the only intentional external browser request, for typography; system-font fallbacks are included.

Do not commit real user uploads, confidential reports, cloud credentials, or `.env` files. Local environments, keys, datasets, artifacts, and common credential files are excluded from Git; the Docker build context is restricted to runtime files. These exclusions do not replace reviewing staged changes or scanning Git history. See [SECURITY.md](SECURITY.md) for deployment boundaries and safe secret handling.

## Next milestones

Next product milestones: independently sourced evaluation data, user feedback, stronger support detection, and accessible image-region correction without disguising human edits as OCR. Public hosting requires a separate security/deployment review. Competition-specific AWS and COOL work remains optional to the portfolio roadmap and unverified until actually performed.
