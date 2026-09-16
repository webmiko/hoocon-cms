"""Unified plain-text GigaChat KB: one file, markdown headings for navigation."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PACKAGED_KB_PATH = Path(__file__).resolve().parents[1] / "data" / "gigachat_kb.txt"
KB_LINE_WIDTH = 119


@dataclass(frozen=True, slots=True)
class ManualChunk:
    """One manual excerpt for the AI context."""

    source: str  # ``html`` | ``pdf``
    label: str
    text: str


_META_RE = re.compile(
    r"<!--\s*kb-meta:\s*version=(\d+)\s+built_at=([^\s]+)\s+html=(\d+)\s+pdf=(\d+)\s*-->",
)
_CHUNK_HEADING_RE = re.compile(r"^###\s+(.+)$")


@dataclass(frozen=True, slots=True)
class KbDocumentMeta:
    """Header metadata embedded in the committed KB text file."""

    version: int
    built_at: str
    html_count: int
    pdf_count: int


def _wrap_plain(text: str, *, width: int = KB_LINE_WIDTH) -> str:
    return textwrap.fill(
        text,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )


def _wrap_prefixed(text: str, prefix: str, *, width: int = KB_LINE_WIDTH) -> str:
    return textwrap.fill(
        text[len(prefix) :],
        width=width,
        initial_indent=prefix,
        subsequent_indent=" " * len(prefix),
        break_long_words=False,
        break_on_hyphens=False,
    )


def _wrap_heading(line: str, *, width: int = KB_LINE_WIDTH) -> str:
    if len(line) <= width:
        return line
    match = re.match(r"^(#+)\s+", line)
    if not match:
        return _wrap_plain(line, width=width)
    hashes = match.group(1)
    head = f"{hashes} "
    return textwrap.fill(
        line[len(head) :],
        width=width,
        initial_indent=head,
        subsequent_indent=" " * len(head),
        break_long_words=False,
        break_on_hyphens=False,
    )


def _append_wrapped_lines(lines: list[str], block: str) -> None:
    """Split block into lines respecting the 119-char repo limit."""
    for line in block.splitlines():
        if not line:
            lines.append("")
            continue
        if line.startswith("@"):
            lines.append(line)
            continue
        if line.startswith("#"):
            lines.append(_wrap_heading(line))
            continue
        if line.startswith("- "):
            lines.append(_wrap_prefixed(line, "- "))
            continue
        if line.startswith(("В: ", "О: ")):
            lines.append(_wrap_prefixed(line, line[:3]))
            continue
        if len(line) <= KB_LINE_WIDTH:
            lines.append(line)
            continue
        lines.extend(_wrap_plain(line, width=KB_LINE_WIDTH).splitlines())


def format_kb_document(
    chunks: list[ManualChunk],
    *,
    meta: KbDocumentMeta,
    site_sections: list[tuple[str, str]] | None = None,
) -> str:
    """Render one navigable text KB with ``#`` / ``##`` / ``###`` headings."""
    lines: list[str] = []
    _append_wrapped_lines(
        lines,
        "\n".join(
            (
                "# База знаний Hoocon — GigaChat",
                "",
                (
                    f"<!-- kb-meta: version={meta.version} built_at={meta.built_at} "
                    f"html={meta.html_count} pdf={meta.pdf_count} -->"
                ),
                "",
                "Один файл вместо локальных папок ``_manuals-ru`` и ``_инструкции-pdf``.",
                "Разделы ``##`` — темы; ``###`` — отдельный мануал или страница.",
            ),
        ),
    )
    lines.append("")

    if site_sections:
        lines.append("## Сайт hoocon.ru (снимок на момент сборки)")
        lines.append("")
        for title, body in site_sections:
            cleaned = (body or "").strip()
            if not cleaned or cleaned == "—":
                continue
            _append_wrapped_lines(lines, f"### {title}")
            lines.append("")
            _append_wrapped_lines(lines, cleaned)
            lines.append("")

    html_chunks = [chunk for chunk in chunks if chunk.source == "html"]
    pdf_chunks = [chunk for chunk in chunks if chunk.source == "pdf"]

    lines.append("## HTML-руководства (_manuals-ru)")
    lines.append("")
    if html_chunks:
        for chunk in html_chunks:
            _append_wrapped_lines(lines, f"### {chunk.label}")
            lines.append("")
            _append_wrapped_lines(lines, chunk.text.strip())
            lines.append("")
    else:
        lines.append("—")
        lines.append("")

    lines.append("## PDF-инструкции (_инструкции-pdf)")
    lines.append("")
    if pdf_chunks:
        for chunk in pdf_chunks:
            _append_wrapped_lines(lines, f"### {chunk.label}")
            lines.append("")
            _append_wrapped_lines(lines, chunk.text.strip())
            lines.append("")
    else:
        lines.append("—")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_kb_meta(text: str) -> KbDocumentMeta | None:
    """Read embedded metadata from the KB file header."""
    match = _META_RE.search(text)
    if not match:
        return None
    return KbDocumentMeta(
        version=int(match.group(1)),
        built_at=match.group(2),
        html_count=int(match.group(3)),
        pdf_count=int(match.group(4)),
    )


def parse_manual_chunks(text: str) -> tuple[ManualChunk, ...]:
    """Extract manual ``###`` sections from the unified KB text file."""
    in_manuals = False
    current_label = ""
    current_lines: list[str] = []
    chunks: list[ManualChunk] = []

    def flush() -> None:
        nonlocal current_label, current_lines
        if not in_manuals or not current_label:
            current_label = ""
            current_lines = []
            return
        body = "\n".join(current_lines).strip()
        if body and body != "—":
            source = "pdf" if current_label.startswith("_инструкции-pdf/") else "html"
            chunks.append(ManualChunk(source=source, label=current_label, text=body))
        current_label = ""
        current_lines = []

    for line in text.splitlines():
        if line.startswith("## HTML-руководства"):
            flush()
            in_manuals = True
            continue
        if line.startswith("## PDF-инструкции"):
            flush()
            in_manuals = True
            continue
        if not in_manuals:
            continue
        heading = _CHUNK_HEADING_RE.match(line)
        if heading:
            flush()
            current_label = heading.group(1).strip()
            continue
        if current_label:
            current_lines.append(line)

    flush()
    return tuple(chunks)


@lru_cache(maxsize=1)
def load_kb_text(path: Path | None = None) -> str:
    """Read committed KB text (empty string if missing)."""
    kb_path = (path or PACKAGED_KB_PATH).resolve()
    if not kb_path.is_file():
        return ""
    try:
        return kb_path.read_text(encoding="utf-8")
    except OSError:
        return ""


def load_packaged_chunks(path: Path | None = None) -> tuple[ManualChunk, ...]:
    """Load manual chunks from the unified ``gigachat_kb.txt`` file."""
    text = load_kb_text(path)
    if not text:
        return ()
    return parse_manual_chunks(text)
