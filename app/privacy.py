"""Small shared privacy boundaries for file names and exported reports."""
import unicodedata


def display_filename(filename: str | None) -> str:
    """Keep a short display name, never client directory paths or controls."""
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if not unicodedata.category(c).startswith("C")).strip()
    return name[:120] if name and name not in {".", ".."} else "chart.png"


def inspection_report(result: dict) -> dict:
    """Reports still contain OCR text and estimates, but not embedded images."""
    return {key: value for key, value in result.items() if key not in {"image", "reconstruction"}}
