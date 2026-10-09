"""Image-only, bounded chart inspection. No fixture metadata enters this pipeline."""
from __future__ import annotations

import base64
import hashlib
from html import escape
from io import BytesIO
import math
import re
import time
from xml.etree import ElementTree

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
import pytesseract

MAX_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InvalidImage(ValueError):
    pass


def decode_image(raw: bytes) -> np.ndarray:
    try:
        with Image.open(BytesIO(raw)) as im:
            if im.width * im.height > MAX_PIXELS:
                raise InvalidImage("Image is too large. Use an image under 20 megapixels.")
            if im.format not in {"PNG", "JPEG", "WEBP"}:
                raise InvalidImage("Choose a PNG, JPEG, or WebP chart image.")
            im = ImageOps.exif_transpose(im)
            rgba = im.convert("RGBA")
            background = Image.new("RGBA", rgba.size, "white")
            background.alpha_composite(rgba)
            im = background.convert("RGB")
            im.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            rgb = np.array(im)
        if min(rgb.shape[:2]) < 100:
            raise InvalidImage("This image is too small. Use a chart at least 100 pixels wide and tall.")
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidImage("Could not read this image. Choose a PNG, JPEG, or WebP under 20 megapixels.") from exc


def image_url(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise InvalidImage("Could not encode the inspection image.")
    return "data:image/png;base64," + base64.b64encode(encoded).decode()


def parse_tick(text: str) -> dict | None:
    """Strict English-style numbers; do not guess decimal separators or OCR digits."""
    token = text.strip().replace("−", "-").replace("–", "-")
    match = re.fullmatch(
        r"(?P<currency>[€£$])?(?P<sign>-?)(?P<digits>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
        r"(?P<magnitude>[kKMB])?(?P<percent>%)?", token)
    if not match or (match["currency"] and match["percent"]):
        return None
    scale = {None: 1, "k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9}[match["magnitude"]]
    value = float(match["sign"] + match["digits"].replace(",", "")) * scale
    if not math.isfinite(value) or abs(value) >= 1e12:
        return None
    return dict(value=value, unit=match["currency"] or match["percent"] or "")


def number(text: str) -> float | None:
    parsed = parse_tick(text)
    return parsed["value"] if parsed else None


def ocr(image: np.ndarray, *, offset=(0, 0), scale=1, psm=11) -> list[dict]:
    if not image.size:
        return []
    data = pytesseract.image_to_data(image, config=f"--psm {psm}",
                                   output_type=pytesseract.Output.DICT, timeout=15)
    words = []
    for i, text in enumerate(data["text"]):
        conf = float(data["conf"][i])
        if not text.strip() or conf < 25:
            continue
        x, y, w, h = (int(data[k][i]) / scale for k in ("left", "top", "width", "height"))
        words.append(dict(text=text.strip(), confidence=round(conf / 100, 3),
                          box=[round(x + offset[0]), round(y + offset[1]), round(w), round(h)]))
    return words


def find_bars(image: np.ndarray, *, grayscale=False) -> tuple[list[dict], str]:
    """Find solid separate rectangles, refusing incomplete or irregular groups."""
    h, w = image.shape[:2]
    if grayscale:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Light paper only. Opening removes thin axes/grid lines before contours.
        mask = cv2.inRange(gray, 0, 200)
    else:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, np.array([0, 60, 45]), np.array([179, 255, 255]))
    size = 5 if grayscale else 3
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((size, size), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        fill = cv2.contourArea(contour) / (bw * bh)
        if (.014 * w < bw < .24 * w and .022 * h < bh < .82 * h
                and bw * bh > .001 * h * w and fill > .87
                and .06 * h < y and y + bh < .95 * h):
            interior = image[y+max(1, bh//12):y+bh-max(1, bh//12), x+bw//4:x+3*bw//4]
            row_colors = np.median(interior, axis=1)
            variation = np.percentile(np.max(np.abs(row_colors - np.median(row_colors, axis=0)), axis=1), 95)
            # A connected contour can contain multiple stacked colors. Do not
            # silently treat that stack as a single solid bar.
            if variation > 30:
                return [], "bottom"
            color = image[y + bh // 2, x + bw // 2]
            candidates.append(dict(box=[x, y, bw, bh], color="#%02x%02x%02x" % tuple(int(c) for c in color[::-1])))
    if len(candidates) < 2:
        return [], "bottom"
    best, edge = [], "bottom"
    tolerance = max(4, h * .008)
    for side in ("bottom", "top"):
        for anchor in candidates:
            ax, ay, aw, ah = anchor["box"]
            base = ay + ah if side == "bottom" else ay
            group = [c for c in candidates if abs((c["box"][1] + (c["box"][3] if side == "bottom" else 0)) - base) <= tolerance]
            if len(group) > len(best):
                best, edge = group, side
    best.sort(key=lambda c: c["box"][0])
    # Exclude stacked or overlapping marks: the MVP supports one series only.
    if len(best) < 2 or len(best) != len(candidates) or len(best) > 24 or any(a["box"][0] + a["box"][2] > b["box"][0] for a, b in zip(best, best[1:])):
        return [], edge
    widths = np.array([c["box"][2] for c in best])
    if np.max(widths) / np.min(widths) > 1.8:
        return [], edge
    centers = np.array([c["box"][0] + c["box"][2] / 2 for c in best])
    gaps = np.diff(centers)
    if len(gaps) > 1 and np.max(gaps) / np.min(gaps) > 1.5:
        return [], edge
    return best, edge


def axis_ticks(words: list[dict], image_width: int) -> list[dict]:
    numeric = []
    for word in words:
        parsed = parse_tick(word["text"])
        if parsed is not None:
            numeric.append({**word, **parsed, "cy": word["box"][1] + word["box"][3] / 2})
    if len(numeric) < 3:
        return []
    # Tick labels are right-aligned; their right edges form a column.
    groups = []
    for anchor in numeric:
        right = anchor["box"][0] + anchor["box"][2]
        group = [t for t in numeric if abs(t["box"][0] + t["box"][2] - right) < max(12, image_width * .018)]
        if len(group) >= 3:
            groups.append(group)
    if not groups:
        return []
    ticks = max(groups, key=lambda g: (len(g), np.mean([t["box"][0] for t in g])))
    ticks.sort(key=lambda t: t["cy"])
    unique = []
    for tick in ticks:
        if not unique or abs(tick["cy"] - unique[-1]["cy"]) > 8:
            unique.append(tick)
    return unique


def fit_axis(ticks: list[dict]) -> tuple[float, float, float] | None:
    if len(ticks) < 3:
        return None
    if len({t.get("unit", "") for t in ticks if t.get("unit")}) > 1:
        return None
    ys = np.array([t["cy"] for t in ticks])
    values = np.array([t["value"] for t in ticks])
    span = float(np.ptp(values))
    if span < 1e-9 or np.ptp(ys) < 30:
        return None
    a, b = np.polyfit(ys, values, 1)
    residual = float(np.max(np.abs(a * ys + b - values)) / span)
    return float(a), float(b), residual


def ticks_cover_bars(ticks: list[dict], bars: list[dict]) -> bool:
    if len(ticks) < 3:
        return False
    low, high = min(t["cy"] for t in ticks), max(t["cy"] for t in ticks)
    margin = max(4, (high-low) * .018)
    return all(low-margin <= b["box"][1] and b["box"][1]+b["box"][3] <= high+margin for b in bars)


def format_value(value: float, unit: str = "") -> str:
    text = f"{value:.4g}"
    return f"{unit}{text}" if unit in {"$", "€", "£"} else f"{text}{unit}"


def nice_scale(maximum: float) -> tuple[float, np.ndarray]:
    target = max(maximum, 1e-9) / 5
    power = 10 ** math.floor(math.log10(target))
    step = next(m * power for m in (1, 2, 2.5, 5, 10) if m * power >= target)
    count = math.ceil(max(maximum, 1e-9) * 1.08 / step)
    return count * step, np.arange(count + 1) * step


def reconstruction_svg(bars: list[dict], unit: str) -> str:
    W, H, left, right, top, bottom = 800, 480, 85, 765, 70, 402
    maximum = max(b["value"] for b in bars)
    ymax, ticks = nice_scale(maximum)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" data-axis-max="{ymax}" data-baseline="{bottom}" data-plot-top="{top}" role="img" aria-label="Reconstructed chart with a zero baseline">',
             '<rect width="800" height="480" fill="#fff"/>',
             '<text x="85" y="35" font-family="Arial,sans-serif" font-size="18" font-weight="600" fill="#263643">Reconstructed from visible evidence</text>']
    for tick in ticks:
        y = bottom - tick / ymax * (bottom - top)
        parts.append(f'<line x1="{left}" y1="{y:.2f}" x2="{right}" y2="{y:.2f}" stroke="#e6e9ea"/>')
        parts.append(f'<text x="70" y="{y+5:.2f}" text-anchor="end" font-family="Arial,sans-serif" font-size="14" fill="#687583">{escape(format_value(tick, unit))}</text>')
    step = (right - left) / len(bars)
    for i, bar in enumerate(bars):
        height = bar["value"] / ymax * (bottom - top)
        x = left + i * step + step * .22
        parts.extend([
            f'<rect data-chart-bar="true" x="{x:.2f}" y="{bottom-height:.2f}" width="{step*.56:.2f}" height="{height:.2f}" rx="3" fill="{bar["color"]}"/>',
            f'<text x="{left+(i+.5)*step:.2f}" y="{bottom-height-10:.2f}" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" font-weight="600" fill="#263643">≈ {escape(format_value(bar["value"], unit))}</text>',
            f'<text x="{left+(i+.5)*step:.2f}" y="428" text-anchor="middle" font-family="Arial,sans-serif" font-size="14" fill="#687583">{escape(bar["label"][:22])}</text>',
        ])
    parts.append('<text x="85" y="465" font-family="Arial,sans-serif" font-size="12" fill="#87919a">Values are estimated from pixels. The underlying source data has not been verified.</text></svg>')
    return "".join(parts)


def verify_reconstruction(svg: str, bars: list[dict]) -> bool:
    """Read back SVG geometry, checking count, zero baseline, order, and values."""
    try:
        root = ElementTree.fromstring(svg)
        ymax = float(root.attrib["data-axis-max"])
        bottom = float(root.attrib["data-baseline"])
        top = float(root.attrib["data-plot-top"])
        if not all(math.isfinite(v) for v in (ymax, bottom, top)) or ymax <= 0 or bottom <= top:
            return False
        rectangles = root.findall("{http://www.w3.org/2000/svg}rect[@data-chart-bar='true']")
        if len(rectangles) != len(bars) or not bars:
            return False
        last_right = -math.inf
        for rect, bar in zip(rectangles, bars):
            x, y, width, height = (float(rect.attrib[k]) for k in ("x", "y", "width", "height"))
            if not all(math.isfinite(v) for v in (x, y, width, height)):
                return False
            reconstructed = height / (bottom - top) * ymax
            if (height < 0 or width <= 0 or x < last_right or y < top or abs(y+height-bottom) > .02
                    or abs(reconstructed-bar["value"]) > ymax * .0001):
                return False
            last_right = x + width
        return True
    except (ElementTree.ParseError, KeyError, ValueError, ZeroDivisionError):
        return False


def analyze(raw: bytes, filename: str = "chart.png") -> dict:
    started = time.perf_counter()
    image = decode_image(raw)
    h, w = image.shape[:2]
    traces: list[dict] = []
    findings: list[dict] = []
    overlays: list[dict] = []
    geometry = dict(method="color", detected_bars=0)

    def trace(tool, action, detail, metrics=None):
        elapsed = round((time.perf_counter() - started) * 1000)
        previous = traces[-1]["elapsed_ms"] if traces else 0
        traces.append(dict(step=len(traces) + 1, tool=tool, action=action, detail=detail,
                           metrics=metrics or {}, elapsed_ms=elapsed, duration_ms=elapsed - previous))

    def result(status, summary, bars=None, axis=None, svg=None, comparison=None):
        return dict(status=status, summary=summary, filename=filename[:160], image=image_url(image),
                    source_sha256=hashlib.sha256(raw).hexdigest(),
                    width=w, height=h, bars=bars or [], axis=axis, findings=findings, overlays=overlays, geometry=geometry,
                    trace=traces, reconstruction=svg, comparison=comparison,
                    processing_ms=round((time.perf_counter() - started) * 1000),
                    engine=dict(opencv=cv2.__version__, ocr="Tesseract", policy="axis-audit-v2",
                                deployment="local", cool_verified=False),
                    scope="Single-series, solid-color vertical bar charts with a readable linear numeric axis. Design checks do not verify the truth of the source data.")

    trace("decode_image", "Inspect image", f"Decoded a {w} × {h} image. Analysis uses pixels only.", {"width": w, "height": h})
    bars, edge = find_bars(image)
    trace("detect_bar_geometry", "Locate chart marks", f"Found {len(bars)} aligned solid bars using color masks and contours.",
          {"bars_found": len(bars), "shared_edge": edge})
    gray_bars, gray_edge = find_bars(image, grayscale=True)
    trace("check_luminance_geometry", "Check grayscale structure", "Cross-check dark rectangular marks so grayscale bars are not silently omitted.",
          {"luminance_bars": len(gray_bars), "color_bars": len(bars)})
    if len(gray_bars) > len(bars):
        trace("inspection_policy", "Use luminance evidence", "Luminance segmentation found more aligned solid bars than color segmentation. Continue with that geometry.")
        bars, edge = gray_bars, gray_edge
        geometry["method"] = "luminance"
    geometry["detected_bars"] = len(bars)
    if len(bars) < 2:
        findings.append(dict(kind="unsupported", severity="review", title="Chart structure needs review",
                             detail="Could not isolate at least two solid vertical bars. Try a single-series bar chart with visible axes.", evidence=[]))
        trace("inspection_policy", "Stop reconstruction", "Insufficient bar geometry. No numeric values or repair will be invented.")
        return result("review", "This image needs a closer look.")
    for i, bar in enumerate(bars):
        overlays.append(dict(box=bar["box"], label=f"Bar {i+1}", kind="bar"))

    xmin = min(b["box"][0] for b in bars)
    y0, y1 = int(h * .10), int(h * .90)
    x1 = max(1, xmin - 6)
    crop = image[y0:y1, :x1]
    try:
        words = ocr(crop, offset=(0, y0))
    except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
        trace("read_axis", "OCR unavailable", str(exc)[:180])
        findings.append(dict(kind="ocr_unavailable", severity="review", title="Axis reader unavailable", detail="Tesseract is missing or exceeded its time limit. The image has not been assessed.", evidence=[]))
        return result("review", "Axis reading could not complete.")
    ticks = axis_ticks(words, w)
    fit = fit_axis(ticks)
    trace("read_axis", "Read numeric ticks", f"Read {len(ticks)} aligned axis ticks.",
          {"ticks": [t["value"] for t in ticks], "fit_error": round(fit[2], 4) if fit else None})

    # Actual perception-decision-action loop: weak or inconsistent OCR changes the tool call.
    if fit is None or fit[2] > .025 or not ticks_cover_bars(ticks, bars):
        trace("inspection_policy", "Reinspect axis crop", "The tick fit is missing, inconsistent, or does not cover the full bar geometry; switch to a targeted enlarged tick-column OCR pass.",
              {"minimum_ticks": 3, "max_fit_error": .025, "covers_bars": ticks_cover_bars(ticks, bars)})
        # Isolating the tick column removes the axis line and rotated title, both
        # of which can cause a genuine zero to be read as the letter O.
        crop_left = max(0, min(t["box"][0] for t in ticks)-12) if ticks else 0
        crop_right = min(x1, max(t["box"][0]+t["box"][2] for t in ticks)+8) if ticks else x1
        gray = cv2.cvtColor(image[y0:y1, crop_left:crop_right], cv2.COLOR_BGR2GRAY)
        enlarged = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        # Contrast enhancement can harm already-crisp small glyphs. Apply it
        # only when the observed crop actually has a narrow intensity range.
        low_contrast = int(np.max(gray))-int(np.min(gray)) < 60
        enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(enlarged) if low_contrast else enlarged
        try:
            retry_words = ocr(enhanced, offset=(crop_left, y0), scale=2, psm=6)
            retry_ticks = axis_ticks(retry_words, w)
            retry_fit = fit_axis(retry_ticks)
            def evidence_rank(candidate_fit, candidate_ticks):
                return (candidate_fit[2] <= .025, ticks_cover_bars(candidate_ticks, bars), len(candidate_ticks), -candidate_fit[2])
            if retry_fit and (not fit or evidence_rank(retry_fit, retry_ticks) > evidence_rank(fit, ticks)):
                ticks, fit = retry_ticks, retry_fit
        except (pytesseract.TesseractNotFoundError, RuntimeError):
            trace("read_axis_detail", "OCR time limit", "The additional crop inspection did not complete within the time limit.")
        trace("read_axis_detail", "Resolve axis evidence", f"Axis now has {len(ticks)} usable ticks.", {"ticks": [t["value"] for t in ticks], "contrast_enhanced": low_contrast})
    if fit is None or fit[2] > .025 or not ticks_cover_bars(ticks, bars):
        findings.append(dict(kind="unreadable_axis", severity="review", title="A reliable scale is missing",
                             detail="At least three consistent numeric ticks covering the full bars are required. A missing, nonlinear, unreadable, or incomplete scale prevents reconstruction.", evidence=ticks))
        trace("inspection_policy", "Request human review", "Axis scale remains ambiguous after targeted reinspection. Reconstruction is withheld.")
        return result("review", "There is not enough evidence to reconstruct this chart.")

    a, b, error = fit
    slope_values = np.diff([t["value"] for t in ticks])
    if not (np.all(slope_values > 0) or np.all(slope_values < 0)):
        trace("inspection_policy", "Request human review", "Tick values are not monotonic. Axis interpretation is ambiguous.")
        return result("review", "The axis scale could not be verified.")
    for tick in ticks:
        overlays.append(dict(box=tick["box"], label=tick["text"], kind="tick"))
    bases = [bar["box"][1] + (bar["box"][3] if edge == "bottom" else 0) for bar in bars]
    baseline_px = float(np.median(bases))
    baseline = float(a * baseline_px + b)
    span = abs(ticks[-1]["value"] - ticks[0]["value"])
    # Use observed pixel/fit error rather than a fixed percentage of the whole
    # axis: the latter can silently turn a small nonzero baseline into zero.
    tolerance = abs(a) * 3 + error * span
    has_zero_tick = any(t["value"] == 0 for t in ticks)
    if abs(baseline) <= tolerance and has_zero_tick:
        baseline = 0.0
    unit = next((t.get("unit", "") for t in ticks if t.get("unit")), "")
    sensitivity = abs(a) * 2 + error * span
    axis = dict(slope=a, intercept=b, baseline=float(f"{baseline:.10g}"), inverted=a > 0, unit=unit,
                fit_error=round(error, 5), ticks=ticks, tolerance=round(tolerance, 4),
                pixel_fit_sensitivity=sensitivity,
                sensitivity_note="Sensitivity to ±2 pixels plus the maximum tick-fit residual. Not a statistical confidence interval; excludes OCR and model errors.",
                range=[min(t["value"] for t in ticks), max(t["value"] for t in ticks)])
    # A fitted line alone does not justify extrapolating the bar's baseline.
    # Equally tall bars can have both aligned edges; axis direction resolves it.
    expected_edge = "top" if a > 0 else "bottom"
    if edge != expected_edge:
        expected_bases = [bar["box"][1] + (bar["box"][3] if expected_edge == "bottom" else 0) for bar in bars]
        if np.ptp(expected_bases) <= max(4, h * .008):
            edge = expected_edge
            baseline_px = float(np.median(expected_bases))
            baseline = float(a * baseline_px + b)
            baseline = 0.0 if abs(baseline) <= tolerance and has_zero_tick else baseline
            axis["baseline"] = float(f"{baseline:.10g}")
            trace("inspection_policy", "Resolve shared edge", "Equally tall bars have two shared edges. Resolve the zero-baseline end using the numeric axis direction.",
                  {"shared_edge": edge, "baseline": axis["baseline"]})
        else:
            findings.append(dict(kind="unresolved_geometry", severity="review", title="The bar direction needs review",
                                 detail="The shared bar edge does not agree with the positive numeric scale. No reconstruction is generated.", evidence=[]))
            trace("inspection_policy", "Request human review", "Bar direction disagrees with the calibrated positive scale.")
            return result("review", "The measurements need human review.", axis=axis)

    trace("calibrate_axis", "Map pixels to values", f"Linear tick fit error: {error*100:.2f}% of the axis range. Visible bar baseline: {format_value(baseline, unit)}.",
          {"baseline": axis["baseline"], "inverted": a > 0, "fit_error": error, "baseline_tolerance": tolerance})
    if abs(baseline) <= tolerance and not has_zero_tick:
        findings.append(dict(kind="baseline_uncertain", severity="review", title="The baseline cannot be resolved",
                             detail="The fitted baseline is close to zero, but no zero tick was read. Pixel and OCR-fit error are too large to confidently distinguish a small nonzero baseline.", evidence=[]))
        trace("inspection_policy", "Request human review", "Do not round an uncertain baseline to zero without an observed zero tick.")
        return result("review", "The baseline needs human review.", axis=axis)

    for i, bar in enumerate(bars):
        x, y, bw, bh = bar["box"]
        endpoint = y if edge == "bottom" else y + bh
        bar["value"] = float(f"{a * endpoint + b:.10g}")
        bar["pixel_fit_range"] = [max(0, bar["value"]-sensitivity), max(0, bar["value"]+sensitivity)]
        bar["pixel_length"] = bh
        bar["label"] = f"Bar {i+1}"
    # Read category labels independently; failure does not fabricate names.
    label_y = min(h - 1, int(max(max(t["cy"] for t in ticks), max(bar["box"][1] + bar["box"][3] for bar in bars)) + 8))
    try:
        label_crop = cv2.resize(image[label_y:], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        label_words = ocr(label_crop, offset=(0, label_y), scale=2, psm=6)
        for bar in bars:
            x, y, bw, bh = bar["box"]
            center = x + bw / 2
            candidates = [word for word in label_words if abs(word["box"][0] + word["box"][2] / 2 - center) < bw * .85]
            if candidates:
                top = min(word["box"][1] for word in candidates)
                row = sorted([word for word in candidates if abs(word["box"][1] - top) < 16], key=lambda v: v["box"][0])
                bar["label"] = " ".join(word["text"] for word in row)[:50]
    except (pytesseract.TesseractNotFoundError, RuntimeError):
        pass
    trace("recover_values", "Measure bar endpoints", "Applied the fitted scale to each bar endpoint; category names come from OCR when readable.",
          {"estimated_values": [bar["value"] for bar in bars]})
    # Restrict reconstruction to observed endpoints inside the calibration envelope.
    low, high = axis["range"]
    if baseline < -tolerance or baseline < low - tolerance or baseline > high + tolerance or any(bar["value"] < -tolerance or bar["value"] < low - tolerance or bar["value"] > high + tolerance for bar in bars):
        findings.append(dict(kind="unresolved_geometry", severity="review", title="Bar geometry and scale disagree",
                             detail="Some endpoints fall outside the calibrated positive scale. This layout needs manual interpretation.", evidence=[]))
        trace("inspection_policy", "Request human review", "Recovered endpoints violate the calibrated range; no corrected chart is generated.")
        return result("review", "The measurements need human review.", axis=axis)
    for bar in bars:
        bar["value"] = max(0, bar["value"])

    if baseline > tolerance:
        findings.append(dict(kind="truncated_axis", severity="warning", title="The bars start above zero",
                             detail=f"The visible baseline is approximately {format_value(baseline, unit)}. Bar lengths therefore amplify proportional differences. A zero-baseline comparison makes that effect visible.",
                             evidence=[ticks[-1]] if a < 0 else [ticks[0]]))
    if a > 0:
        findings.append(dict(kind="inverted_axis", severity="warning", title="The numeric axis runs downward",
                             detail="Larger values appear lower in the image. This reverses the usual visual direction; context determines whether the choice is appropriate.", evidence=[ticks[0], ticks[-1]]))
    if not findings:
        findings.append(dict(kind="axis_checks_passed", severity="pass", title="The axis checks pass",
                             detail="The detected bars share a zero baseline and the values increase upward. This does not establish that the source data or wider claim is true.", evidence=[]))

    comparison = None
    if baseline > tolerance and not axis["inverted"]:
        smallest, largest = min(bars, key=lambda x: x["value"]), max(bars, key=lambda x: x["value"])
        if smallest["value"] > 0 and smallest["pixel_length"] > 0:
            apparent = largest["pixel_length"] / smallest["pixel_length"]
            actual = largest["value"] / smallest["value"]
            comparison = dict(apparent_ratio=round(apparent, 2), value_ratio=round(actual, 3),
                              actual_change_pct=round((actual - 1) * 100, 2),
                              first_label=smallest["label"], second_label=largest["label"],
                              explanation="Ratio of the longest to shortest visible bar, compared with the ratio of their recovered numeric values.")
    trace("inspection_policy", "Reconstruct chart", "Scale and bar geometry agree. Rebuild from recovered values with zero baseline and conventional upward direction.",
          {"findings": [f["kind"] for f in findings]})
    svg = reconstruction_svg(bars, unit)
    verified = verify_reconstruction(svg, bars)
    trace("verify_reconstruction", "Check preserved values", "Read back the generated SVG rectangles and verify their count, order, shared zero baseline, and numeric heights.",
          {"bar_count": len(bars), "data_source": "pixel_estimates", "geometry_verified": verified})
    if not verified:
        findings.append(dict(kind="render_verification_failed", severity="review", title="Reconstruction did not verify",
                             detail="The generated geometry did not preserve the recovered values within rendering tolerance. The reconstruction is withheld.", evidence=[]))
        return result("review", "The reconstruction needs human review.", axis=axis)
    status = "flagged" if any(f["severity"] == "warning" for f in findings) else "clear"
    summary = "The presentation changes the apparent comparison." if status == "flagged" else "No supported axis issue found."
    return result(status, summary, bars, axis, svg, comparison)
