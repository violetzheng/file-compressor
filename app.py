"""
Endpoints
POST /api/analyze  -> upload a file, get its original size + minimum achievable size
POST /api/compress -> upload a file + target size (bytes), get back a compressed
                      file of the same type, as close to (and under) the target
                      as possible.

Supported JPEG, PNG, WebP, and PDF.
"""

import io
import os
import shutil
import subprocess
import tempfile

from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB upload cap

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PDF_EXTS = {".pdf"}

MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def ext_of(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


# Image compression (Pillow)

def compress_image(data: bytes, ext: str, quality: int) -> bytes:
    """Re-encode an image at a given quality (1-95). For PNG, 'quality'
    maps to palette size, since PNG is lossless otherwise."""
    img = Image.open(io.BytesIO(data))
    buf = io.BytesIO()

    if ext in (".jpg", ".jpeg"):
        img = img.convert("RGB")
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    elif ext == ".webp":
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        img.save(buf, "WEBP", quality=quality, method=6)
    elif ext == ".png":
        # Map quality 1-95 -> palette of 8-256 colors.
        colors = max(8, min(256, round(quality / 95 * 256)))
        img = img.convert("RGBA").quantize(colors=colors, method=Image.FASTOCTREE)
        img.save(buf, "PNG", optimize=True)
    else:
        raise ValueError(f"Unsupported image type: {ext}")

    return buf.getvalue()


def image_bounds(data: bytes, ext: str) -> tuple[int, int]:
    """Return (min_size, max_size) achievable by re-encoding."""
    smallest = len(compress_image(data, ext, 1))
    return min(smallest, len(data)), len(data)


def image_to_target(data: bytes, ext: str, target: int) -> bytes:
    """Binary-search quality for the best result at or under `target` bytes."""
    lo, hi = 1, 95
    best = compress_image(data, ext, lo)  # guaranteed floor
    while lo <= hi:
        mid = (lo + hi) // 2
        out = compress_image(data, ext, mid)
        if len(out) <= target:
            best = out
            lo = mid + 1  # room for more quality
        else:
            hi = mid - 1
    return best


# --------------------------------------------------------------------------
# PDF compression (Ghostscript)
# --------------------------------------------------------------------------

# Ordered from highest quality (largest) to lowest quality (smallest).
GS_PRESETS = ["/prepress", "/printer", "/ebook", "/screen"]


def ghostscript_available() -> bool:
    return shutil.which("gs") is not None


def compress_pdf(data: bytes, preset: str) -> bytes:
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "in.pdf")
        dst = os.path.join(tmp, "out.pdf")
        with open(src, "wb") as f:
            f.write(data)
        subprocess.run(
            [
                "gs", "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                f"-dPDFSETTINGS={preset}",
                "-dNOPAUSE", "-dQUIET", "-dBATCH",
                f"-sOutputFile={dst}", src,
            ],
            check=True,
            capture_output=True,
        )
        with open(dst, "rb") as f:
            out = f.read()
    # Ghostscript can occasionally *grow* a file; never return worse than input.
    return out if len(out) < len(data) else data


def pdf_bounds(data: bytes) -> tuple[int, int]:
    smallest = compress_pdf(data, "/screen")
    return len(smallest), len(data)


def pdf_to_target(data: bytes, target: int) -> bytes:
    """Try presets from highest quality down; return the best one that fits,
    else the smallest achievable."""
    smallest = None
    for preset in GS_PRESETS:
        out = compress_pdf(data, preset)
        if len(out) <= target:
            return out
        if smallest is None or len(out) < len(smallest):
            smallest = out
    return smallest


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/")
def index():
    return render_template("index.html")


def _get_upload():
    f = request.files.get("file")
    if f is None or f.filename == "":
        return None, None, (jsonify(error="No file uploaded."), 400)
    ext = ext_of(f.filename)
    if ext not in IMAGE_EXTS | PDF_EXTS:
        return None, None, (
            jsonify(error="Unsupported type. Use JPG, PNG, WebP, or PDF."), 415)
    if ext in PDF_EXTS and not ghostscript_available():
        return None, None, (
            jsonify(error="PDF support needs Ghostscript installed on the "
                          "server (see README)."), 501)
    return f.read(), ext, None


@app.post("/api/analyze")
def analyze():
    data, ext, err = _get_upload()
    if err:
        return err
    try:
        if ext in IMAGE_EXTS:
            min_size, max_size = image_bounds(data, ext)
        else:
            min_size, max_size = pdf_bounds(data)
    except Exception:
        return jsonify(error="Could not read that file — it may be corrupt."), 422
    return jsonify(
        original_size=max_size,
        min_size=min_size,
        file_type=ext.lstrip("."),
    )


@app.post("/api/compress")
def compress():
    data, ext, err = _get_upload()
    if err:
        return err
    try:
        target = int(request.form["target"])
        if target <= 0:
            raise ValueError
    except (KeyError, ValueError):
        return jsonify(error="Provide a positive target size in bytes."), 400

    try:
        if len(data) <= target:
            out = data  # already small enough
        elif ext in IMAGE_EXTS:
            out = image_to_target(data, ext, target)
        else:
            out = pdf_to_target(data, target)
    except Exception:
        return jsonify(error="Compression failed for that file."), 422

    name = request.files["file"].filename
    stem, _ = os.path.splitext(os.path.basename(name))
    return send_file(
        io.BytesIO(out),
        mimetype=MIME_BY_EXT[ext],
        as_attachment=True,
        download_name=f"{stem}-compressed{ext}",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
