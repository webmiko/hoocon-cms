"""Read text back from a rendered quote PDF."""

from __future__ import annotations

import io

import pypdfium2 as pdfium


def pdf_text(buf: io.BytesIO) -> str:
    """Return the text of every page, in order."""
    document = pdfium.PdfDocument(buf.getvalue())
    try:
        parts: list[str] = []
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            parts.append(text_page.get_text_bounded())
            text_page.close()
            page.close()
        return "\n".join(parts).replace("\u200b", "")
    finally:
        document.close()
