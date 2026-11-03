"""Shrink large PDFs with Ghostscript so the in-browser PDF engine can load them.

The reader uses PDFium compiled to WASM; very large PDFs exhaust its memory
("error code 1" / endless "loading"). We re-write the file once with
Ghostscript's ``/ebook`` preset — it downsamples images and drops bloat while
keeping text selectable — and serve the smaller copy. Ingestion parses the same
file, so structure/text are preserved.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def ghostscript_available() -> bool:
    return shutil.which("gs") is not None


async def optimize_pdf(
    data: bytes,
    *,
    preset: str = "/ebook",
    timeout_seconds: float = 300.0,
) -> bytes | None:
    """Return a smaller PDF, or ``None`` if Ghostscript is unavailable, fails, or
    the result is not actually smaller.
    """
    if not ghostscript_available():
        return None

    workdir = Path(tempfile.mkdtemp(prefix="pdfopt-"))
    src = workdir / "in.pdf"
    dst = workdir / "out.pdf"
    try:
        src.write_bytes(data)
        cmd = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.7",
            f"-dPDFSETTINGS={preset}",
            "-dNOPAUSE",
            "-dBATCH",
            "-dQUIET",
            "-dDetectDuplicateImages=true",
            "-dCompressFonts=true",
            "-o",
            str(dst),
            str(src),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout_seconds)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            logger.warning("Ghostscript timed out after %ss", timeout_seconds)
            return None

        if proc.returncode != 0 or not dst.exists():
            logger.warning("Ghostscript failed: %s", (stderr or b"")[:300])
            return None

        optimized = dst.read_bytes()
        if not optimized or len(optimized) >= len(data):
            return None
        return optimized
    except Exception as exc:  # noqa: BLE001
        logger.warning("PDF optimization error: %s", exc)
        return None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
