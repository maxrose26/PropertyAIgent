"""Page rendering + safe on-disk storage for visual evidence (Sprint 3C,
"Allocation and Site-Plan Image Extraction", Part 6 rendering requirements
and Part 17 security controls).

Renders ONE specific page of ONE specific source PDF to an image file plus
a thumbnail, under data/visuals/ (already covered by the project's
.gitignore data/ rule - rendered images are never committed to Git).
Storage keys are derived only from known-safe identifiers (council code,
document id, page number, render version) - never from a document's own
title or filename - so there is no path-traversal surface at all, and the
same (document, page, render version) request always lands on the same
file, giving idempotency for free at the storage layer.

Rendering untrusted PDFs is the same hazard app.extraction.pdf_text
already solved for text extraction (a pathological, densely-vectorised
drawing can blow past several GB of memory) - this module mirrors that
module's subprocess-timeout pattern exactly rather than inventing a new
one, including the queue-read-before-join ordering that avoids a real
confirmed deadlock in that module.
"""
from __future__ import annotations

import hashlib
import multiprocessing
import re
from pathlib import Path

from app.db.session import DATA_DIR

VISUALS_DIR = DATA_DIR / "visuals"

RENDER_TIMEOUT_SECONDS = 60
# Drawings are image-heavy scans/CAD exports - allow more headroom than
# text extraction's 15MB, but still refuse the pathological cases outright
# rather than let a subprocess spend a minute rendering one page.
MAX_RENDERABLE_FILE_SIZE = 25 * 1024 * 1024  # 25MB
MAX_PAGE_NUMBER = 500  # a requested page beyond this is refused outright, never silently clamped

RENDER_RESOLUTION = 200  # dpi - legible for site/location plans without unusably large files
THUMBNAIL_MAX_DIMENSION = 400

# Bump this to force every page to be re-rendered even though its source
# file is unchanged (Part 14: "explicit render-version reprocess request").
RENDER_VERSION = "v1"


def safe_storage_key(council_code: str, document_id: int | str, page_number: int, render_version: str = RENDER_VERSION) -> str:
    """A filesystem-safe, collision-resistant key for one rendered page -
    built only from known-safe identifiers, never from user/portal-
    supplied text, so there is nothing here an attacker-controlled title
    could inject a path segment into."""
    council_part = re.sub(r"[^\w\-]", "_", str(council_code))[:50] or "unknown"
    document_part = re.sub(r"[^\w\-]", "_", str(document_id))[:50] or "unknown"
    return f"{council_part}_{document_part}_p{page_number}_{render_version}"


def _visuals_dir_for(council_code: str) -> Path:
    folder = VISUALS_DIR / (re.sub(r"[^\w\-]", "_", str(council_code))[:50] or "unknown")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _resolve_safe_path(folder: Path, filename: str) -> Path:
    """Resolves filename against folder and verifies the result is still
    inside folder - defence in depth alongside safe_storage_key never
    accepting free text (Part 17: path-traversal prevention)."""
    folder_resolved = folder.resolve()
    candidate = (folder / filename).resolve()
    if candidate != folder_resolved and folder_resolved not in candidate.parents:
        raise ValueError("resolved path escapes the visuals storage directory")
    return candidate


def compute_file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_page_render_hash(source_file_hash: str, page_number: int, render_version: str = RENDER_VERSION) -> str:
    """Identity hash for "this exact page, of this exact source file,
    rendered at this exact render-pipeline version" - derived from the
    SOURCE file's own hash, not the rendered image's bytes. This is what
    the orchestration pipeline (app.visuals.pipeline) checks against
    existing VisualEvidence rows BEFORE calling render_page at all, so an
    unchanged document skips rendering - and the AI classification that
    would otherwise follow it - without ever touching the file again."""
    return hashlib.sha256(f"{source_file_hash}:{page_number}:{render_version}".encode("utf-8")).hexdigest()


def _render_in_subprocess(
    pdf_path_str: str, page_number: int, resolution: int, image_dest_str: str,
    thumb_dest_str: str, thumb_max_dim: int, result_queue,
) -> None:
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path_str) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                result_queue.put({"error": "page_out_of_range"})
                return
            page = pdf.pages[page_number - 1]
            page_image = page.to_image(resolution=resolution)
            page_image.save(image_dest_str)
            width, height = page_image.original.size

            thumbnail = page_image.original.copy()
            thumbnail.thumbnail((thumb_max_dim, thumb_max_dim))
            thumbnail.save(thumb_dest_str)

        result_queue.put({"width": width, "height": height})
    except Exception as exc:
        result_queue.put({"error": str(exc)[:300]})


def _existing_render_result(image_dest: Path, thumb_dest: Path) -> dict:
    from PIL import Image

    with Image.open(image_dest) as img:
        width, height = img.size
    return {
        "image_path": str(image_dest),
        "thumbnail_path": str(thumb_dest),
        "image_width": width,
        "image_height": height,
        "file_hash": compute_file_hash(image_dest),
    }


def render_page(
    pdf_path: Path, page_number: int, council_code: str, document_id: int | str,
    render_version: str = RENDER_VERSION, force: bool = False,
) -> dict | None:
    """Renders a single page to an image + thumbnail under
    data/visuals/{council}/, returning
    {"image_path", "thumbnail_path", "image_width", "image_height",
    "file_hash"} - or None if rendering failed or was refused outright
    (oversized source file, out-of-range page). Idempotent: if the target
    files already exist for this exact (council, document_id, page_number,
    render_version) key and force is False, returns their existing
    metadata without touching the source PDF again (Part 6/Part 14 -
    "avoid unnecessary re-rendering")."""
    pdf_path = Path(pdf_path)
    if page_number < 1 or page_number > MAX_PAGE_NUMBER:
        return None
    try:
        if pdf_path.stat().st_size > MAX_RENDERABLE_FILE_SIZE:
            return None
    except OSError:
        return None

    folder = _visuals_dir_for(council_code)
    key = safe_storage_key(council_code, document_id, page_number, render_version)
    try:
        image_dest = _resolve_safe_path(folder, f"{key}.png")
        thumb_dest = _resolve_safe_path(folder, f"{key}_thumb.png")
    except ValueError:
        # A resolved path escaping the storage directory should never
        # happen given safe_storage_key's own sanitisation, but treat it
        # as a hard refusal rather than an unhandled exception that could
        # take down an entire batch run over one bad input (Part 17).
        return None

    if not force and image_dest.exists() and thumb_dest.exists():
        return _existing_render_result(image_dest, thumb_dest)

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    process = ctx.Process(
        target=_render_in_subprocess,
        args=(str(pdf_path), page_number, RENDER_RESOLUTION, str(image_dest), str(thumb_dest), THUMBNAIL_MAX_DIMENSION, result_queue),
    )
    process.start()
    # Read before join - see app.extraction.pdf_text.extract_document_text
    # for the confirmed deadlock this ordering avoids.
    try:
        result = result_queue.get(timeout=RENDER_TIMEOUT_SECONDS)
    except Exception:
        result = {"error": "timeout"}
    if process.is_alive():
        process.terminate()
        process.join(timeout=5)
        if process.is_alive():
            process.kill()
    else:
        process.join(timeout=5)

    if "error" in result:
        # Never leave a half-written file behind on failure (Part 6:
        # "cleanup on failure").
        for path in (image_dest, thumb_dest):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        return None

    return {
        "image_path": str(image_dest),
        "thumbnail_path": str(thumb_dest),
        "image_width": result["width"],
        "image_height": result["height"],
        "file_hash": compute_file_hash(image_dest),
    }
