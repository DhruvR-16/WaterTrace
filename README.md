# ChartCourt

**Read between the axes.** An evidence-led visual audit for chart screenshots, built for the OpenCV AI Competition 2026.

ChartCourt measures bars, reads axis ticks, highlights the evidence, and reconstructs supported charts with a zero baseline and conventional axis direction. In the included truncated-axis example, the visible bars suggest a 4× ratio, while the recovered values differ by approximately 6.5%.

**Current implementation (v0.2):** local Python / OpenCV 5 app. It detects nonzero baselines and inverted axes in positive, regularly spaced single-series vertical bar charts on light backgrounds, including solid grayscale bars. An uncertain or incomplete scale triggers targeted tick-column OCR; unresolved images are referred for review. No AI API key is needed. The inspection policy is a bounded state machine, not an LLM.

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

- Five real image examples: truncated axis, conventional axis, inverted axis, missing ticks, and grayscale bars.
- Color/luminance segmentation, contour geometry, OCR tick reading, linear axis calibration, and value estimation.
- Strict numeric parsing for currency, percentages, English-style thousands separators, and k/M/B suffixes. Ambiguous comma decimals are rejected.
- Targeted reinspection when the axis is ambiguous or does not cover the bars, with recorded metrics and decision thresholds. Contrast enhancement is only applied to low-contrast retry crops.
- Geometry guards for irregular spacing, unaligned marks, and multicolor stacks; unsupported charts can still be misinterpreted, so review evidence.
- Pixel-fit sensitivity ranges in the data table, JSON, and CSV. These are **not statistical confidence intervals** and do not include OCR/model errors.
- Read-back verification of generated SVG bar count, order, baseline, and numerical heights before offering a reconstruction.
- Original/reconstruction comparison, evidence overlays, recovered values table, inspection trace.
- Downloadable reconstructed SVG, estimates CSV, and JSON inspection report with the original file's SHA-256 digest.
- Upload validation before multipart parsing, bounded upload/OCR execution and concurrency, safe failure messages, no persistent upload storage.
- Responsive browser workspace and keyboard-accessible controls.

## Data flow

```text
Image bytes → decode/resize → color + luminance bar geometry → axis crop OCR
  → fit scale → if unclear/incomplete: isolate tick column + enlarge + OCR
  → unresolved: review / resolved: recover bar values + pixel-fit ranges
  → axis findings → reconstruct → verify generated SVG geometry
```

`app/vision.py` only sees image bytes and a display filename. It does not read fixture names, labels, expected answers, or sample metadata. The backend returns measured evidence and the browser renders it.

## Verification

```sh
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/evaluate.py
.venv/bin/python scripts/evaluate.py --suite all
```

Tests run real OCR. The suite covers numerical recovery, a resized JPEG, erased axes/baseline ticks, grayscale and currency charts, fractional values, small nonzero or uncertain baselines, unsupported layouts, malformed/streamed uploads, resource cleanup, and reconstruction integrity. The local suite has **80 passing tests**; see [VERIFICATION.md](VERIFICATION.md) for checks and outstanding validation.

The evaluator offers `--suite demo` (5 Matplotlib images), `--suite stress` (15 independently rendered Pillow cases), and `--suite all`. It checks the specific issue, recovered bar count, numerical error, and whether reconstruction should be withheld. It reports reconstruction coverage, unsupported refusal rate, and false flags on clean charts, and exits nonzero on a regression. These cases were used during development: they are **not a held-out or public-dataset accuracy benchmark**.

Regenerate our self-authored examples with `.venv/bin/python scripts/generate_samples.py`. Numerical ground truth lives in `tests/fixtures/truth.json` and is never served to the inspection pipeline. Development dependencies include Matplotlib only for fixture generation.

## Current boundaries

- Intended for positive, regularly spaced single-series vertical bars with solid colors or dark grayscale fills on a light background. Stacked/grouped bars, negative bars, log/broken axes, dark backgrounds, pictograms, and infographic layouts are unsupported. Detection heuristics can still misinterpret unsupported inputs; results need inspection.
- Three consistent OCR ticks must cover the full bar geometry, including the baseline. A good fit is an internal consistency check, not a calibrated probability of correctness.
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

## Repository layout

```text
app/
  main.py              FastAPI routes, upload validation, concurrency limits
  vision.py            OpenCV geometry, OCR, axis policy, reconstruction
  static/              Browser interface and self-authored example PNGs
scripts/
  generate_samples.py  Reproducible example chart generation
  evaluate.py          Evaluation against fixture ground truth
  stress_cases.py      Independent Pillow-based regression chart generator
tests/
  fixtures/truth.json  Ground truth; never used by the analysis pipeline
  test_inspection.py   Real-OCR regression and API tests
  test_reliability.py  Additional formats, refusal, and reconstruction tests
```

## Privacy and repository hygiene

The local application does not send chart images to an external AI service or retain uploads after processing. Large multipart uploads can use temporary disk storage during a request. Google Fonts is the only intentional external browser request, for typography; system-font fallbacks are included.

Do not commit real user uploads, confidential reports, cloud credentials, or `.env` files. Local environments, keys, datasets, artifacts, and common credential files are excluded from Git; the Docker build context is restricted to runtime files. These exclusions do not replace reviewing staged changes or scanning Git history. See [SECURITY.md](SECURITY.md) for deployment boundaries and safe secret handling.

## Next milestones

The initial deliverable is a runnable MVP. Next competition milestones: independent dataset evaluation, improved support detection, user feedback, real AWS deployment and measured COOL execution, then report/video preparation.
